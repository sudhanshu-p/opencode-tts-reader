import { Plugin } from "@opencode/plugin";
import type { Session } from "@opencode/schema/session";
import { loadReaderConfig, type ReaderConfig } from "./config";
import { handleSessionIdle } from "./handle";
import { log as defaultLog, type LogFn } from "./log";
import { TtsService } from "./service";
import type { MessageItem, SpeakInput } from "./types";

/** Replaceable seams for tests and local embedding. */
export interface PluginDeps {
  config?: ReaderConfig;
  serviceFactory?: (config: ReaderConfig) => TtsService;
  log?: LogFn;
}

const TOOL_NAME = "reader_speak";

const TOOL_DESCRIPTION =
  "Speak text through the local KittenTTS reader. Use for the final reply prose when explicitly asked, or when automatic reading is disabled.";

const TOOL_INPUT = {
  type: "object",
  properties: {
    text: {
      type: "string",
      description: "The prose to read aloud, verbatim.",
    },
  },
  required: ["text"],
  additionalProperties: false,
} as const;

interface ToolRunContext {
  sessionID?: string;
  messageID?: string;
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function readToolText(input: unknown): string {
  if (typeof input !== "object" || input === null) return "";
  const text = (input as { text?: unknown }).text;
  return typeof text === "string" ? text : "";
}

/** Build the V2 server plugin. The default export is the production wiring. */
export function createPlugin(deps: PluginDeps = {}): Plugin.Plugin {
  return Plugin.define({
    id: "reader.tts",
    async setup(ctx) {
      const config = deps.config ?? loadReaderConfig();
      const log = deps.log ?? defaultLog;
      const service = deps.serviceFactory?.(config) ?? new TtsService({ config });

      const ready = service.ensureStarted();
      void ready.catch((error: unknown) => {
        log("service start failed", { error: describeError(error) });
      });

      const speak = (input: SpeakInput) => service.speak(input);

      await ctx.tool.transform((tool) => {
        tool.add({
          name: TOOL_NAME,
          description: TOOL_DESCRIPTION,
          input: TOOL_INPUT,
          async execute(input: unknown, context: ToolRunContext) {
            await ready;
            const result = await service.speak({
              text: readToolText(input),
              sessionID: context.sessionID ?? "",
              messageID: context.messageID ?? "",
              source: "manual",
              force: true,
            });
            if (result.action === "queued") return { content: "Speaking." };
            if (result.action === "pending") {
              return { content: "Held for /reader-speak." };
            }
            return { content: `Reader: ${result.action}` };
          },
        });
      });

      await ctx.command.transform((command) => {
        command.add({
          name: "reader-speak",
          description: "Speak the reply held for this session.",
          execute: async (input) => {
            await ready;
            await service.speakPending(input.sessionID);
          },
        });
        command.add({
          name: "reader-stop",
          description: "Stop speech and clear the reader queue.",
          execute: async () => {
            await ready;
            await service.stop();
          },
        });
        command.add({
          name: "reader-mute",
          description: "Mute automatic reading.",
          execute: async () => {
            await ready;
            await service.mute();
          },
        });
        command.add({
          name: "reader-unmute",
          description: "Unmute automatic reading.",
          execute: async () => {
            await ready;
            await service.unmute();
          },
        });
      });

      const abort = new AbortController();
      const stopped = new Promise<null>((resolve) => {
        if (abort.signal.aborted) {
          resolve(null);
          return;
        }
        abort.signal.addEventListener("abort", () => resolve(null), {
          once: true,
        });
      });

      // The event stream is infinite; keep it off the setup path so the
      // plugin finishes registering.
      void (async () => {
        const events = ctx.event.subscribe()[Symbol.asyncIterator]();
        try {
          while (!abort.signal.aborted) {
            const next = await Promise.race([events.next(), stopped]);
            if (next === null || next.done) break;
            if (abort.signal.aborted) break;

            const event = next.value;
            try {
              if (
                (event as { type?: unknown }).type !==
                "session.execution.succeeded"
              ) {
                continue;
              }

              const sessionID = (
                event as { data?: { sessionID?: unknown } }
              ).data?.sessionID;
              if (typeof sessionID !== "string") continue;

              await ready;

              const session = await ctx.session.get({
                sessionID: sessionID as Session.ID,
              });
              if (!session) {
                log("idle skipped", {
                  sessionID,
                  action: "skipped",
                  reason: "missing",
                });
                continue;
              }

              if (session.parentID && !config.includeSubagents) {
                log("idle skipped", {
                  sessionID,
                  action: "skipped",
                  reason: "subagent",
                });
                continue;
              }

              const messages = await ctx.session.context({
                sessionID: sessionID as Session.ID,
              });
              const result = await handleSessionIdle(
                {
                  sessionID,
                  session: { id: session.id, parentID: session.parentID },
                  messages: messages as readonly MessageItem[],
                },
                { config, speak },
              );

              log("idle handled", {
                sessionID,
                action: result.action,
                reason: result.reason,
              });
            } catch (error) {
              log("idle handler failed", { error: describeError(error) });
            }
          }
        } catch (error) {
          log("event stream failed", { error: describeError(error) });
        } finally {
          if (abort.signal.aborted) {
            const closing = events.return?.();
            if (closing) void closing.catch(() => {});
          }
        }
      })();

      return () => {
        abort.abort();
      };
    },
  });
}

export default createPlugin();
