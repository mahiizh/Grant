import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);

export async function enableMocking() {
  // Mocking is opt-in. The default must be the live API so a production or
  // local build never silently serves fixture data.
  if (import.meta.env.VITE_API_MODE !== "mock") {
    return;
  }

  return worker.start({
    onUnhandledFrame: "bypass",
  });
}
