import { describe, expect, test } from "bun:test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  DEFAULT_CONFIG,
  loadReaderConfig,
  toSnakeCaseConfig,
} from "../src/config";

describe("reader config", () => {
  test("returns defaults when the file is missing", () => {
    const cfg = loadReaderConfig(
      join(tmpdir(), "definitely-missing-reader.json"),
    );
    expect(cfg.voice).toBe("Bella");
    expect(cfg.port).toBe(8765);
    expect(cfg.maxWords).toBe(1500);
  });

  test("merges snake_case JSON over defaults", () => {
    const dir = mkdtempSync(join(tmpdir(), "reader-config-"));
    const path = join(dir, "tts-reader.json");
    writeFileSync(
      path,
      JSON.stringify({ voice: "Bruno", max_words: 100, auto_read: false }),
    );
    const cfg = loadReaderConfig(path);
    expect(cfg.voice).toBe("Bruno");
    expect(cfg.maxWords).toBe(100);
    expect(cfg.autoRead).toBe(false);
    expect(cfg.port).toBe(DEFAULT_CONFIG.port);
  });

  test("maps camelCase patches to snake_case", () => {
    expect(
      toSnakeCaseConfig({ autoRead: false, voice: "Bruno", maxWords: 50 }),
    ).toEqual({
      auto_read: false,
      voice: "Bruno",
      max_words: 50,
    });
  });
});
