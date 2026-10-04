import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { capturar, desbordes, entrarADemo } from "./ayudantes";

// Reviso las pantallas principales a 360, 390, 768 y 1440 px CSS: ancho
// efectivo del DOM, nada fuera de la pantalla y accesibilidad con axe (WCAG A
// y AA, incluido contraste). Uso la demo: datos sintéticos aislados.
const ANCHOS = [360, 390, 768, 1440];

async function revisar(page: Page, nombre: string, ancho: number) {
  const efectivo = await page.evaluate(() => ({ ancho: document.documentElement.clientWidth, desplazable: document.documentElement.scrollWidth }));
  expect(efectivo.ancho, `${nombre} @${ancho}: ancho efectivo`).toBe(ancho);
  expect(efectivo.desplazable, `${nombre} @${ancho}: scroll horizontal`).toBeLessThanOrEqual(ancho);
  expect(await desbordes(page), `${nombre} @${ancho}: elementos fuera de la pantalla`).toEqual([]);
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const graves = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  expect(graves, `${nombre} @${ancho}: violaciones de accesibilidad`).toEqual([]);
}

for (const ancho of ANCHOS) {
  test(`pantallas principales a ${ancho} px`, async ({ page }) => {
    await page.setViewportSize({ width: ancho, height: ancho < 768 ? 800 : 900 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await revisar(page, "portada", ancho);
    if (ancho === 360 || ancho === 1440) await capturar(page, `ancho-${ancho}-portada`);

    const org = await entrarADemo(page);
    for (const seccion of ["resumen", "posiciones", "incidentes", "configuracion"]) {
      await page.goto(`/app/${org}/${seccion}`);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await revisar(page, seccion, ancho);
    }
    // Las cuatro secciones entran en la barra sin tener que desplazarla.
    const fuera = await page.getByRole("navigation", { name: "Secciones" }).getByRole("link").evaluateAll((enlaces) =>
      enlaces.filter((e) => e.getBoundingClientRect().right > document.documentElement.clientWidth).map((e) => e.textContent));
    expect(fuera, `secciones cortadas @${ancho}`).toEqual([]);
    if (ancho === 360 || ancho === 1440) {
      await page.goto(`/app/${org}/resumen`);
      await expect(page.getByRole("list", { name: "Elementos que necesitan atención" })).toBeVisible();
      await capturar(page, `ancho-${ancho}-resumen`);
    }
    await page.goto(`/app/${org}/posiciones`);
    await page.getByRole("list", { name: "Cuentas observadas" }).getByRole("link").first().click();
    await expect(page.getByText("Datos sintéticos", { exact: true })).toBeVisible();
    await revisar(page, "detalle de posición", ancho);
    if (ancho === 360 || ancho === 1440) await capturar(page, `ancho-${ancho}-posicion`);
    await page.goto(`/app/${org}/incidentes`);
    await page.getByRole("list", { name: "Incidentes activos" }).getByRole("link").first().click();
    await expect(page.getByRole("button", { name: "Tomar el incidente" })).toBeVisible();
    await revisar(page, "detalle de incidente", ancho);
    if (ancho === 360 || ancho === 1440) await capturar(page, `ancho-${ancho}-incidente`);
  });
}

test("teclado: saltar al contenido, foco visible y secciones navegables", async ({ page }) => {
  const org = await entrarADemo(page);
  await expect(page.getByRole("heading", { name: "Resumen" })).toBeVisible();
  await page.keyboard.press("Tab");
  const saltar = page.getByRole("link", { name: "Saltar al contenido" });
  await expect(saltar).toBeFocused();
  const contorno = await saltar.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(contorno).not.toBe("none");
  // Recorro con Tab hasta la sección Incidentes y entro con Enter.
  for (let i = 0; i < 15; i++) {
    const nombre = await page.evaluate(() => document.activeElement?.textContent ?? "");
    if (/^Incidentes/.test(nombre.trim())) break;
    await page.keyboard.press("Tab");
  }
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/app/${org}/incidentes$`));
});
