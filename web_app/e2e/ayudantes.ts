import { expect, type Page } from "@playwright/test";
import path from "node:path";

// Dirección de la fixture grabada (Aave V3, bloque 26116392, health factor ≈ 1,2254).
export const DIRECCION_FIXTURE = "0x4246c44B2171F4f6cB6626bc19e5B977a6Be8C3F";
export const CONTRASENA = "contrasena-e2e-segura";

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
