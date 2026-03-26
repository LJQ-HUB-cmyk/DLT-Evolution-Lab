import { defineConfig, devices } from "@playwright/test";

const reuse = process.env.CI ? false : true;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5173",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: reuse,
    timeout: 180_000,
    stdout: "pipe",
    stderr: "pipe",
  },
  projects: [
    { name: "desktop", testMatch: /smoke\.desktop\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", testMatch: /smoke\.mobile\.spec\.ts/, use: { ...devices["Pixel 7"] } },
  ],
});
