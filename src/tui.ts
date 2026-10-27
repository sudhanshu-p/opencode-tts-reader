import { Plugin } from "@opencode/plugin/tui";
import { loadReaderConfig, type ReaderConfig } from "./config";
import { TtsService } from "./service";
import type { PendingItem } from "./types";

/** Options passed to the TUI toast API. */
export interface PendingToast {
  title: string;
  message: string;
  variant: "info" | "success";
  duration: number;
  sessionID?: string;
}

interface PendingService {
  speakPending(sessionID?: string): Promise<unknown>;
}

interface VoiceService {
  voices(): Promise<string[]>;
  patchConfig(patch: Partial<ReaderConfig>): Promise<void>;
}

interface IdleService extends PendingService {
  ensureStarted(): Promise<void>;
  pending(sessionID?: string): Promise<PendingItem[]>;
  voices(): Promise<string[]>;
  patchConfig(patch: Partial<ReaderConfig>): Promise<void>;
}

/** Minimal TUI surface used by the helpers, so tests can inject a fake. */
interface TuiContext {
  data: {
    on(name: string, handler: (event: unknown) => void): () => void;
  };
  keymap: {
    layer(factory: () => unknown): void;
  };
  ui: {
    toast: { show(options: PendingToast): void };
    dialog: {
      confirm(options: {
        title: string;
        message: string;
      }): Promise<boolean | undefined>;
      select(options: {
        title: string;
        options: Array<{ title: string; value: string }>;
        current?: string;
      }): Promise<string | undefined>;
    };
  };
}

/** Dependencies accepted by {@link createTuiPlugin}. */
export interface TuiPluginDeps {
  config?: ReaderConfig;
  serviceFactory?: (config: ReaderConfig) => IdleService;
  schedule?: (fn: () => void | Promise<void>, ms: number) => unknown;
}

/** Build the notice shown when a reply is held. */
export function buildPendingToast(
  pending: PendingItem,
  config: ReaderConfig,
): PendingToast | null {
  if (config.askMarkdown === "none") return null;
  if (pending.reason !== "markdown" && pending.reason !== "long") return null;

  const toast: PendingToast = {
    title:
      pending.reason === "markdown"
        ? "Markdown reply not read"
        : "Long reply not read",
    message:
      pending.reason === "markdown"
        ? "Run /reader-speak to hear it."
        : `This reply is ${pending.words} words. Run /reader-speak to hear it.`,
    variant: "info",
    duration: 10000,
  };
  if (pending.session_id !== undefined) toast.sessionID = pending.session_id;
  return toast;
}

/** Offer a held reply through the configured dialog or toast. */
export async function notifyPending(
  context: TuiContext,
  service: PendingService,
  pending: PendingItem | undefined,
  config: ReaderConfig,
): Promise<"none" | "toast" | "spoken" | "declined"> {
  if (pending === undefined || config.askMarkdown === "none") return "none";

  if (config.askMarkdown === "dialog") {
    const accepted = await context.ui.dialog.confirm({
      title: "Read this reply aloud?",
      message:
        "This reply was held because it looks like a document or is very long.",
    });
    if (!accepted) return "declined";
    await service.speakPending(pending.session_id ?? undefined);
    return "spoken";
  }

  const toast = buildPendingToast(pending, config);
  if (toast === null) return "none";
  context.ui.toast.show(toast);
  return "toast";
}

/** Let the user choose and persist a reader voice. */
export async function chooseVoice(
  context: TuiContext,
  service: VoiceService,
  config: ReaderConfig,
): Promise<string | undefined> {
  const voices = await service.voices();
  const voice = await context.ui.dialog.select({
    title: "Reader voice",
    options: voices.map((value) => ({ title: value, value })),
    current: config.voice,
  });
  if (voice === undefined) return undefined;

  await service.patchConfig({ voice });
  config.voice = voice;
  context.ui.toast.show({
    title: "Reader voice",
    message: `Voice set to ${voice}`,
    variant: "success",
    duration: 10000,
  });
  return voice;
}

/** Build the TUI plugin, optionally with test-injected dependencies. */
export function createTuiPlugin(deps: TuiPluginDeps = {}) {
  const config = deps.config ?? loadReaderConfig();
  const service = deps.serviceFactory?.(config) ?? new TtsService({ config });
  const ready = service.ensureStarted().catch((error: unknown) => {
    console.error("[reader.tts.tui]", "service start failed", error);
  });

  return Plugin.define({
    id: "reader.tts.tui",
    setup(context) {
      const unsubscribe = context.data.on("session.idle", (event) => {
        const sessionID = (event as { data?: { sessionID?: unknown } }).data
          ?.sessionID;
        if (typeof sessionID !== "string") return;

        const schedule =
          deps.schedule ??
          ((fn: () => void | Promise<void>, ms: number) =>
            setTimeout(fn, ms));
        schedule(() => {
          void (async () => {
            try {
              await ready;
              const pending = await service.pending(sessionID);
              await notifyPending(context, service, pending[0], config);
            } catch (error) {
              console.error("[reader.tts.tui]", "pending notice failed", error);
            }
          })();
        }, 500);
      });

      context.keymap.layer(() => ({
        commands: [
          {
            id: "reader.voice",
            title: "Reader: choose voice",
            group: "Reader",
            slash: { name: "reader-voice" },
            run: async () => {
              await ready;
              await chooseVoice(context, service, config);
            },
          },
        ],
      }));

      return unsubscribe;
    },
  });
}

export default createTuiPlugin();
