import { expect, test } from "@playwright/test";
import { capturar, desbordes, entrarADemo } from "./ayudantes";

test("en un viewport móvil no hay scroll horizontal y la navegación es usable", async ({ page }) => {
  const org = await entrarADemo(page);
  for (const seccion of ["resumen", "posiciones", "incidentes", "configuracion"]) {
    await page.goto(`/app/${org}/${seccion}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await desbordes(page), `desborde horizontal en ${seccion}`).toEqual([]);
  }
  await page.goto(`/app/${org}/incidentes`);
  await page.getByRole("list", { name: "Incidentes activos" }).getByRole("link").first().click();
  await expect(page.getByRole("button", { name: "Tomar el incidente" })).toBeVisible();
  // También en los detalles, donde hay hashes y direcciones largas.
  expect(await desbordes(page), "desborde en el incidente").toEqual([]);
  await page.goto(`/app/${org}/posiciones`);
  await page.getByRole("list", { name: "Cuentas observadas" }).getByRole("link").first().click();
  await expect(page.getByText("Datos sintéticos", { exact: true })).toBeVisible();
  expect(await desbordes(page), "desborde en la posición").toEqual([]);
  await page.goto(`/app/${org}/incidentes`);
  await page.getByRole("list", { name: "Incidentes activos" }).getByRole("link").first().click();
  await capturar(page, "10-movil-incidente");
});
