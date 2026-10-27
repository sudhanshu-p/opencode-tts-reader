import { describe, expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

const root = join(import.meta.dir, "..");

describe("installer", () => {
  test("dry run prints planned actions without changing the system", () => {
    const result = spawnSync(
      "bash",
      [join(root, "scripts", "install.sh"), "--dry-run"],
      { encoding: "utf8" },
    );
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("opencode/plugins/opencode-tts");
    expect(result.stdout).toContain(".local/bin/opencode-tts");
    expect(result.stdout).toContain("uv sync");
  });
});
