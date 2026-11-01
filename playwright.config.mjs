import process from "node:process";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "playground",
  testMatch: "*.spec.mjs",
  timeout: 120000,
  use: {
    baseURL: "http://127.0.0.1:8469",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium", launchOptions: { executablePath: process.env.CHROME_PATH } } },
    { name: "firefox", use: { browserName: "firefox" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  webServer: {
    command: `uv run --no-project python -m http.server 8469 --bind 127.0.0.1 --directory ${process.env.PLAYGROUND_DIR || "playground"}`,
    reuseExistingServer: false,
    url: "http://127.0.0.1:8469",
  },
  workers: 1,
});
