import { http, HttpResponse } from "msw";
import { GOLDEN_SET_FIXTURE, GoldenPairFixture } from "../fixtures/evals.fixture";

let goldenSet: GoldenPairFixture[] = [...GOLDEN_SET_FIXTURE];

export function resetGoldenSetMock() {
  goldenSet = [...GOLDEN_SET_FIXTURE];
}

export const evalsHandlers = [
  http.get("*/evals/golden/dataset", () => {
    return HttpResponse.json({
      questions: goldenSet,
      total: goldenSet.length,
    });
  }),

  http.post("*/evals/golden/dataset", async ({ request }) => {
    const body: any = await request.json();
    const newPair: GoldenPairFixture = {
      id: `eval-${Date.now()}`,
      question: body.question,
      category: body.category || "fact-lookup",
      expected_route: body.expected_route || "hybrid_search",
      expected_answer: body.expected_answer || "",
      ground_truth_entities: body.ground_truth_entities || [],
      ground_truth_chunk_ids: body.ground_truth_chunk_ids || [],
      complexity: body.complexity || "medium",
      lastAccuracy: "pass",
      faithfulness: 0.95,
      latencyMs: 340,
    };

    goldenSet.unshift(newPair);

    return HttpResponse.json(newPair);
  }),

  http.post("*/evals/golden", async () => {
    return HttpResponse.json({
      run_id: `run-${Date.now()}`,
      status: "completed",
      total_questions: goldenSet.length,
      accuracy: 0.942,
      started_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
    });
  }),
];
