import { http, HttpResponse } from "msw";
import { CANDIDATES_DATA_FIXTURE } from "../fixtures/candidates.fixture";

export const retrievalHandlers = [
  http.get("*/retrieval/compare", ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get("query") || "Transactional Outbox postgres failure";
    const k = Number(url.searchParams.get("k") || 60);
    const vectorCutoff = Number(url.searchParams.get("vector_cutoff") || 0.75);
    const crossEncoderCutoff = Number(url.searchParams.get("cross_encoder_cutoff") || 0.85);

    const candidates = CANDIDATES_DATA_FIXTURE.map((c) => {
      const passesVector = c.vector_score >= vectorCutoff;
      const passesReranker = c.cross_encoder_score >= crossEncoderCutoff;
      return {
        ...c,
        included: passesVector && passesReranker,
      };
    });

    return HttpResponse.json({
      query,
      rrf_k: k,
      vector_cutoff: vectorCutoff,
      cross_encoder_cutoff: crossEncoderCutoff,
      candidates,
      total_candidates: candidates.length,
    });
  }),
];
