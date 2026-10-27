import { describe, expect, test } from "bun:test";
import { extractFinalAnswer } from "../src/extract";
import type { MessageItem } from "../src/types";

const user = (id = "u1"): MessageItem => ({ id, type: "user" });
const assistant = (
  id: string,
  content: MessageItem["content"],
): MessageItem => ({
  id,
  type: "assistant",
  content,
});
const text = (value: string) => ({ type: "text" as const, text: value });
const tool = (name: string, input: unknown = {}) => ({
  type: "tool" as const,
  name,
  state: { status: "completed", input },
});

describe("extractFinalAnswer", () => {
  test("uses text after the last tool call", () => {
    const messages = [
      user(),
      assistant("a1", [
        text("I'll check."),
        tool("bash"),
        text("The answer is 42."),
      ]),
    ];
    expect(extractFinalAnswer(messages)).toEqual({
      text: "The answer is 42.",
      messageID: "a1",
      turnHasMarkdownFile: false,
      containsReaderTool: false,
    });
  });

  test("ignores preamble in an earlier assistant message", () => {
    const messages = [
      user(),
      assistant("a1", [text("I'll check."), tool("bash")]),
      assistant("a2", [text("Final answer.")]),
    ];
    expect(extractFinalAnswer(messages)?.text).toBe("Final answer.");
  });

  test("uses the last assistant message that has text", () => {
    const messages = [
      user(),
      assistant("a1", [text("First final.")]),
      assistant("a2", [tool("bash")]),
    ];
    expect(extractFinalAnswer(messages)?.text).toBe("First final.");
  });

  test("ignores reasoning", () => {
    const messages = [
      user(),
      assistant("a1", [
        { type: "reasoning", text: "secret thinking" },
        text("Visible answer."),
      ]),
    ];
    expect(extractFinalAnswer(messages)?.text).toBe("Visible answer.");
  });

  test("detects a markdown file tool anywhere in the turn", () => {
    const messages = [
      user(),
      assistant("a1", [
        tool("read", { filePath: "/tmp/PLAN.md" }),
        text("Summary."),
      ]),
    ];
    expect(extractFinalAnswer(messages)?.turnHasMarkdownFile).toBe(true);
  });

  test("detects a reader_speak tool anywhere in the turn", () => {
    const messages = [
      user(),
      assistant("a1", [tool("reader_speak"), text("Done.")]),
    ];
    const result = extractFinalAnswer(messages);
    expect(result?.containsReaderTool).toBe(true);
    expect(result?.text).toBe("Done.");
  });

  test("returns null without a user message", () => {
    expect(extractFinalAnswer([assistant("a1", [text("Hello.")])])).toBeNull();
  });

  test("returns null for a tool-only assistant message", () => {
    expect(
      extractFinalAnswer([user(), assistant("a1", [tool("bash")])]),
    ).toBeNull();
  });

  test("only looks at the last turn", () => {
    const messages = [
      user("u1"),
      assistant("a1", [text("Old answer.")]),
      user("u2"),
      assistant("a2", [text("New answer.")]),
    ];
    expect(extractFinalAnswer(messages)?.text).toBe("New answer.");
  });
});
