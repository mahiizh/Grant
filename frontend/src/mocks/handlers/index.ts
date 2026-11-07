import { graphHandlers } from "./graph.handlers";
import { documentsHandlers } from "./documents.handlers";
import { queryHandlers } from "./query.handlers";
import { tracesHandlers } from "./traces.handlers";
import { retrievalHandlers } from "./retrieval.handlers";
import { cacheHandlers } from "./cache.handlers";
import { evalsHandlers } from "./evals.handlers";
import { experimentsHandlers } from "./experiments.handlers";
import { settingsHandlers } from "./settings.handlers";
import { threadsHandlers } from "./threads.handlers";

export const handlers = [
  ...graphHandlers,
  ...documentsHandlers,
  ...queryHandlers,
  ...tracesHandlers,
  ...retrievalHandlers,
  ...cacheHandlers,
  ...evalsHandlers,
  ...experimentsHandlers,
  ...settingsHandlers,
  ...threadsHandlers,
];
