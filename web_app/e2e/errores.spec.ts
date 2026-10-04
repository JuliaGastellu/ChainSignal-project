import { expect, test } from "@playwright/test";
import { capturar, entrarADemo } from "./ayudantes";

// Fallas de la API simuladas interceptando las respuestas en el navegador.

test("un 429 explica la espera y no se presenta como éxito", async ({ page }) => {
  const org = await entrarADemo(page);
  await page.route(`**/orgs/${org}/accounts`, (ruta) =>
    ruta.fulfill({ status: 429, headers: { "Retry-After": "30" }, json: { error: "rate_limited", message: "slow down" } }),
  );
  await page.goto(`/app/${org}/posiciones`);
  await expect(page.getByText("Demasiadas solicitudes")).toBeVisible();
  await expect(page.getByText("Esperá 30 s antes de reintentar.")).toBeVisible();
  await capturar(page, "09-error-429");
});

test("un 403 se muestra como falta de permiso", async ({ page }) => {
  const org = await entrarADemo(page);
  await page.route(`**/orgs/${org}/incidents?status=active`, (ruta) => ruta.fulfill({ status: 403, json: { error: "forbidden", message: "no" } }));
  await page.goto(`/app/${org}/incidentes`);
  await expect(page.getByText("Sin permiso")).toBeVisible();
});

test("con el servidor caído avisa y permite reintentar", async ({ page }) => {
  const org = await entrarADemo(page);
  await page.route(`**/orgs/${org}/summary`, (ruta) => ruta.abort("connectionrefused"));
  await page.goto(`/app/${org}/resumen`);
  await expect(page.getByText("El servidor no responde")).toBeVisible({ timeout: 20_000 });
  await page.unroute(`**/orgs/${org}/summary`);
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.getByRole("heading", { name: "Resumen" })).toBeVisible();
});

test("una sesión vencida lleva al login", async ({ page }) => {
  const org = await entrarADemo(page);
  await page.route("**/auth/session", (ruta) => ruta.fulfill({ status: 401, json: { error: "not_authenticated", message: "no" } }));
  await page.goto(`/app/${org}/resumen`);
  await expect(page).toHaveURL(/\/login$/);
});

test("si el stream de eventos se corta, muestra que está reconectando y vuelve", async ({ page }) => {
  const org = await entrarADemo(page);
  await expect(page.getByText("Servicio: en vivo")).toBeVisible();
  await page.route(`**/orgs/${org}/events/stream*`, (ruta) => ruta.fulfill({ status: 429, json: { error: "too_many_streams", message: "x" } }));
  await page.reload();
  await expect(page.getByText("Servicio: reconectando…")).toBeVisible();
  await page.unroute(`**/orgs/${org}/events/stream*`);
  await expect(page.getByText("Servicio: en vivo")).toBeVisible({ timeout: 20_000 });
});
