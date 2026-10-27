import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

/** Settings shared with the local Python TTS service. */
export interface ReaderConfig {
  host: string;
  port: number;
  model: string;
  backend: "mlx" | "cpu" | "auto";
  weights: "packed" | "emb4";
  device: string;
  voice: string;
  autoRead: boolean;
  muted: boolean;
  includeSubagents: boolean;
  maxWords: number;
  documentHeadings: number;
  documentWords: number;
  markdownFileWords: number;
  announceCode: boolean;
  announceSkipped: boolean;
  askMarkdown: "toast" | "dialog" | "none";
  maxQueue: number;
  chunkMaxChars: number;
  messageDedupeTtlS: number;
  textDedupeTtlS: number;
}

/** Defaults mirroring the Python service's `Config` dataclass. */
export const DEFAULT_CONFIG: ReaderConfig = {
  host: "127.0.0.1",
  port: 8765,
  model: "KittenML/kitten-tts-2",
  backend: "mlx",
  weights: "packed",
  device: "mps",
  voice: "Bella",
  autoRead: true,
  muted: false,
  includeSubagents: false,
  maxWords: 1500,
  documentHeadings: 2,
  documentWords: 400,
  markdownFileWords: 200,
  announceCode: false,
  announceSkipped: false,
  askMarkdown: "toast",
  maxQueue: 100,
  chunkMaxChars: 260,
  messageDedupeTtlS: 3600,
  textDedupeTtlS: 300,
};

/** Explicit camelCase to snake_case mapping for every config field. */
const SNAKE_CASE_KEYS: Readonly<Record<keyof ReaderConfig, string>> = {
  host: "host",
  port: "port",
  model: "model",
  backend: "backend",
  weights: "weights",
  device: "device",
  voice: "voice",
  autoRead: "auto_read",
  muted: "muted",
  includeSubagents: "include_subagents",
  maxWords: "max_words",
  documentHeadings: "document_headings",
  documentWords: "document_words",
  markdownFileWords: "markdown_file_words",
  announceCode: "announce_code",
  announceSkipped: "announce_skipped",
  askMarkdown: "ask_markdown",
  maxQueue: "max_queue",
  chunkMaxChars: "chunk_max_chars",
  messageDedupeTtlS: "message_dedupe_ttl_s",
  textDedupeTtlS: "text_dedupe_ttl_s",
};

const SNAKE_TO_CAMEL: Readonly<Record<string, keyof ReaderConfig>> =
  Object.fromEntries(
    Object.entries(SNAKE_CASE_KEYS).map(([camel, snake]) => [snake, camel]),
  ) as Record<string, keyof ReaderConfig>;

const ENUM_VALUES: Partial<Record<keyof ReaderConfig, readonly string[]>> = {
  backend: ["mlx", "cpu", "auto"],
  weights: ["packed", "emb4"],
  askMarkdown: ["toast", "dialog", "none"],
};

function xdgPath(envVar: string, fallback: readonly string[]): string {
  const value = process.env[envVar];
  if (value) return value;
  return join(homedir(), ...fallback);
}

/** Return the location of the reader configuration file. */
export function configPath(): string {
  return join(
    xdgPath("XDG_CONFIG_HOME", [".config"]),
    "opencode",
    "tts-reader.json",
  );
}

/**
 * Load configuration, merging a partial JSON file over the defaults.
 * Missing, unreadable, or malformed files yield the defaults.
 */
export function loadReaderConfig(path: string = configPath()): ReaderConfig {
  let data: unknown;
  try {
    data = JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return { ...DEFAULT_CONFIG };
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return { ...DEFAULT_CONFIG };
  }

  const config: ReaderConfig = { ...DEFAULT_CONFIG };
  for (const [key, value] of Object.entries(data)) {
    const camel = SNAKE_TO_CAMEL[key];
    if (!camel) continue;
    const expected = typeof DEFAULT_CONFIG[camel];
    if (typeof value !== expected) continue;
    const allowed = ENUM_VALUES[camel];
    if (allowed && !allowed.includes(value as string)) continue;
    if (typeof value === "number" && !Number.isFinite(value)) continue;
    (config as unknown as Record<string, unknown>)[camel] = value;
  }
  return config;
}

/** Convert a camelCase config patch to the service's snake_case keys. */
export function toSnakeCaseConfig(
  patch: Partial<ReaderConfig>,
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const [camel, value] of Object.entries(patch)) {
    const snake = SNAKE_CASE_KEYS[camel as keyof ReaderConfig];
    if (snake !== undefined && value !== undefined) body[snake] = value;
  }
  return body;
}
