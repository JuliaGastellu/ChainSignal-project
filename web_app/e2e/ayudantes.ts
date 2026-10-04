import { expect, type Page } from "@playwright/test";
import path from "node:path";

// Dirección de la fixture grabada (Aave V3, bloque 26116392, health factor ≈ 1,2254).
export const DIRECCION_FIXTURE = "0x4246c44B2171F4f6cB6626bc19e5B977a6Be8C3F";
export const CONTRASENA = "contrasena-e2e-segura";
// Receptor HTTPS local que levanta scripts/entorno_e2e.py: los webhooks no salen de la máquina.
export const PUERTO_RECEPTOR = Number(process.env.CHAINSIGNAL_E2E_RECEPTOR_PORT ?? 9443);
export const WEBHOOK_OK = `https://localhost:${PUERTO_RECEPTOR}/hooks/equipo`;
export const WEBHOOK_FALLA = `https://localhost:${PUERTO_RECEPTOR}/hooks/falla`;

// Playwright corre desde web_app/; las capturas van a docs/capturas del repositorio.
const CAPTURAS = path.resolve(process.cwd(), "..", "docs", "capturas");

export function emailUnico(prefijo: string): string {
  return `${prefijo}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@ejemplo.test`;
}

export async function capturar(page: Page, nombre: string) {
  await page.screenshot({ path: path.join(CAPTURAS, `${nombre}.png`), fullPage: true });
}

export async function entrarADemo(page: Page): Promise<string> {
  await page.goto("/");
  await page.getByRole("button", { name: "Probar la demo" }).click();
  await expect(page).toHaveURL(/\/app\/[0-9a-f]+\/resumen$/);
  return page.url().split("/app/")[1].split("/")[0];
}

export async function crearOrganizacion(page: Page, nombre: string): Promise<{ email: string; org: string }> {
  const email = emailUnico("owner");
  await page.goto("/registro");
  await page.getByLabel("Nombre de la organización").fill(nombre);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Contraseña").fill(CONTRASENA);
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page).toHaveURL(/\/app\/[0-9a-f]+\/resumen$/);
  return { email, org: page.url().split("/app/")[1].split("/")[0] };
}

// Navego por las secciones principales (el nombre del enlace puede incluir el contador de incidentes).
export async function irA(page: Page, seccion: "Resumen" | "Posiciones" | "Incidentes" | "Configuración") {
  await page.getByRole("navigation", { name: "Secciones" }).getByRole("link", { name: new RegExp(`^${seccion}`) }).click();
}

// Creo una política de health factor pasando por la vista previa obligatoria.
export async function crearPoliticaHF(page: Page, umbral: string) {
  await page.getByRole("button", { name: "Nueva política" }).click();
  await page.getByLabel("Umbral de alerta (health factor)").fill(umbral);
  await page.getByRole("button", { name: "Ver cuándo abre y cuándo despeja" }).click();
  await expect(page.getByText(/^Abre cuando el health factor queda por debajo de/)).toBeVisible();
  await page.getByRole("button", { name: "Crear política" }).click();
  await expect(page.getByText(new RegExp(`Health factor menor a ${umbral.replace(".", ",")};`))).toBeVisible();
}

// Creo un webhook hacia el receptor local, guardo el secreto que se muestra una vez y lo pruebo.
export async function crearWebhook(page: Page, url: string, nombre = "Alertas del equipo") {
  const canales = page.getByRole("region", { name: "Canales de notificación" });
  await canales.getByLabel("Nombre", { exact: true }).fill(nombre);
  await canales.getByLabel("URL del webhook (https)").fill(url);
  await canales.getByRole("button", { name: "Crear webhook" }).click();
  await expect(page.getByText(/Guardá este secreto ahora/)).toBeVisible();
  await page.getByRole("button", { name: "Listo, lo guardé" }).click();
}

// Elementos que se salen del ancho de la pantalla, sin contar los que viven dentro
// de un contenedor con scroll horizontal propio (la barra de secciones, tablas).
export async function desbordes(page: Page): Promise<string[]> {
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
