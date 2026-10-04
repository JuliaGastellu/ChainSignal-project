import { expect, test } from "@playwright/test";
import { capturar, crearOrganizacion, crearPoliticaHF, crearWebhook, DIRECCION_FIXTURE, irA, WEBHOOK_OK } from "./ayudantes";

// Recorrido completo con datos controlados: alta, dirección y red, primer
// snapshot, política con vista previa, webhook externo probado contra un
// receptor local (monitoreo preparado), incidente abierto por el worker,
// explicación con referencias legibles, seguimiento y resolución.
test("activación, monitoreo preparado y revisión de un incidente", async ({ page }) => {
  await page.goto("/");
  await capturar(page, "01-landing");

  const { email, org } = await crearOrganizacion(page, "Tesorería Norte");
  await expect(page.getByText("Monitoreo preparado: 0 de 4")).toBeVisible();
  await expect(page.getByText("Servicio: en vivo")).toBeVisible();
  await capturar(page, "02-resumen-vacio");

  // Dirección y red.
  await irA(page, "Posiciones");
  await expect(page.getByText("Todavía no observás ninguna dirección")).toBeVisible();
  await page.getByLabel("Dirección").fill(DIRECCION_FIXTURE);
  await expect(page.getByLabel("Red")).toHaveValue("1");
  await page.getByLabel("Nombre (opcional)").fill("Prestataria USDC");
  await page.getByRole("button", { name: "Agregar" }).click();

  // Primer snapshot. Los snapshots son datos públicos de la dirección: si otra organización ya la leyó, el botón dice "Leer de nuevo".
  await expect(page.getByRole("heading", { name: "Prestataria USDC" })).toBeVisible();
  await page.getByRole("button", { name: /Obtener primer snapshot|Leer de nuevo/ }).click();
  await expect(page.getByText("1,2254")).toBeVisible();
  await expect(page.getByText("26.116.392")).toBeVisible();
  await expect(page.getByText("Dato actualizado", { exact: true })).toBeVisible();
  await expect(page.getByText("Posición con deuda")).toBeVisible();
  await expect(page.getByText("Sin alertas abiertas")).toBeVisible();
  await expect(page.getByText("Sin política de health factor")).toBeVisible();
  await capturar(page, "03-posicion-detalle");

  // Política con vista previa y webhook externo verificado.
  await irA(page, "Configuración");
  await expect(page.getByText("1 de 10")).toBeVisible();
  await crearPoliticaHF(page, "1.5");
  await crearWebhook(page, WEBHOOK_OK);
  const canales = page.getByRole("region", { name: "Canales de notificación" });
  await canales.getByRole("button", { name: /Enviar prueba/ }).click();
  await expect(canales.getByText(/El destino externo aceptó la prueba \(HTTP 2xx\)/)).toBeVisible();
  await expect(canales.getByText("Aceptada por el destino externo")).toBeVisible();
  await capturar(page, "04-configuracion");

  // Con cuenta, lectura válida, política y canal externo verificado, el monitoreo está preparado aunque no haya incidentes.
  await irA(page, "Resumen");
  await expect(page.getByText("Monitoreo preparado", { exact: true })).toBeVisible();

  // El worker evalúa y abre el incidente; la interfaz se entera por el stream.
  await irA(page, "Posiciones");
  await page.getByRole("link", { name: /Prestataria USDC/ }).click();
  await page.getByRole("button", { name: "Evaluar políticas ahora" }).click();
  await expect(page.getByRole("region", { name: "Alertas abiertas" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Alerta abierta: health factor bajo el umbral")).toBeVisible();

  await irA(page, "Resumen");
  const atencion = page.getByRole("list", { name: "Elementos que necesitan atención" });
  await expect(atencion.getByText("Health factor 1,2254 por debajo del umbral de alerta 1,5.")).toBeVisible();
  await capturar(page, "05-resumen-con-alerta");
  await atencion.getByRole("link", { name: "Revisar el incidente" }).click();

  await expect(page.getByText("Sin asignar")).toBeVisible();
  await expect(page.getByText("Versión 1", { exact: true })).toBeVisible();
  // La entrega al webhook la aceptó el destino; no digo que alguien la leyó.
  await expect(page.getByRole("region", { name: "Notificaciones" }).getByText("Aceptada por el destino externo")).toBeVisible();
  // Explicación por plantilla con referencias legibles.
  await expect(page.getByText("Plantilla determinista")).toBeVisible();
  await expect(page.getByRole("link", { name: "Lectura del bloque 26.116.392" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Política, versión 1" }).first()).toBeVisible();
  await capturar(page, "06-incidente-abierto");

  // Seguimiento y resolución.
  await page.getByRole("button", { name: "Tomar el incidente" }).click();
  await expect(page.getByText("En seguimiento", { exact: true })).toBeVisible();
  await expect(page.locator("dt", { hasText: "Responsable" }).locator("+ dd")).toHaveText(email);
  await page.getByLabel("Nota de resolución").fill("Repagué parte de la deuda; sigo mirando el umbral.");
  await page.getByRole("button", { name: "Resolver" }).click();
  await expect(page.getByText("Resuelto", { exact: true })).toBeVisible();
  await expect(page.locator("p", { hasText: "Nota de resolución:" })).toContainText("Repagué parte de la deuda; sigo mirando el umbral.");
  await capturar(page, "07-incidente-resuelto");

  await irA(page, "Incidentes");
  await expect(page.getByText("No hay incidentes activos")).toBeVisible();
  await page.getByRole("tab", { name: "Resueltos" }).click();
  await expect(page.getByRole("link", { name: /Health factor bajo/ })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/app/${org}/incidentes$`));
});
