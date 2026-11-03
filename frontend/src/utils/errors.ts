import type { ApiError } from "../types/api";

export function getErrorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "message" in error) {
    return String((error as ApiError).message);
  }
  return "Something went wrong. Please try again.";
}
