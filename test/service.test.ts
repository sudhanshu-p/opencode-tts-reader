import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DEFAULT_CONFIG } from "../src/config";
import { TtsService } from "../src/service";

const ok = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

function tempRepo(): string {
  const root = mkdtempSync(join(tmpdir(), "reader-repo-"));
  const bin = join(root, "python", ".venv", "bin");
  mkdirSync(bin, { recursive: true });
  writeFileSync(join(bin, "python"), "");
  return root;
}

describe("TtsService", () => {
  test("speak posts snake_case body", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const service = new TtsService({
      config: { ...DEFAULT_CONFIG, port: 9999 },
      fetch: async (input, init) => {
        calls.push([String(input), init]);
        return ok({ action: "queued", words: 2, job_id: "j1" });
      },
    });
    const result = await service.speak({
      text: "Hi",
      sessionID: "s1",
      messageID: "m1",
      turnHasMarkdownFile: true,
    });
    expect(result.jobId).toBe("j1");
    expect(calls[0][0]).toBe("http://127.0.0.1:9999/speak");
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({
      text: "Hi",
      session_id: "s1",
      message_id: "m1",
      source: "auto",
      turn_has_markdown_file: true,
      force: false,
    });
  });

  test("pending adds the session query", async () => {
    const calls: string[] = [];
    const service = new TtsService({
      fetch: async (input) => {
        calls.push(String(input));
        return ok({ pending: [] });
      },
    });
    await service.pending("s1");
    expect(calls[0]).toBe("http://127.0.0.1:8765/pending?session_id=s1");
  });

  test("patchConfig maps camelCase", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const service = new TtsService({
      fetch: async (input, init) => {
        calls.push([String(input), init]);
        return ok({});
      },
    });
    await service.patchConfig({ voice: "Bruno", autoRead: false });
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({
      voice: "Bruno",
      auto_read: false,
    });
  });

  test("ensureStarted does not spawn when healthy", async () => {
    let spawned = false;
    const service = new TtsService({
      fetch: async () => ok({ ok: true }),
      spawn: (() => {
        spawned = true;
        return { unref() {} };
      }) as never,
      repoRoot: tempRepo(),
    });
    await service.ensureStarted();
    expect(spawned).toBe(false);
  });

  test("ensureStarted spawns detached when unhealthy", async () => {
    const repoRoot = tempRepo();
    let calls = 0;
    let spawned: { command: string; args: string[]; options: any } | null =
      null;
    const service = new TtsService({
      fetch: async () => {
        calls += 1;
        if (calls === 1) throw new Error("ECONNREFUSED");
        return ok({ ok: true });
      },
      spawn: ((command: string, args: string[], options: any) => {
        spawned = { command, args, options };
        return { unref() {} };
      }) as never,
      repoRoot,
      dataDir: join(repoRoot, "data"),
      sleep: async () => {},
    });
    await service.ensureStarted();
    const spawnedCall = spawned as {
      command: string;
      args: string[];
      options: any;
    } | null;
    expect(spawnedCall?.command).toBe(
      join(repoRoot, "python", ".venv", "bin", "python"),
    );
    expect(spawnedCall?.args).toEqual(["-m", "tts_service"]);
    expect(spawnedCall?.options.cwd).toBe(join(repoRoot, "python"));
    expect(spawnedCall?.options.detached).toBe(true);
  });
});
