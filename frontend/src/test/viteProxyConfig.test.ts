import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("Vite API proxy", () => {
  it("defaults to the V2 FastAPI port", () => {
    const viteConfig = readFileSync(
      resolve(process.cwd(), "vite.config.ts"),
      "utf8",
    );

    expect(viteConfig).toMatch(
      /target:\s*environment\.VITE_API_PROXY_TARGET \?\? "http:\/\/127\.0\.0\.1:8002"/,
    );
    expect(viteConfig).not.toContain('?? "http://127.0.0.1:8000"');
  });
});
