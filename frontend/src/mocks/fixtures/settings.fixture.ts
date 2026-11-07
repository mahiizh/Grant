export interface SettingsFixture {
  acl_scopes: string[];
  default_scope: string;
  default_as_of_date: string;
  canvas_theme: "dark" | "match";
  stores: Record<string, { status: "healthy" | "degraded" | "down"; latency_ms: number; configured: boolean }>;
}

export const INITIAL_SETTINGS_FIXTURE: SettingsFixture = {
  acl_scopes: ["public", "data-platform", "security-admin", "executive-audit"],
  default_scope: "data-platform",
  default_as_of_date: "2026-04-12",
  canvas_theme: "dark",
  stores: {
    postgres: { status: "healthy", latency_ms: 1.2, configured: true },
    qdrant: { status: "healthy", latency_ms: 2.4, configured: true },
    neo4j: { status: "healthy", latency_ms: 3.1, configured: true },
    redis: { status: "healthy", latency_ms: 0.8, configured: true },
  },
};
