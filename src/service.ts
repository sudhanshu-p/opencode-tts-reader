import { spawn as nodeSpawn, type SpawnOptions } from "node:child_process";
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  realpathSync,
} from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DEFAULT_CONFIG, toSnakeCaseConfig, type ReaderConfig } from "./config";
import type { Health, PendingItem, SpeakInput, SpeakResult } from "./types";

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;
type SpawnLike = (
  command: string,
  args: readonly string[],
  options: SpawnOptions,
) => { unref(): void };

/** Options accepted by {@link TtsService}. */
export interface TtsServiceOptions {
  config?: ReaderConfig;
  baseUrl?: string;
  repoRoot?: string;
  dataDir?: string;
  fetch?: FetchLike;
  spawn?: SpawnLike;
  sleep?: (ms: number) => Promise<void>;
  startTimeoutMs?: number;
  pollMs?: number;
}

interface RawSpeakResponse {
  action: SpeakResult["action"];
  reason?: SpeakResult["reason"];
  words?: number;
  job_id?: string | null;
}

interface RawPendingResponse {
  pending: PendingItem[];
}

interface RawVoicesResponse {
  voices: string[];
}

function defaultDataDir(): string {
  const base = process.env.XDG_DATA_HOME;
  return base
    ? join(base, "opencode-tts")
    : join(homedir(), ".local", "share", "opencode-tts");
}

const defaultSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

/** Client for the local Python TTS service. */
export class TtsService {
  private readonly baseUrl: string;
  private readonly repoRoot: string;
  private readonly dataDir: string;
  private readonly fetchImpl: FetchLike;
  private readonly spawnImpl: SpawnLike;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly startTimeoutMs: number;
  private readonly pollMs: number;
  private started: Promise<void> | null = null;

  constructor(options: TtsServiceOptions = {}) {
    const config = options.config ?? DEFAULT_CONFIG;
    this.baseUrl = options.baseUrl ?? `http://${config.host}:${config.port}`;
    this.repoRoot =
      options.repoRoot ??
      realpathSync(fileURLToPath(new URL("..", import.meta.url)));
    this.dataDir = options.dataDir ?? defaultDataDir();
    this.fetchImpl =
      options.fetch ?? ((input, init) => globalThis.fetch(input, init));
    this.spawnImpl = options.spawn ?? (nodeSpawn as SpawnLike);
    this.sleep = options.sleep ?? defaultSleep;
    this.startTimeoutMs = options.startTimeoutMs ?? 120_000;
    this.pollMs = options.pollMs ?? 500;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(init.headers ?? {}),
      },
      signal: AbortSignal.timeout(5000),
    });
    const body = await response.text();
    if (!response.ok) {
      throw new Error(
        `TTS service ${response.status} ${response.statusText}: ${body}`,
      );
    }
    if (!body) return undefined as T;
    return JSON.parse(body) as T;
  }

  private post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  /** Fetch the service health snapshot. */
  health(): Promise<Health> {
    return this.request<Health>("/health");
  }

  private toSpeakResult(raw: RawSpeakResponse): SpeakResult {
    return {
      action: raw.action,
      reason: raw.reason ?? null,
      words: raw.words ?? 0,
      jobId: raw.job_id ?? null,
    };
  }

  /** Submit prose for speech. */
  async speak(input: SpeakInput): Promise<SpeakResult> {
    const body: Record<string, unknown> = {
      text: input.text,
      session_id: input.sessionID,
      message_id: input.messageID,
      source: input.source ?? "auto",
      turn_has_markdown_file: input.turnHasMarkdownFile ?? false,
      force: input.force ?? false,
    };
    if (input.voice !== undefined) body.voice = input.voice;
    const raw = await this.post<RawSpeakResponse>("/speak", body);
    return this.toSpeakResult(raw);
  }

  /** Speak the reply held for a session, or any session when omitted. */
  async speakPending(sessionID?: string): Promise<SpeakResult> {
    const raw = await this.post<RawSpeakResponse>("/speak-pending", {
      session_id: sessionID ?? null,
    });
    return this.toSpeakResult(raw);
  }

  /** List replies awaiting an explicit speak request. */
  async pending(sessionID?: string): Promise<PendingItem[]> {
    const query =
      sessionID === undefined
        ? ""
        : `?session_id=${encodeURIComponent(sessionID)}`;
    const raw = await this.request<RawPendingResponse>(`/pending${query}`);
    return raw.pending;
  }

  /** Stop speech and clear the queue. */
  async stop(): Promise<void> {
    await this.post<unknown>("/stop");
  }

  /** Mute automatic reading. */
  async mute(): Promise<void> {
    await this.post<unknown>("/mute");
  }

  /** Unmute automatic reading. */
  async unmute(): Promise<void> {
    await this.post<unknown>("/unmute");
  }

  /** List the voices the engine can synthesize. */
  async voices(): Promise<string[]> {
    const raw = await this.request<RawVoicesResponse>("/voices");
    return raw.voices;
  }

  /** Update service settings from a camelCase patch. */
  async patchConfig(patch: Partial<ReaderConfig>): Promise<void> {
    await this.request<unknown>("/config", {
      method: "PATCH",
      body: JSON.stringify(toSnakeCaseConfig(patch)),
    });
  }

  /**
   * Start the local service if it is not already healthy.
   * Concurrent callers share one start attempt.
   */
  ensureStarted(): Promise<void> {
    if (this.started === null) {
      this.started = this.start().finally(() => {
        this.started = null;
      });
    }
    return this.started;
  }

  private async isHealthy(): Promise<boolean> {
    try {
      const health = await this.health();
      return health.ok === true;
    } catch {
      return false;
    }
  }

  private async start(): Promise<void> {
    if (await this.isHealthy()) return;

    const python = join(
      this.repoRoot,
      "python",
      ".venv",
      "bin",
      "python",
    );
    if (!existsSync(python)) {
      throw new Error(
        `TTS service python not found at ${python}. ` +
          "Run `uv sync` in the python directory to install it.",
      );
    }

    mkdirSync(this.dataDir, { recursive: true });
    const logPath = join(this.dataDir, "service.log");
    const fd = openSync(logPath, "a");
    try {
      const child = this.spawnImpl(python, ["-m", "tts_service"], {
        cwd: join(this.repoRoot, "python"),
        detached: true,
        stdio: ["ignore", fd, fd],
      });
      child.unref();
    } finally {
      closeSync(fd);
    }

    const deadline = Date.now() + this.startTimeoutMs;
    while (Date.now() < deadline) {
      await this.sleep(this.pollMs);
      if (await this.isHealthy()) return;
    }
    throw new Error(
      `TTS service did not become healthy within ${this.startTimeoutMs}ms. ` +
        `See ${logPath}.`,
    );
  }
}
