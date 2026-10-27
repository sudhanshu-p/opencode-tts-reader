import { describe, expect, test } from "bun:test";
import { DEFAULT_CONFIG } from "../src/config";
import { createPlugin } from "../src/index";

describe("server plugin", () => {
  test("registers the tool, commands, and speaks one idle session", async () => {
    const spoken: any[] = [];
    const tools: any[] = [];
    const commands: any[] = [];
    const fakeService = {
      ensureStarted: async () => {},
      speak: async (input: any) => {
        spoken.push(input);
        return { action: "queued", words: 2, jobId: "j1" };
      },
      speakPending: async () => {},
      stop: async () => {},
      mute: async () => {},
      unmute: async () => {},
    };
    const messages = [
      { id: "u1", type: "user" },
      {
        id: "a1",
        type: "assistant",
        content: [{ type: "text", text: "Hello." }],
      },
    ];
    async function* events() {
      yield {
        type: "session.execution.succeeded",
        data: { sessionID: "s1" },
      };
    }
    const ctx = {
      event: { subscribe: () => events() },
      session: {
        get: async () => ({ id: "s1" }),
        context: async () => messages,
      },
      tool: {
        transform: async (callback: any) =>
          callback({ add: (tool: any) => tools.push(tool) }),
      },
      command: {
        transform: async (callback: any) =>
          callback({ add: (command: any) => commands.push(command) }),
      },
    };
    const plugin = createPlugin({
      config: DEFAULT_CONFIG,
      serviceFactory: () => fakeService as never,
      log: () => {},
    });
    await (plugin.setup as any)(ctx);
    await Bun.sleep(20);
    expect(spoken).toHaveLength(1);
    expect(tools.map((tool) => tool.name)).toEqual(["reader_speak"]);
    expect(commands.map((command) => command.name)).toEqual([
      "reader-speak",
      "reader-stop",
      "reader-mute",
      "reader-unmute",
    ]);
    const toolResult = await tools[0].execute({ text: "Hi" }, {});
    expect(toolResult).toEqual({ content: "Speaking." });
  });
});
