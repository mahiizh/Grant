import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export const apiClient = createClient<paths>({
  baseUrl: API_BASE_URL,
});

export function formatApiError(error: unknown, fallback: string): string {
  if (!error) return fallback;
  if (typeof error === "string") return error;
  const err = error as Record<string, unknown>;
  if (typeof err.detail === "string") return err.detail;
  if (Array.isArray(err.detail)) {
    return err.detail
      .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : JSON.stringify(item)))
      .join("; ");
  }
  if (typeof err.message === "string") return err.message;
  return fallback;
}
