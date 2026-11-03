import { getErrorMessage } from "./errors";

/** Map safe V2 receipt-lookup API failures to operator-facing guidance. */
export function getV2LookupErrorMessage(cause: unknown): string {
  if (typeof cause === "object" && cause !== null && "status" in cause) {
    const status = (cause as { status: unknown }).status;
    if (status === 403) {
      return "Receipt Viewer access is required for V2 receipt lookup.";
    }
    if (status === 401) {
      return "Your session is unavailable or expired. Sign in to continue.";
    }
    if (status === 404) {
      return "The active backend does not expose the V2 receipt endpoint yet. It may require an approved backend-only restart.";
    }
  }
  return getErrorMessage(cause);
}
