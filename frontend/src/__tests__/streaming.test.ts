import { afterEach, describe, expect, it, vi } from "vitest";
import { streamSendMessage } from "../lib/api/hooks/useThreads";

function mockStream(chunks: string[]) {
  const encoder = new TextEncoder();
  let index = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (index < chunks.length) {
              return { done: false, value: encoder.encode(chunks[index++]) };
            }
            return { done: true, value: undefined };
          },
        }),
      },
    }))
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamSendMessage", () => {
  it("forwards live tokens and time-to-first-token from SSE events", async () => {
    mockStream([
      'event: token\ndata: {"token":"Alpha "}\n\n',
      'event: token\ndata: {"token":"beta"}\n\n',
      'event: done\ndata: {"message_id":"msg-1","role":"assistant","content":"Alpha beta","ttft_ms":42.5}\n\n',
    ]);

    const tokens: string[] = [];
    let ttft = 0;
    let doneContent = "";
    await streamSendMessage(
      "thread-1",
      { content: "question" },
      {
        onToken: (token) => tokens.push(token),
        onTtft: (ms) => {
          ttft = ms;
        },
        onDone: (message) => {
          doneContent = message.content;
        },
      }
    );

    expect(tokens).toEqual(["Alpha ", "beta"]);
    expect(ttft).toBe(42.5);
    expect(doneContent).toBe("Alpha beta");
  });

  it("surfaces backend SSE error events", async () => {
    mockStream(['event: error\ndata: {"detail":"Ask budget exceeded"}\n\n']);

    const onError = vi.fn();
    await streamSendMessage("thread-1", { content: "question" }, { onError });

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0].message).toBe("Ask budget exceeded");
  });
});
