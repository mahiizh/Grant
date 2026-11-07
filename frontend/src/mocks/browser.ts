import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);

export async function enableMocking() {
  const mode = import.meta.env.VITE_API_MODE ?? "mock";
  if (mode !== "mock") {
    return;
  }

  return worker.start({
    onUnhandledFrame: "bypass",
  });
}
