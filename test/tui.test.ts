import { describe, expect, test } from "bun:test";
import { DEFAULT_CONFIG } from "../src/config";
import {
  buildPendingToast,
  chooseVoice,
  createTuiPlugin,
  notifyPending,
} from "../src/tui";
import type { PendingItem } from "../src/types";

const pending: PendingItem = {
  session_id: "s1",
  message_id: "m1",
  reason: "markdown",
  words: 300,
  created_at: 1,
};

function context() {
  const toasts: any[] = [];
  const confirmations: boolean[] = [];
  const selections: Array<string | undefined> = [];
  return {
    toasts,
    confirmations,
    selections,
    ctx: {
      data: { on: () => () => {} },
      keymap: { layer: () => {} },
      ui: {
        toast: { show: (options: any) => toasts.push(options) },
        dialog: {
          confirm: async () => confirmations.shift(),
          select: async () => selections.shift(),
        },
      },
    },
  };
}

describe("TUI pending notices", () => {
  test("builds a markdown toast", () => {
    expect(buildPendingToast(pending, DEFAULT_CONFIG)).toEqual({
      title: "Markdown reply not read",
      message: "Run /reader-speak to hear it.",
      variant: "info",
      duration: 10000,
      sessionID: "s1",
    });
  });

  test("builds a long-reply toast", () => {
    const toast = buildPendingToast(
      { ...pending, reason: "long", words: 1800 },
      DEFAULT_CONFIG,
    );
    expect(toast?.message).toContain("1800 words");
  });

  test("respects ask_markdown none", () => {
    expect(
      buildPendingToast(pending, { ...DEFAULT_CONFIG, askMarkdown: "none" }),
    ).toBeNull();
  });

  test("shows a toast by default", async () => {
    const { toasts, ctx } = context();
    const result = await notifyPending(
      ctx,
      { speakPending: async () => {} } as never,
      pending,
      DEFAULT_CONFIG,
    );
    expect(result).toBe("toast");
    expect(toasts).toHaveLength(1);
  });

  test("dialog acceptance speaks the pending reply", async () => {
    const { toasts, confirmations, ctx } = context();
    confirmations.push(true);
    const spoken: string[] = [];
    const result = await notifyPending(
      ctx,
      {
        speakPending: async (sessionID: string) => {
          spoken.push(sessionID);
        },
      } as never,
      pending,
      { ...DEFAULT_CONFIG, askMarkdown: "dialog" },
    );
    expect(result).toBe("spoken");
    expect(spoken).toEqual(["s1"]);
    expect(toasts).toEqual([]);
  });

  test("dialog rejection leaves the reply held", async () => {
    const { confirmations, ctx } = context();
    confirmations.push(false);
    const spoken: string[] = [];
    const result = await notifyPending(
      ctx,
      {
        speakPending: async (sessionID: string) => {
          spoken.push(sessionID);
        },
      } as never,
      pending,
      { ...DEFAULT_CONFIG, askMarkdown: "dialog" },
    );
    expect(result).toBe("declined");
    expect(spoken).toEqual([]);
  });
});

describe("TUI voice picker", () => {
  test("patches the selected voice and confirms it", async () => {
    const { toasts, selections, ctx } = context();
    selections.push("Bruno");
    const patched: any[] = [];
    const voice = await chooseVoice(
      ctx,
      {
        voices: async () => ["Bella", "Bruno"],
        patchConfig: async (patch: any) => {
          patched.push(patch);
        },
      } as never,
      { ...DEFAULT_CONFIG },
    );
    expect(voice).toBe("Bruno");
    expect(patched).toEqual([{ voice: "Bruno" }]);
    expect(toasts[0].message).toBe("Voice set to Bruno");
  });
});

describe("TUI plugin wiring", () => {
  test("registers /reader-voice and toasts a held reply on idle", async () => {
    const toasts: any[] = [];
    let idleHandler: ((event: any) => void) | undefined;
    let layerFactory: (() => any) | undefined;
    const fakeService = {
      ensureStarted: async () => {},
      pending: async () => [pending],
      speakPending: async () => {},
      voices: async () => ["Bella"],
      patchConfig: async () => {},
    };
    const ctx = {
      data: {
        on: (_name: string, handler: (event: any) => void) => {
          idleHandler = handler;
          return () => {};
        },
      },
      keymap: {
        layer: (factory: () => any) => {
          layerFactory = factory;
        },
      },
      ui: {
        toast: { show: (options: any) => toasts.push(options) },
        dialog: { confirm: async () => false, select: async () => undefined },
      },
    };
    const plugin = createTuiPlugin({
      config: DEFAULT_CONFIG,
      serviceFactory: () => fakeService as never,
      schedule: (fn) => fn(),
    });
    await (plugin.setup as any)(ctx);
    expect(layerFactory?.().commands[0].slash.name).toBe("reader-voice");
    idleHandler?.({ data: { sessionID: "s1" } });
    await Bun.sleep(10);
    expect(toasts[0].title).toBe("Markdown reply not read");
  });
});
