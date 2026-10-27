/** Visible prose emitted by the assistant. */
export interface TextContent {
  type: "text";
  text: string;
}

/** Model reasoning; never spoken. */
export interface ReasoningContent {
  type: "reasoning";
  text: string;
}

/** A tool call and its current state. */
export interface ToolContent {
  type: "tool";
  name: string;
  state?: { status?: string; input?: unknown };
}

export type Content = TextContent | ReasoningContent | ToolContent;

/** Minimal shape of an OpenCode session message. */
export interface MessageItem {
  id: string;
  type: string;
  content?: readonly Content[];
}

/** Final prose of one turn plus the signals used to classify it. */
export interface Extraction {
  text: string;
  messageID: string;
  turnHasMarkdownFile: boolean;
  containsReaderTool: boolean;
}

/** Request body for the local TTS service's speak endpoint. */
export interface SpeakInput {
  text: string;
  sessionID: string;
  messageID: string;
  source?: "auto" | "manual" | "notice";
  turnHasMarkdownFile?: boolean;
  force?: boolean;
  voice?: string;
}

/** Normalized outcome of a speak request. */
export interface SpeakResult {
  action:
    | "queued"
    | "pending"
    | "muted"
    | "duplicate"
    | "empty"
    | "queue_full";
  reason?: "markdown" | "long" | null;
  words: number;
  jobId?: string | null;
}

/** Response body of the local TTS service's health endpoint. */
export interface Health {
  ok: boolean;
  loading?: boolean;
  load_error?: string | null;
  model?: string;
  backend?: string;
  voice?: string;
  muted?: boolean;
  auto_read?: boolean;
  queue_depth?: number;
  speaking?: boolean;
  pending_count?: number;
}

/** A held reply awaiting an explicit speak request. */
export interface PendingItem {
  session_id: string;
  message_id: string;
  reason: "markdown" | "long";
  words: number;
  created_at: number;
}
