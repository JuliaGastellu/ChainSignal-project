import { expect, test, type Page } from "@playwright/test";
import { capturar, entrarADemo } from "./ayudantes";

// Elementos que se salen del ancho de la pantalla, sin contar los que viven dentro
// de un contenedor con scroll horizontal propio (la barra de secciones, tablas).
async function desbordes(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const ancho = document.documentElement.clientWidth;
    const dentroDeScroll = (el: Element | null): boolean => {
      for (let p = el?.parentElement; p; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX;
        if (ox === "auto" || ox === "scroll" || ox === "hidden") return true;
      }
      return false;
    };
    return [...document.querySelectorAll("body *")]
      .filter((el) => el.getBoundingClientRect().right > ancho + 1 && !dentroDeScroll(el))
      .map((el) => `${el.tagName.toLowerCase()}: ${(el.textContent ?? "").slice(0, 40)}`);
  });
}

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
