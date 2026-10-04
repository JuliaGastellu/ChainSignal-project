import { defineConfig, devices } from "@playwright/test";

// E2E contra un entorno aislado: API y worker sobre SQLite temporal con la
// lectura de Aave V3 reproducida desde una fixture (scripts/entorno_e2e.py), y
// la interfaz compilada servida por `vite preview`. Nada apunta a producción.
const python = process.env.CHAINSIGNAL_PYTHON ?? "python";
// Puertos configurables para no chocar con otro entorno levantado en la misma máquina.
const PUERTO_API = Number(process.env.CHAINSIGNAL_E2E_API_PORT ?? 8001);
const PUERTO_WEB = Number(process.env.CHAINSIGNAL_E2E_WEB_PORT ?? 4173);
const PUERTO_RECEPTOR = Number(process.env.CHAINSIGNAL_E2E_RECEPTOR_PORT ?? 9443);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: `http://127.0.0.1:${PUERTO_WEB}`,
    trace: "retain-on-failure",
    locale: "es-AR",
    // Chromium completo en modo headless nuevo (no hace falta el headless shell).
    channel: "chromium",
  },
  projects: [
    { name: "escritorio", use: { ...devices["Desktop Chrome"], channel: "chromium" }, testIgnore: /movil\.spec\.ts/ },
    { name: "movil", use: { ...devices["Pixel 7"], channel: "chromium" }, testMatch: /movil\.spec\.ts/ },
  ],
  webServer: [
    {
      command: `"${python}" ../scripts/entorno_e2e.py --puerto ${PUERTO_API} --origen-web http://127.0.0.1:${PUERTO_WEB} --puerto-receptor ${PUERTO_RECEPTOR}`,
      url: `http://127.0.0.1:${PUERTO_API}/health`,
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: `npm run build && npx vite preview --port ${PUERTO_WEB} --strictPort`,
      url: `http://127.0.0.1:${PUERTO_WEB}`,
      timeout: 180_000,
      reuseExistingServer: false,
      env: { CHAINSIGNAL_API_PROXY: `http://127.0.0.1:${PUERTO_API}` },
    },
  ],
});
