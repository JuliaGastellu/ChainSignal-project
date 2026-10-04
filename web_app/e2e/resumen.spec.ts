import { expect, test } from "@playwright/test";
import { capturar, crearOrganizacion, crearPoliticaHF, crearWebhook, DIRECCION_FIXTURE, irA, WEBHOOK_OK } from "./ayudantes";

async function agregarCuenta(page: import("@playwright/test").Page, direccion: string, nombre: string) {
  await irA(page, "Posiciones");
  // Con la organización vacía, el formulario ya está abierto.
  await page.getByLabel("Dirección").fill(direccion);
  await page.getByLabel("Nombre (opcional)").fill(nombre);
  await page.getByRole("button", { name: "Agregar" }).click();
  await expect(page.getByRole("heading", { name: nombre })).toBeVisible();
}

test("sano: monitoreo preparado sin incidentes", async ({ page }) => {
  await crearOrganizacion(page, "Equipo sano");
  await agregarCuenta(page, DIRECCION_FIXTURE, "Cuenta sana");
  await page.getByRole("button", { name: /Obtener primer snapshot|Leer de nuevo/ }).click();
  await expect(page.getByText("Dato actualizado", { exact: true })).toBeVisible();
  await irA(page, "Configuración");
  await crearPoliticaHF(page, "1.1"); // el health factor de la fixture (1,2254) queda por encima
  await crearWebhook(page, WEBHOOK_OK);
  await page.getByRole("region", { name: "Canales de notificación" }).getByRole("button", { name: /Enviar prueba/ }).click();
  await expect(page.getByText("Aceptada por el destino externo")).toBeVisible();
  await irA(page, "Resumen");
  await expect(page.getByText(/Nada requiere atención ahora/)).toBeVisible();
  await expect(page.getByText("Monitoreo preparado", { exact: true })).toBeVisible();
  await capturar(page, "15-resumen-sano");
});

test("datos no disponibles: lo dice y da el siguiente paso", async ({ page }) => {
  await crearOrganizacion(page, "Equipo sin datos");
  // Una dirección que la lectura de prueba no tiene: el proveedor no puede leerla.
  await agregarCuenta(page, "0x00000000000000000000000000000000000000a1", "Cuenta sin datos");
  await page.getByRole("button", { name: /Obtener primer snapshot|Leer de nuevo/ }).click();
  await expect(page.getByText("Dato no disponible", { exact: true })).toBeVisible();
  await expect(page.getByText("Actividad desconocida")).toBeVisible();
  await page.getByRole("button", { name: "Evaluar políticas ahora" }).click();
  await irA(page, "Resumen");
  const atencion = page.getByRole("list", { name: "Elementos que necesitan atención" });
  await expect(atencion.getByText(/Sin datos no puedo decir si la posición está bien/)).toBeVisible({ timeout: 30_000 });
  await expect(atencion.getByRole("link", { name: "Ver la cuenta y reintentar la lectura" })).toBeVisible();
  await capturar(page, "16-resumen-sin-datos");
});

test("práctica aislada desde una organización real", async ({ page }) => {
  const { org } = await crearOrganizacion(page, "Equipo que practica");
  await page.getByText("Practicar un incidente (opcional)").click();
  await page.getByRole("button", { name: "Abrir la práctica" }).click();
  await expect(page).not.toHaveURL(new RegExp(`/app/${org}/`));
  await expect(page.getByText(/No cuenta como preparación del monitoreo de una organización real/)).toBeVisible();
  await expect(page.getByRole("list", { name: "Elementos que necesitan atención" })).toBeVisible();
  // La organización real sigue limpia.
  await page.goto(`/app/${org}/incidentes`);
  await expect(page.getByText("No hay incidentes activos")).toBeVisible();
});
