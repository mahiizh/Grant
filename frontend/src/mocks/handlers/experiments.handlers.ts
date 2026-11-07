import { http, HttpResponse } from "msw";
import { INITIAL_EXPERIMENTS_FIXTURE, ExperimentRunFixture } from "../fixtures/experiments.fixture";

let experiments: ExperimentRunFixture[] = [...INITIAL_EXPERIMENTS_FIXTURE];

export function resetExperimentsMock() {
  experiments = [...INITIAL_EXPERIMENTS_FIXTURE];
}

export const experimentsHandlers = [
  http.get("*/experiments", () => {
    return HttpResponse.json({
      experiments,
      total: experiments.length,
    });
  }),

  http.post("*/experiments", async ({ request }) => {
    const body: any = await request.json();
    const exp = experiments.find((e) => e.id === body.experiment_id) || experiments[0];
    if (exp && typeof body.traffic_split === "number") {
      exp.traffic_split = body.traffic_split;
    }
    return HttpResponse.json(exp);
  }),
];
