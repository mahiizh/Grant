import { http, HttpResponse } from "msw";
import { INITIAL_SETTINGS_FIXTURE } from "../fixtures/settings.fixture";
import { INITIAL_OVERVIEW_METRICS, INITIAL_GUARDRAILS_METRICS } from "../fixtures/metrics.fixture";

let settings = { ...INITIAL_SETTINGS_FIXTURE };

export function resetSettingsMock() {
  settings = { ...INITIAL_SETTINGS_FIXTURE };
}

export const settingsHandlers = [
  http.get("*/settings", () => {
    return HttpResponse.json(settings);
  }),

  http.patch("*/settings", async ({ request }) => {
    const body: any = await request.json();
    if (body.default_scope) settings.default_scope = body.default_scope;
    if (body.default_as_of_date) settings.default_as_of_date = body.default_as_of_date;
    if (body.canvas_theme) settings.canvas_theme = body.canvas_theme;
    return HttpResponse.json(settings);
  }),

  http.get("*/health", () => {
    return HttpResponse.json({
      status: "ok",
      version: "0.2.0",
      environment: "development",
      components: {
        postgres: { status: "healthy", latency_ms: 1.1 },
        qdrant: { status: "healthy", latency_ms: 2.2 },
        neo4j: { status: "healthy", latency_ms: 2.9 },
        redis: { status: "healthy", latency_ms: 0.7 },
        outbox: { status: "healthy", latency_ms: 0.0 },
      },
      outbox_lag: 0,
    });
  }),

  http.get("*/health/ready", () => {
    return HttpResponse.json({
      status: "ok",
      version: "0.2.0",
      environment: "development",
      configured_stores: {
        postgres: true,
        qdrant: true,
        neo4j: true,
        redis: true,
      },
    });
  }),

  http.get("*/health/live", () => {
    return HttpResponse.json({ status: "ok" });
  }),

  http.get("*/metrics/overview", () => {
    return HttpResponse.json(INITIAL_OVERVIEW_METRICS);
  }),

  http.get("*/metrics/guardrails", () => {
    return HttpResponse.json(INITIAL_GUARDRAILS_METRICS);
  }),
];
