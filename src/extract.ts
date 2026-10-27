import type { Content, Extraction, MessageItem, ToolContent } from "./types";

const MARKDOWN_TOOL_NAMES = new Set(["read", "write", "edit", "patch"]);

const PATH_KEYS = ["filePath", "path", "file_path", "filename"] as const;

const MARKDOWN_SUFFIXES = [".md", ".mdx"] as const;

function isMarkdownPath(value: string): boolean {
  const path = value.trim().toLowerCase();
  return MARKDOWN_SUFFIXES.some((suffix) => path.endsWith(suffix));
}

/** True when a tool call targets a markdown document. */
export function isMarkdownTool(content: ToolContent): boolean {
  if (!MARKDOWN_TOOL_NAMES.has(content.name)) return false;

  const input = content.state?.input;
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return false;
  }

  const fields = input as Record<string, unknown>;
  for (const key of PATH_KEYS) {
    const value = fields[key];
    if (typeof value === "string" && isMarkdownPath(value)) return true;
    if (
      Array.isArray(value) &&
      value.some((entry) => typeof entry === "string" && isMarkdownPath(entry))
    ) {
      return true;
    }
  }

  return false;
}

/** True for the reader's own speak tool, including namespaced variants. */
export function isReaderTool(content: ToolContent): boolean {
  return (
    content.name === "reader_speak" || content.name.endsWith("_reader_speak")
  );
}

function collectText(items: readonly Content[]): string {
  const parts: string[] = [];
  for (const item of items) {
    if (item.type !== "text") continue;
    const text = item.text.trim();
    if (text) parts.push(text);
  }
  return parts.join("\n");
}

function lastText(items: readonly Content[]): string | null {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.type !== "text") continue;
    const text = item.text.trim();
    if (text) return text;
  }
  return null;
}

function lastToolIndex(items: readonly Content[]): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (items[index].type === "tool") return index;
  }
  return -1;
}

/**
 * Return only the final prose of the last turn: the text an assistant produced
 * after its last tool call, falling back to earlier messages when needed.
 */
export function extractFinalAnswer(
  messages: readonly MessageItem[],
): Extraction | null {
  let lastUserIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].type === "user") {
      lastUserIndex = index;
      break;
    }
  }
  if (lastUserIndex === -1) return null;

  const turn: MessageItem[] = [];
  for (let index = lastUserIndex + 1; index < messages.length; index += 1) {
    if (messages[index].type === "assistant") turn.push(messages[index]);
  }
  if (turn.length === 0) return null;

  let turnHasMarkdownFile = false;
  let containsReaderTool = false;
  for (const message of turn) {
    for (const item of message.content ?? []) {
      if (item.type !== "tool") continue;
      if (isMarkdownTool(item)) turnHasMarkdownFile = true;
      if (isReaderTool(item)) containsReaderTool = true;
    }
  }

  for (let index = turn.length - 1; index >= 0; index -= 1) {
    const message = turn[index];
    const items = message.content ?? [];
    const toolIndex = lastToolIndex(items);

    let text: string;
    if (toolIndex >= 0) {
      text = collectText(items.slice(toolIndex + 1));
      if (!text) {
        const fallback = lastText(items);
        if (fallback === null) continue;
        text = fallback;
      }
    } else {
      text = collectText(items);
      if (!text) continue;
    }

    return {
      text,
      messageID: message.id,
      turnHasMarkdownFile,
      containsReaderTool,
    };
  }

  return null;
}
