#!/usr/bin/env python3
"""
Pod Debugging and Diagnostics Tool
===================================
Version: 1.0.0

Comprehensive pod debugging tool for the RPi Kubernetes cluster.
Inspects pod status, events, logs, PVCs, images, node resources,
cross-service dependencies, and provides actionable recommendations.

Usage:
    python debug_pods.py                                  # All namespaces
    python debug_pods.py -n observability                 # Specific namespace
    python debug_pods.py -n management -p management-api  # Specific pod
    python debug_pods.py -l "app=grafana"                 # By label
    python debug_pods.py --failing-only                   # Only failing pods
    python debug_pods.py --json                           # JSON output
    python debug_pods.py --logs --tail 100                # Include logs

Prerequisites:
    - kubectl configured and working
    - Python 3.8+
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# =============================================================================
# ANSI colors for terminal output
# =============================================================================

class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def cprint(msg: str, color: str = Color.WHITE):
    print(f"{color}{msg}{Color.RESET}")


def header(title: str):
    line = "=" * 80
    cprint(f"\n{line}", Color.CYAN)
    cprint(f"  {title}", Color.CYAN)
    cprint(line, Color.CYAN)


def subheader(title: str):
    line = "-" * 60
    cprint(f"\n{line}", Color.YELLOW)
    cprint(f"  {title}", Color.YELLOW)
    cprint(line, Color.YELLOW)


def ok(msg: str):
    cprint(f"  [OK]    {msg}", Color.GREEN)


def warn(msg: str):
    cprint(f"  [WARN]  {msg}", Color.YELLOW)


def fail(msg: str):
    cprint(f"  [FAIL]  {msg}", Color.RED)


def info(msg: str):
    cprint(f"  [INFO]  {msg}", Color.WHITE)


def recommend(msg: str):
    cprint(f"  [FIX]   {msg}", Color.MAGENTA)


# =============================================================================
# kubectl helpers
# =============================================================================

KUBECONFIG: Optional[str] = None


def kubectl(args: str, parse_json: bool = False) -> dict:
    """Run a kubectl command and return the result."""
    cmd = ["kubectl"]
    if KUBECONFIG:
        cmd.extend(["--kubeconfig", KUBECONFIG])
    cmd.extend(args.split())

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        if parse_json and output:
            return {"success": result.returncode == 0, "data": json.loads(output)}
        return {"success": result.returncode == 0, "output": output, "error": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Command timed out"}
    except json.JSONDecodeError:
        return {"success": False, "output": output, "error": "Invalid JSON"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def kubectl_json(args: str) -> dict:
    """Run kubectl with -o json and parse the result."""
    return kubectl(f"{args} -o json", parse_json=True)


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class PodDiagnostic:
    name: str
    namespace: str
    status: str
    phase: str
    ready: int
    total: int
    restarts: int
    node: str
    is_failing: bool
    conditions: list = field(default_factory=list)
    events: list = field(default_factory=list)
    images: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    logs: dict = field(default_factory=dict)


# Known service dependency map
SERVICE_DEPENDENCIES = {
    "milvus": ["minio"],
    "mlflow": ["postgresql", "minio"],
    "jupyterhub": ["postgresql"],
    "management-api": [],
    "management-ui": ["management-api"],
    "grafana": ["prometheus"],
    "jaeger": [],
    "victoriametrics": [],
    "otel-collector": [],
}


# =============================================================================
# Diagnostic functions
# =============================================================================

def get_pod_status(pod: dict) -> str:
    """Determine the effective status of a pod."""
    phase = pod.get("status", {}).get("phase", "Unknown")
    status = phase

    # Check init container statuses
    for cs in pod.get("status", {}).get("initContainerStatuses", []):
        waiting = cs.get("state", {}).get("waiting")
        if waiting:
            status = f"Init:{waiting.get('reason', 'Waiting')}"
            return status
        terminated = cs.get("state", {}).get("terminated")
        if terminated and terminated.get("exitCode", 0) != 0:
            status = "Init:Error"
            return status

    # Check container statuses
    for cs in pod.get("status", {}).get("containerStatuses", []):
        waiting = cs.get("state", {}).get("waiting")
        if waiting:
            status = waiting.get("reason", "Waiting")
            return status
        terminated = cs.get("state", {}).get("terminated")
        if terminated:
            reason = terminated.get("reason", "")
            if reason:
                status = reason
                return status

    return status


def analyze_pod(pod: dict) -> PodDiagnostic:
    """Analyze a single pod and produce diagnostics."""
    metadata = pod.get("metadata", {})
    spec = pod.get("spec", {})
    status_obj = pod.get("status", {})

    name = metadata.get("name", "unknown")
    namespace = metadata.get("namespace", "default")
    phase = status_obj.get("phase", "Unknown")
    node = spec.get("nodeName", "unscheduled")

    effective_status = get_pod_status(pod)

    ready = 0
    total = 0
    restarts = 0
    for cs in status_obj.get("containerStatuses", []):
        total += 1
        if cs.get("ready"):
            ready += 1
        restarts += cs.get("restartCount", 0)

    is_failing = effective_status not in ("Running", "Completed", "Succeeded")

    diag = PodDiagnostic(
        name=name,
        namespace=namespace,
        status=effective_status,
        phase=phase,
        ready=ready,
        total=total,
        restarts=restarts,
        node=node,
        is_failing=is_failing,
    )

    # Conditions
    for cond in status_obj.get("conditions", []):
        diag.conditions.append({
            "type": cond.get("type"),
            "status": cond.get("status"),
            "message": cond.get("message", ""),
        })

    # Images
    all_containers = spec.get("initContainers", []) + spec.get("containers", [])
    all_statuses = status_obj.get("initContainerStatuses", []) + status_obj.get("containerStatuses", [])
    status_map = {cs["name"]: cs for cs in all_statuses}

    for container in all_containers:
        img_info = {
            "container": container["name"],
            "image": container.get("image", ""),
            "pullPolicy": container.get("imagePullPolicy", ""),
            "status": "unknown",
        }
        cs = status_map.get(container["name"], {})
        waiting = cs.get("state", {}).get("waiting", {})
        if waiting.get("reason", "").startswith(("ImagePull", "ErrImage")):
            img_info["status"] = f"FAILED: {waiting.get('reason')} - {waiting.get('message', '')}"
        elif cs.get("imageID"):
            img_info["status"] = "pulled"
        diag.images.append(img_info)

    return diag


def get_pod_events(namespace: str, pod_name: str) -> list:
    """Retrieve events for a specific pod."""
    result = kubectl_json(
        f"get events -n {namespace} --field-selector involvedObject.name={pod_name} --sort-by=.lastTimestamp"
    )
    events = []
    if result.get("success") and result.get("data", {}).get("items"):
        for event in result["data"]["items"]:
            events.append({
                "type": event.get("type", ""),
                "reason": event.get("reason", ""),
                "message": event.get("message", ""),
                "count": event.get("count", 1),
                "lastTimestamp": event.get("lastTimestamp", ""),
            })
    return events


def get_pod_logs(namespace: str, pod_name: str, containers: list, tail: int = 50) -> dict:
    """Get current and previous logs for all containers."""
    logs = {}
    for container in containers:
        cname = container["name"]
        # Current logs
        result = kubectl(f"logs -n {namespace} {pod_name} -c {cname} --tail={tail}")
        logs[cname] = {"current": result.get("output", "") if result["success"] else ""}

        # Previous logs
        result = kubectl(f"logs -n {namespace} {pod_name} -c {cname} --tail={tail} --previous")
        if result["success"] and result.get("output"):
            logs[cname]["previous"] = result["output"]

    return logs


def get_pvc_status(namespace: str) -> list:
    """Get PVC status for a namespace."""
    result = kubectl_json(f"get pvc -n {namespace}")
    pvcs = []
    if result.get("success") and result.get("data", {}).get("items"):
        for pvc in result["data"]["items"]:
            pvcs.append({
                "name": pvc["metadata"]["name"],
                "status": pvc.get("status", {}).get("phase", "Unknown"),
                "capacity": (pvc.get("status", {}).get("capacity", {}) or {}).get("storage", "N/A"),
                "storageClass": pvc.get("spec", {}).get("storageClassName", "N/A"),
            })
    return pvcs


def get_node_info() -> list:
    """Get node status and resource info."""
    nodes = []
    result = kubectl_json("get nodes")
    if result.get("success") and result.get("data", {}).get("items"):
        for node in result["data"]["items"]:
            name = node["metadata"]["name"]
            arch = node.get("status", {}).get("nodeInfo", {}).get("architecture", "unknown")
            conditions = node.get("status", {}).get("conditions", [])
            ready = any(c["type"] == "Ready" and c["status"] == "True" for c in conditions)
            pressures = [c["type"] for c in conditions if "Pressure" in c["type"] and c["status"] == "True"]
            nodes.append({
                "name": name,
                "arch": arch,
                "ready": ready,
                "pressures": pressures,
            })
    return nodes


def check_dependencies(namespace: str, pod_name: str) -> list:
    """Check if dependencies for a service are running."""
    issues = []
    # Match pod name to known service
    for service, deps in SERVICE_DEPENDENCIES.items():
        if service in pod_name.lower():
            for dep in deps:
                # Check if dependency pods are running
                result = kubectl_json(f"get pods -A -l app={dep}")
                if not result.get("success") or not result.get("data", {}).get("items"):
                    # Try broader search
                    result = kubectl(f"get pods -A", parse_json=False)
                    if dep not in result.get("output", ""):
                        issues.append(f"Dependency '{dep}' does not appear to be running")
                    else:
                        # Check if it's actually running
                        lines = result.get("output", "").split("\n")
                        for line in lines:
                            if dep in line.lower() and "Running" not in line:
                                issues.append(f"Dependency '{dep}' is not in Running state")
                else:
                    for item in result["data"]["items"]:
                        dep_status = get_pod_status(item)
                        if dep_status not in ("Running", "Completed", "Succeeded"):
                            dep_name = item["metadata"]["name"]
                            issues.append(
                                f"Dependency '{dep}' pod '{dep_name}' is in state: {dep_status}"
                            )
            break
    return issues


def generate_recommendations(diag: PodDiagnostic, pod: dict, nodes: list) -> list:
    """Generate actionable recommendations based on pod state."""
    recs = []

    status = diag.status

    if "ImagePull" in status or "ErrImage" in status:
        recs.append("Image pull failed. Check if the image exists and is accessible.")
        for img in diag.images:
            if img["pullPolicy"] == "IfNotPresent" and (
                img["image"].endswith(":latest") or ":" not in img["image"]
            ):
                recs.append(
                    f"Image '{img['image']}' uses IfNotPresent policy -- "
                    f"it must be pre-built and imported into k3s containerd."
                )
                recs.append(
                    f"Build: docker build -t {img['image']} . && "
                    f"docker save {img['image']} | sudo k3s ctr images import -"
                )

    elif status == "CrashLoopBackOff":
        recs.append(
            f"Container is crash-looping. Check logs: "
            f"kubectl logs -n {diag.namespace} {diag.name} --previous"
        )
        if diag.restarts > 10:
            recs.append(
                f"High restart count ({diag.restarts}). "
                f"The application likely has a fatal startup error."
            )

    elif "Init:Error" in status or "Init:" in status:
        recs.append("Init container failed. Check init container logs.")
        recs.append("Common causes: port conflicts, missing dependencies, permission issues.")

    elif status == "Pending":
        recs.append("Pod is Pending. Common causes:")
        recs.append("  - Insufficient node resources (CPU/memory)")
        recs.append("  - PVC not bound (storage class or capacity issue)")
        recs.append("  - Node selector/affinity mismatch")
        recs.append("  - Taints preventing scheduling")
        for cond in diag.conditions:
            if cond["type"] == "PodScheduled" and cond["status"] == "False":
                recs.append(f"Scheduler message: {cond['message']}")

    elif "OOMKilled" in status:
        recs.append("Container was OOM-killed. Increase memory limits in the deployment.")

    # Architecture check
    node_arch_map = {n["name"]: n["arch"] for n in nodes}
    if diag.node in node_arch_map:
        node_arch = node_arch_map[diag.node]
        for img in diag.images:
            if "milvus" in img["image"].lower() and node_arch == "arm64":
                recs.append(
                    "Milvus does NOT support ARM64. "
                    "Add nodeSelector 'kubernetes.io/arch: amd64' to schedule on the control plane."
                )

    # Dependency checks
    dep_issues = check_dependencies(diag.namespace, diag.name)
    recs.extend(dep_issues)

    return recs


# =============================================================================
# Output functions
# =============================================================================

def print_pod_status(diag: PodDiagnostic):
    """Print a single pod status line."""
    status_colors = {
        "Running": Color.GREEN,
        "Completed": Color.GRAY,
        "Succeeded": Color.GREEN,
        "Pending": Color.YELLOW,
    }
    color = Color.RED if diag.is_failing else status_colors.get(diag.status, Color.YELLOW)
    line = (
        f"  {diag.namespace}/{diag.name:<45} "
        f"{diag.status:<20} "
        f"{diag.ready}/{diag.total}  "
        f"Restarts: {diag.restarts}  "
        f"Node: {diag.node}"
    )
    cprint(line, color)


def print_detailed(diag: PodDiagnostic):
    """Print detailed diagnostics for a pod."""
    header(f"{diag.namespace}/{diag.name} -- {diag.status}")

    # Conditions
    subheader("Conditions")
    for cond in diag.conditions:
        icon = "[OK]  " if cond["status"] == "True" else "[FAIL]"
        color = Color.GREEN if cond["status"] == "True" else Color.RED
        msg = f" -- {cond['message']}" if cond["message"] else ""
        cprint(f"  {icon} {cond['type']}: {cond['status']}{msg}", color)

    # Images
    subheader("Image Pull Status")
    for img in diag.images:
        color = Color.GREEN if img["status"] == "pulled" else Color.RED if "FAILED" in img["status"] else Color.WHITE
        cprint(f"  Container: {img['container']}", color)
        cprint(f"    Image:       {img['image']}", color)
        cprint(f"    PullPolicy:  {img['pullPolicy']}", color)
        cprint(f"    Status:      {img['status']}", color)

    # Events
    subheader("Events")
    if diag.events:
        for event in diag.events:
            color = Color.YELLOW if event["type"] == "Warning" else Color.WHITE
            cprint(
                f"  [{event['type']}] {event['reason']} (x{event['count']}): {event['message']}",
                color,
            )
    else:
        info("No events found")

    # Logs
    if diag.logs:
        for container_name, log_data in diag.logs.items():
            if log_data.get("current"):
                subheader(f"Logs: {container_name} (current)")
                for line in log_data["current"].split("\n")[-30:]:
                    cprint(f"    {line}", Color.WHITE)
            if log_data.get("previous"):
                subheader(f"Logs: {container_name} (previous crash)")
                for line in log_data["previous"].split("\n")[-30:]:
                    cprint(f"    {line}", Color.GRAY)

    # Recommendations
    if diag.recommendations:
        subheader("Recommendations")
        for rec in diag.recommendations:
            recommend(rec)


def print_json_output(diagnostics: list, nodes: list, pvcs: dict):
    """Output all diagnostics as JSON."""
    output = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "nodes": nodes,
        "pvcs": pvcs,
        "pods": [asdict(d) for d in diagnostics],
        "summary": {
            "total": len(diagnostics),
            "running": sum(1 for d in diagnostics if not d.is_failing),
            "failing": sum(1 for d in diagnostics if d.is_failing),
        },
    }
    print(json.dumps(output, indent=2, default=str))


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Pod Debugging and Diagnostics Tool for RPi Kubernetes Cluster"
    )
    parser.add_argument("-n", "--namespace", default="", help="Namespace to inspect")
    parser.add_argument("-p", "--pod", default="", help="Specific pod name")
    parser.add_argument("-l", "--label", default="", help="Label selector")
    parser.add_argument("--failing-only", action="store_true", help="Only show failing pods")
    parser.add_argument("--logs", action="store_true", help="Include container logs")
    parser.add_argument("--tail", type=int, default=50, help="Number of log lines (default: 50)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--kubeconfig", default="", help="Path to kubeconfig file")

    args = parser.parse_args()

    global KUBECONFIG
    if args.kubeconfig:
        KUBECONFIG = args.kubeconfig

    # Verify connectivity
    if not args.json_output:
        header("Pod Debugging and Diagnostics Tool v1.0.0")
    check = kubectl("cluster-info")
    if not check["success"]:
        if args.json_output:
            print(json.dumps({"error": "Cannot connect to Kubernetes cluster"}))
        else:
            fail("Cannot connect to Kubernetes cluster. Check your kubeconfig.")
        sys.exit(1)
    if not args.json_output:
        ok("Connected to cluster")

    # Get pods
    cmd = "get pods"
    if args.namespace:
        cmd += f" -n {args.namespace}"
    else:
        cmd += " -A"
    if args.pod:
        cmd += f" {args.pod}"
    if args.label:
        cmd += f" -l {args.label}"

    result = kubectl_json(cmd)
    if not result.get("success") or not result.get("data", {}).get("items"):
        if args.json_output:
            print(json.dumps({"error": "No pods found", "pods": []}))
        else:
            fail("No pods found matching the criteria")
        sys.exit(1)

    pods = result["data"]["items"]
    nodes = get_node_info()

    if not args.json_output:
        info(f"Found {len(pods)} pod(s)")
        header("Pod Status Overview")

    # Analyze all pods
    diagnostics = []
    for pod in pods:
        diag = analyze_pod(pod)
        diagnostics.append(diag)
        if not args.json_output:
            print_pod_status(diag)

    # Gather detailed info for failing pods
    failing = [d for d in diagnostics if d.is_failing]

    pods_to_inspect = failing if args.failing_only or not args.pod else [d for d in diagnostics if d.is_failing]

    # Enrich with events, logs, recommendations
    pod_map = {(p["metadata"]["namespace"], p["metadata"]["name"]): p for p in pods}
    pvcs_by_ns = {}

    for diag in pods_to_inspect:
        diag.events = get_pod_events(diag.namespace, diag.name)

        if args.logs or diag.is_failing:
            pod_data = pod_map.get((diag.namespace, diag.name), {})
            all_containers = pod_data.get("spec", {}).get("initContainers", []) + \
                             pod_data.get("spec", {}).get("containers", [])
            diag.logs = get_pod_logs(diag.namespace, diag.name, all_containers, args.tail)

        pod_data = pod_map.get((diag.namespace, diag.name), {})
        diag.recommendations = generate_recommendations(diag, pod_data, nodes)

        # PVC status
        if diag.namespace not in pvcs_by_ns:
            pvcs_by_ns[diag.namespace] = get_pvc_status(diag.namespace)

    # Output
    if args.json_output:
        print_json_output(diagnostics, nodes, pvcs_by_ns)
    else:
        # Summary line
        running_count = sum(1 for d in diagnostics if not d.is_failing)
        failing_count = len(failing)
        print()
        info(f"Running: {running_count} | Failing: {failing_count} | Total: {len(diagnostics)}")

        # Detailed diagnostics
        if pods_to_inspect:
            header("Detailed Diagnostics for Failing Pods")
            for diag in pods_to_inspect:
                print_detailed(diag)

                # Show PVCs for this namespace
                if diag.namespace in pvcs_by_ns and pvcs_by_ns[diag.namespace]:
                    subheader(f"PVCs in namespace: {diag.namespace}")
                    for pvc in pvcs_by_ns[diag.namespace]:
                        color = Color.GREEN if pvc["status"] == "Bound" else Color.RED
                        cprint(
                            f"  {pvc['name']:<35} {pvc['status']:<10} "
                            f"{pvc['capacity']:<10} StorageClass: {pvc['storageClass']}",
                            color,
                        )

        # Node info
        subheader("Node Status")
        for node in nodes:
            color = Color.GREEN if node["ready"] else Color.RED
            pressure_str = f"  PRESSURE: {', '.join(node['pressures'])}" if node["pressures"] else ""
            cprint(f"  {node['name']:<35} arch={node['arch']:<8} {'Ready' if node['ready'] else 'NotReady'}{pressure_str}", color)

        # Final summary
        header("Diagnostics Summary")
        if failing_count == 0:
            ok("All pods are healthy!")
        else:
            fail(f"{failing_count} pod(s) need attention")
            from collections import Counter
            by_status = Counter(d.status for d in failing)
            for status, count in by_status.items():
                warn(f"{count} pod(s) in state: {status}")
                for d in failing:
                    if d.status == status:
                        info(f"  - {d.namespace}/{d.name}")
        print()


if __name__ == "__main__":
    main()
