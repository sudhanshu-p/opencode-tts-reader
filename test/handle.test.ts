import { describe, expect, test } from "bun:test";
import { DEFAULT_CONFIG } from "../src/config";
import { handleSessionIdle } from "../src/handle";
import type { SpeakInput, SpeakResult } from "../src/types";

const messages = [
  { id: "u1", type: "user" },
  {
    id: "a1",
    type: "assistant",
    content: [
      { type: "text" as const, text: "I'll check." },
      {
        type: "tool" as const,
        name: "bash",
        state: { status: "completed", input: {} },
      },
      { type: "text" as const, text: "Final answer." },
    ],
  },
];

function deps(config = DEFAULT_CONFIG) {
  const spoken: SpeakInput[] = [];
  return {
    spoken,
    deps: {
      config,
      speak: async (input: SpeakInput): Promise<SpeakResult> => {
        spoken.push(input);
        return { action: "queued", words: 2, jobId: "j1" };
      },
    },
  };
}

describe("handleSessionIdle", () => {
  test("skips child sessions by default", async () => {
    const { spoken, deps: d } = deps();
    const result = await handleSessionIdle(
      { sessionID: "s1", session: { id: "s1", parentID: "parent" }, messages },
      d,
    );
    expect(result).toEqual({ action: "skipped", reason: "subagent" });
    expect(spoken).toEqual([]);
  });

  test("posts the final prose for a top-level session", async () => {
    const { spoken, deps: d } = deps();
    const result = await handleSessionIdle(
      { sessionID: "s1", session: { id: "s1" }, messages },
      d,
    );
    expect(result.action).toBe("queued");
    expect(spoken).toEqual([
      {
        text: "Final answer.",
        sessionID: "s1",
        messageID: "a1",
        source: "auto",
        turnHasMarkdownFile: false,
      },
    ]);
  });

  test("skips a turn that already called reader_speak", async () => {
    const { spoken, deps: d } = deps();
    const result = await handleSessionIdle(
      {
        sessionID: "s1",
        session: { id: "s1" },
        messages: [
          { id: "u1", type: "user" },
          {
            id: "a1",
            type: "assistant",
            content: [
              {
                type: "tool",
                name: "reader_speak",
                state: { status: "completed", input: {} },
              },
              { type: "text", text: "Done." },
            ],
          },
        ],
      },
      d,
    );
    expect(result).toEqual({ action: "skipped", reason: "reader-tool" });
    expect(spoken).toEqual([]);
  });

  test("skips a turn with no visible text", async () => {
    const { spoken, deps: d } = deps();
    const result = await handleSessionIdle(
      {
        sessionID: "s1",
        session: { id: "s1" },
        messages: [
          { id: "u1", type: "user" },
          {
            id: "a1",
            type: "assistant",
            content: [
              {
                type: "tool",
                name: "bash",
                state: { status: "completed", input: {} },
              },
            ],
          },
        ],
      },
      d,
    );
    expect(result).toEqual({ action: "skipped", reason: "no-final-text" });
    expect(spoken).toEqual([]);
  });

  test("passes the markdown-file flag through", async () => {
    const { spoken, deps: d } = deps();
    await handleSessionIdle(
      {
        sessionID: "s1",
        session: { id: "s1" },
        messages: [
          { id: "u1", type: "user" },
          {
            id: "a1",
            type: "assistant",
            content: [
              {
                type: "tool",
                name: "read",
                state: {
                  status: "completed",
                  input: { filePath: "/tmp/PLAN.md" },
                },
              },
              { type: "text", text: "Summary." },
            ],
          },
        ],
      },
      d,
    );
    expect(spoken[0].turnHasMarkdownFile).toBe(true);
  });
});
