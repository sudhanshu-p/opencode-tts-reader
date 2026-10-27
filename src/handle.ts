import type { ReaderConfig } from "./config";
import { extractFinalAnswer } from "./extract";
import type { MessageItem, SpeakInput, SpeakResult } from "./types";

/** One completed turn, as seen by the idle handler. */
export interface HandleInput {
  sessionID: string;
  session: { id?: string; parentID?: string | null };
  messages: readonly MessageItem[];
}

/** Side effects the idle handler needs. */
export interface HandleDeps {
  config: ReaderConfig;
  speak: (input: SpeakInput) => Promise<SpeakResult>;
}

/** Outcome of an idle-handler decision, without the reply text. */
export type HandleResult =
  | {
      action: "skipped";
      reason: "subagent" | "no-final-text" | "reader-tool";
    }
  | {
      action: SpeakResult["action"];
      reason: SpeakResult["reason"];
      words: number;
    };

/**
 * Decide whether a finished turn should be spoken, and ask the service to
 * speak it. Reply text is only ever passed to the service, never logged or
 * returned.
 */
export async function handleSessionIdle(
  input: HandleInput,
  deps: HandleDeps,
): Promise<HandleResult> {
  const { config, speak } = deps;

  if (input.session.parentID && !config.includeSubagents) {
    return { action: "skipped", reason: "subagent" };
  }

  const extraction = extractFinalAnswer(input.messages);
  if (extraction === null) {
    return { action: "skipped", reason: "no-final-text" };
  }

  if (extraction.containsReaderTool) {
    return { action: "skipped", reason: "reader-tool" };
  }

  const result = await speak({
    text: extraction.text,
    sessionID: input.sessionID,
    messageID: extraction.messageID,
    source: "auto",
    turnHasMarkdownFile: extraction.turnHasMarkdownFile,
  });

  return {
    action: result.action,
    reason: result.reason,
    words: result.words,
  };
}
