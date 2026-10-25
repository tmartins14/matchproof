import { defineConfig } from "@playwright/test";

const PORT = 3100;

export default defineConfig({
  testDir: "e2e",
  reporter: "list",
  use: { baseURL: `http://localhost:${PORT}`, colorScheme: "dark" },
  webServer: { command: `serve out -l ${PORT}`, url: `http://localhost:${PORT}`, reuseExistingServer: true, timeout: 60_000 },
});
