#!/usr/bin/env python3
"""
Milvus Trace Analyzer -- Query Jaeger traces and analyze with Ollama.

Fetches recent Milvus (or any service) traces from the Jaeger REST API,
formats them into structured context, and sends them to an Ollama-hosted
LLM for on-demand diagnosis and analysis.

Usage:
    python analyze-traces.py --lookback 1h
    python analyze-traces.py --lookback 4h --question "Why are inserts slow?"
    python analyze-traces.py --model mistral --lookback 1h --interactive
    python analyze-traces.py --service milvus --limit 30
    python analyze-traces.py --jaeger-url http://192.168.12.112:16686
"""

import argparse
import json
import re
import sys
import textwrap
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_JAEGER_URL = "http://jaeger.local:16686"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3"
DEFAULT_SERVICE = "milvus"
DEFAULT_LIMIT = 20
DEFAULT_LOOKBACK = "1h"

SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Kubernetes and distributed-systems observability engineer.
    You specialise in Milvus vector-database deployments running on k3s clusters
    with mixed amd64/arm64 nodes (Raspberry Pi 5 workers, Ubuntu Desktop control
    plane).

    The user will provide you with distributed trace data collected via
    OpenTelemetry and stored in Jaeger.  Each trace contains spans with
    operation names, durations, status codes, tags, and parent-child
    relationships.

    When analysing traces:
    - Identify slow operations, errors, and anomalous patterns.
    - Correlate span durations with dependent services (etcd, MinIO, OTel).
    - Flag potential causes: resource pressure, network latency, scheduling
      issues (ARM vs amd64), storage I/O, etcd leader election delays.
    - Provide concrete, actionable recommendations with kubectl commands or
      Helm value changes where appropriate.
    - Be concise; use bullet points for findings.
""")

# ---------------------------------------------------------------------------
# Jaeger client
# ---------------------------------------------------------------------------


def _http_get_json(url: str, timeout: int = 30) -> dict:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def parse_lookback(lookback: str) -> timedelta:
    match = re.fullmatch(r"(\d+)\s*(h|m|d)", lookback.strip().lower())
    if not match:
        raise ValueError(f"Invalid lookback format '{lookback}'. Use e.g. 1h, 30m, 2d.")
    value, unit = int(match.group(1)), match.group(2)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "m":
        return timedelta(minutes=value)
    return timedelta(days=value)


def fetch_services(jaeger_url: str) -> list[str]:
    data = _http_get_json(f"{jaeger_url}/api/services")
    return sorted(data.get("data", []))


def fetch_traces(
    jaeger_url: str,
    service: str,
    lookback: timedelta,
    limit: int,
) -> list[dict]:
    now = datetime.now(tz=timezone.utc)
    start_us = int((now - lookback).timestamp() * 1_000_000)
    end_us = int(now.timestamp() * 1_000_000)

    url = (
        f"{jaeger_url}/api/traces"
        f"?service={service}"
        f"&start={start_us}"
        f"&end={end_us}"
        f"&limit={limit}"
    )
    data = _http_get_json(url)
    return data.get("data", [])


# ---------------------------------------------------------------------------
# Trace formatting
# ---------------------------------------------------------------------------

def _us_to_ms(us: int) -> float:
    return round(us / 1000, 2)


def _process_map(trace: dict) -> dict[str, str]:
    """Map processID -> serviceName."""
    mapping: dict[str, str] = {}
    for pid, pinfo in trace.get("processes", {}).items():
        mapping[pid] = pinfo.get("serviceName", pid)
    return mapping


def _tag_dict(tags: list[dict]) -> dict[str, str]:
    return {t["key"]: t.get("value", "") for t in tags} if tags else {}


def format_trace(trace: dict) -> str:
    pmap = _process_map(trace)
    spans = trace.get("spans", [])
    trace_id = trace.get("traceID", "unknown")
    spans_sorted = sorted(spans, key=lambda s: s.get("startTime", 0))

    lines = [f"Trace {trace_id}  ({len(spans)} spans)"]
    lines.append("-" * 60)

    for span in spans_sorted:
        op = span.get("operationName", "?")
        dur_ms = _us_to_ms(span.get("duration", 0))
        svc = pmap.get(span.get("processID", ""), "?")
        tags = _tag_dict(span.get("tags", []))
        logs_entries = span.get("logs", [])

        status = tags.get("otel.status_code", tags.get("status.code", "OK"))
        error_flag = "ERROR" if tags.get("error", "") == "true" or status == "ERROR" else ""

        ref_str = ""
        refs = span.get("references", [])
        if refs:
            parent = refs[0].get("spanID", "")[:8]
            ref_str = f"  parent={parent}"

        line = f"  [{svc}] {op}  {dur_ms}ms  {status}"
        if error_flag:
            line += f"  **{error_flag}**"
        line += ref_str

        # Attach notable tags
        notable_keys = [
            "db.system", "db.operation", "db.statement",
            "net.peer.name", "net.peer.port",
            "http.method", "http.status_code", "http.url",
            "rpc.method", "rpc.service",
        ]
        notable = {k: tags[k] for k in notable_keys if k in tags}
        if notable:
            line += f"\n    tags: {json.dumps(notable)}"

        if logs_entries:
            for le in logs_entries[:3]:
                msg_parts = [f.get("value", "") for f in le.get("fields", []) if f.get("key") == "message"]
                if msg_parts:
                    line += f"\n    log: {msg_parts[0][:200]}"

        lines.append(line)

    return "\n".join(lines)


def format_all_traces(traces: list[dict]) -> str:
    if not traces:
        return "(no traces found in the given time window)"
    sections = [format_trace(t) for t in traces]
    header = f"=== {len(traces)} trace(s) retrieved ===\n"
    return header + "\n\n".join(sections)


def build_summary_stats(traces: list[dict]) -> str:
    if not traces:
        return ""

    total_spans = 0
    error_spans = 0
    durations: list[float] = []
    services: set[str] = set()
    operations: dict[str, list[float]] = {}

    for trace in traces:
        pmap = _process_map(trace)
        for span in trace.get("spans", []):
            total_spans += 1
            dur_ms = _us_to_ms(span.get("duration", 0))
            durations.append(dur_ms)
            svc = pmap.get(span.get("processID", ""), "?")
            services.add(svc)
            op = span.get("operationName", "?")
            operations.setdefault(op, []).append(dur_ms)

            tags = _tag_dict(span.get("tags", []))
            if tags.get("error") == "true" or tags.get("otel.status_code") == "ERROR":
                error_spans += 1

    durations.sort()
    p50 = durations[len(durations) // 2] if durations else 0
    p99 = durations[int(len(durations) * 0.99)] if durations else 0

    slowest_ops = sorted(operations.items(), key=lambda kv: max(kv[1]), reverse=True)[:5]

    lines = [
        "--- Trace Statistics ---",
        f"Traces: {len(traces)}  |  Total spans: {total_spans}  |  Error spans: {error_spans}",
        f"Services seen: {', '.join(sorted(services))}",
        f"Span duration  p50={p50}ms  p99={p99}ms  "
        f"min={min(durations):.2f}ms  max={max(durations):.2f}ms",
        "",
        "Slowest operations (by max duration):",
    ]
    for op, durs in slowest_ops:
        lines.append(f"  {op}: max={max(durs):.2f}ms  avg={sum(durs)/len(durs):.2f}ms  count={len(durs)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------


def ollama_generate(
    ollama_url: str,
    model: str,
    prompt: str,
    system: str = SYSTEM_PROMPT,
    timeout: int = 120,
) -> str:
    payload = json.dumps({
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
    }).encode()

    req = Request(
        f"{ollama_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    return body.get("response", "(empty response from model)")


def ollama_chat(
    ollama_url: str,
    model: str,
    messages: list[dict],
    timeout: int = 120,
) -> str:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
    }).encode()

    req = Request(
        f"{ollama_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    return body.get("message", {}).get("content", "(empty response)")


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------


def interactive_loop(
    ollama_url: str,
    model: str,
    trace_context: str,
    stats: str,
) -> None:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            "Here are the traces I collected from my Milvus deployment:\n\n"
            f"{stats}\n\n{trace_context}\n\n"
            "Please provide an initial analysis of these traces."
        )},
    ]

    print("\n[Sending traces to Ollama for initial analysis...]\n")
    try:
        initial = ollama_chat(ollama_url, model, messages)
    except (HTTPError, URLError, OSError) as exc:
        print(f"Error contacting Ollama at {ollama_url}: {exc}", file=sys.stderr)
        print("Make sure Ollama is running (ollama serve) and the model is pulled.", file=sys.stderr)
        return

    messages.append({"role": "assistant", "content": initial})
    print(initial)
    print("\n" + "=" * 60)
    print("Interactive mode -- type your follow-up questions (Ctrl+C or 'quit' to exit)")
    print("=" * 60)

    while True:
        try:
            question = input("\nYou> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not question or question.lower() in ("quit", "exit", "q"):
            break

        messages.append({"role": "user", "content": question})
        try:
            answer = ollama_chat(ollama_url, model, messages)
        except (HTTPError, URLError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            continue

        messages.append({"role": "assistant", "content": answer})
        print(f"\n{answer}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Query Jaeger traces and analyze with Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              %(prog)s --lookback 1h
              %(prog)s --lookback 4h --question "Why are inserts slow?"
              %(prog)s --model mistral --lookback 1h --interactive
              %(prog)s --jaeger-url http://192.168.12.112:16686 --service milvus
              %(prog)s --list-services
        """),
    )
    p.add_argument("--jaeger-url", default=DEFAULT_JAEGER_URL, help="Jaeger query URL")
    p.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="Ollama API URL")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name")
    p.add_argument("--service", default=DEFAULT_SERVICE, help="Service name to query traces for")
    p.add_argument("--lookback", default=DEFAULT_LOOKBACK, help="Time window: e.g. 1h, 30m, 2d")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max traces to fetch")
    p.add_argument("--question", "-q", default=None, help="One-shot question about the traces")
    p.add_argument("--interactive", "-i", action="store_true", help="Enter interactive follow-up mode")
    p.add_argument("--list-services", action="store_true", help="List available services in Jaeger and exit")
    p.add_argument("--raw", action="store_true", help="Print formatted traces without sending to Ollama")
    return p


def main() -> None:
    args = build_parser().parse_args()

    # ---- List services mode ----
    if args.list_services:
        try:
            services = fetch_services(args.jaeger_url)
        except (HTTPError, URLError, OSError) as exc:
            print(f"Error reaching Jaeger at {args.jaeger_url}: {exc}", file=sys.stderr)
            sys.exit(1)
        print("Services reporting to Jaeger:")
        for svc in services:
            print(f"  - {svc}")
        return

    # ---- Fetch traces ----
    lookback = parse_lookback(args.lookback)
    print(f"Fetching up to {args.limit} traces for '{args.service}' "
          f"(last {args.lookback}) from {args.jaeger_url} ...")

    try:
        traces = fetch_traces(args.jaeger_url, args.service, lookback, args.limit)
    except (HTTPError, URLError, OSError) as exc:
        print(f"Error reaching Jaeger at {args.jaeger_url}: {exc}", file=sys.stderr)
        print("\nTroubleshooting:", file=sys.stderr)
        print("  1. Verify Jaeger is reachable:  curl " + args.jaeger_url + "/api/services", file=sys.stderr)
        print("  2. Check hosts file has jaeger.local mapped to the LoadBalancer IP", file=sys.stderr)
        print("  3. Try --jaeger-url http://<control-plane-ip>:16686", file=sys.stderr)
        sys.exit(1)

    print(f"Retrieved {len(traces)} trace(s).\n")
    trace_context = format_all_traces(traces)
    stats = build_summary_stats(traces)

    if stats:
        print(stats)
        print()

    # ---- Raw mode: just print traces ----
    if args.raw:
        print(trace_context)
        return

    if not traces:
        print("No traces found. Nothing to analyze.")
        print(f"Hint: verify the service name with --list-services")
        return

    # ---- Interactive mode ----
    if args.interactive:
        interactive_loop(args.ollama_url, args.model, trace_context, stats)
        return

    # ---- One-shot analysis ----
    question = args.question or "Analyze these traces. Identify errors, latency issues, and potential root causes."

    prompt = (
        f"Here are recent traces from the '{args.service}' service in my k3s cluster:\n\n"
        f"{stats}\n\n{trace_context}\n\n"
        f"Question: {question}"
    )

    print(f"[Sending to Ollama ({args.model}) at {args.ollama_url} ...]\n")
    try:
        response = ollama_generate(args.ollama_url, args.model, prompt)
    except (HTTPError, URLError, OSError) as exc:
        print(f"Error contacting Ollama at {args.ollama_url}: {exc}", file=sys.stderr)
        print("Make sure Ollama is running (ollama serve) and the model is pulled:", file=sys.stderr)
        print(f"  ollama pull {args.model}", file=sys.stderr)
        sys.exit(1)

    print(response)


if __name__ == "__main__":
    main()
