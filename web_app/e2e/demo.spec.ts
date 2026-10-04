import { expect, test } from "@playwright/test";
import { capturar, irA, crearOrganizacion, entrarADemo } from "./ayudantes";

test("la demo muestra datos sintéticos y permite revisar el incidente", async ({ page }) => {
  await entrarADemo(page);
  await expect(page.getByText(/Datos sintéticos: el recorrido y los canales son simulados/)).toBeVisible();
  await capturar(page, "08-demo-resumen");

  await irA(page, "Posiciones");
  await page.getByRole("list", { name: "Cuentas observadas" }).getByRole("link").first().click();
  await expect(page.getByText("Datos sintéticos", { exact: true })).toBeVisible();
  await expect(page.getByText("1,37", { exact: false }).first()).toBeVisible();

  await irA(page, "Incidentes");
  await page.getByRole("list", { name: "Incidentes activos" }).getByRole("link").first().click();
  await page.getByRole("button", { name: "Tomar el incidente" }).click();
  await expect(page.getByText("En seguimiento", { exact: true })).toBeVisible();
});

test("la demo está aislada de las organizaciones reales", async ({ browser }) => {
  const real = await browser.newContext();
  const paginaReal = await real.newPage();
  const { org: orgReal } = await crearOrganizacion(paginaReal, "Organización real");

  const demo = await browser.newContext();
  const paginaDemo = await demo.newPage();
  const orgDemo = await entrarADemo(paginaDemo);

  // La sesión de la demo no ve la organización real, ni por la interfaz ni por la API.
  await paginaDemo.goto(`/app/${orgReal}/resumen`);
  await expect(paginaDemo.getByText("No sos miembro de esta organización.")).toBeVisible();
  expect((await paginaDemo.request.get(`/orgs/${orgReal}/accounts`)).status()).toBe(403);

  // Y la organización real tampoco ve la demo.
  expect((await paginaReal.request.get(`/orgs/${orgDemo}/summary`)).status()).toBe(403);
  await real.close();
  await demo.close();
});
