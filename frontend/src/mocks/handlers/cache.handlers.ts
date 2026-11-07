import { http, HttpResponse } from "msw";
import { CACHE_SERIES_FIXTURE, INITIAL_INVALIDATIONS_FIXTURE, CacheInvalidationFixture } from "../fixtures/cache.fixture";

let invalidations: CacheInvalidationFixture[] = [...INITIAL_INVALIDATIONS_FIXTURE];

export function resetCacheMock() {
  invalidations = [...INITIAL_INVALIDATIONS_FIXTURE];
}

export function addCacheInvalidation(inv: CacheInvalidationFixture) {
  invalidations.unshift(inv);
}

export const cacheHandlers = [
  http.get("*/cache/stats", ({ request }) => {
    const url = new URL(request.url);
    const window = url.searchParams.get("window") || "24h";

    const totalRequests = CACHE_SERIES_FIXTURE.reduce((acc, p) => acc + p.hits + p.misses, 0);
    const totalHits = CACHE_SERIES_FIXTURE.reduce((acc, p) => acc + p.hits, 0);
    const totalWrongHits = CACHE_SERIES_FIXTURE.reduce((acc, p) => acc + p.wrong_hits, 0);

    return HttpResponse.json({
      window,
      total_requests: totalRequests,
      overall_hit_rate: totalHits / (totalRequests || 1),
      wrong_hit_rate: totalWrongHits / (totalRequests || 1),
      p95_savings_ms: 412.5,
      series: CACHE_SERIES_FIXTURE,
    });
  }),

  http.get("*/cache/invalidations", () => {
    return HttpResponse.json({
      invalidations,
      total: invalidations.length,
    });
  }),
];
