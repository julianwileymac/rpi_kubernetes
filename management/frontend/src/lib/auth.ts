/**
 * Minimal Auth0 wrapper for the rpi_kubernetes management UI.
 *
 * Mirrors :file:`agentic_quant_platform/frontend/src/lib/auth/useAuth.ts`
 * so an operator can carry the same mental model between the AQP UI
 * and the cluster control panel.
 *
 * Phase 8 of the multi-tenant rollout adds Auth0 to the management
 * frontend. The actual JWT validation happens on the backend
 * (:func:`management.backend.src.auth.require_authenticated_mgmt`);
 * the frontend just acquires + attaches the Bearer token via
 * ``@auth0/auth0-react``.
 *
 * When ``NEXT_PUBLIC_AUTH0_DOMAIN`` is unset the helper falls into
 * "local mode" — no IdP, every call passes the matching backend
 * (which also degrades to ``auth_provider=none``).
 */
export interface MgmtAuthConfig {
  domain: string;
  clientId: string;
  audience: string;
  redirectUri: string;
}

export function loadMgmtAuthConfig(): MgmtAuthConfig | null {
  const domain = process.env.NEXT_PUBLIC_AUTH0_DOMAIN || "";
  const clientId = process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID || "";
  const audience = process.env.NEXT_PUBLIC_AUTH0_AUDIENCE || "";
  if (!domain || !clientId || !audience) {
    return null;
  }
  return {
    domain,
    clientId,
    audience,
    redirectUri:
      typeof window !== "undefined"
        ? `${window.location.origin}/auth/callback`
        : "",
  };
}

export function isMgmtAuthEnabled(): boolean {
  return loadMgmtAuthConfig() !== null;
}
