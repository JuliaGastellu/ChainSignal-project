import { expect, test } from "@playwright/test";
import { capturar, irA, crearOrganizacion, DIRECCION_FIXTURE } from "./ayudantes";

// Recorrido completo de activación con datos controlados: alta, dirección y red,
// primer snapshot, política, canal probado, incidente abierto por el worker,
// seguimiento y resolución.
test("activación y revisión de un incidente", async ({ page }) => {
  await page.goto("/");
  await capturar(page, "01-landing");

  const { email, org } = await crearOrganizacion(page, "Tesorería Norte");
  await expect(page.getByText("Primeros pasos (0 de 5)")).toBeVisible();
  await expect(page.getByText("En vivo")).toBeVisible();
  await capturar(page, "02-resumen-vacio");

  // Dirección y red.
  await irA(page, "Posiciones");
  await expect(page.getByText("Todavía no observás ninguna dirección")).toBeVisible();
  await page.getByLabel("Dirección").fill(DIRECCION_FIXTURE);
  await expect(page.getByLabel("Red")).toHaveValue("1");
  await page.getByLabel("Nombre (opcional)").fill("Prestataria USDC");
  await page.getByRole("button", { name: "Agregar" }).click();

  // Primer snapshot.
  await expect(page.getByRole("heading", { name: "Prestataria USDC" })).toBeVisible();
  // Los snapshots son datos públicos de la dirección: si otra organización ya la leyó, el botón dice "Leer de nuevo".
  await page.getByRole("button", { name: /Obtener primer snapshot|Leer de nuevo/ }).click();
  await expect(page.getByText("1,2254")).toBeVisible();
  await expect(page.getByText("26.116.392")).toBeVisible();
  await expect(page.getByText("Datos actualizados")).toBeVisible();
  await expect(page.getByText("Sin política de health factor")).toBeVisible();
  await capturar(page, "03-posicion-detalle");

  // Política y canal probado. El plan está a la vista: prueba de 14 días, uso y precio como hipótesis.
  await irA(page, "Configuración");
  await expect(page.getByText("Piloto de lectura")).toBeVisible();
  await expect(page.getByText("1 de 10")).toBeVisible();
  await expect(page.getByText(/La prueba termina el/)).toBeVisible();
  await page.getByLabel("Umbral de health factor").fill("1.5");
  await page.getByRole("button", { name: "Crear política" }).click();
  await expect(page.getByText("Health factor menor a 1,5; se despeja sobre 1,575.")).toBeVisible();
  await page.getByRole("button", { name: "Crear canal" }).click();
  await expect(page.getByText("Sin probar")).toBeVisible();
  await page.getByRole("button", { name: /Enviar prueba/ }).click();
  await expect(page.getByText("La prueba llegó al canal.")).toBeVisible();
  await expect(page.getByText(/^Probado/)).toBeVisible();
  await capturar(page, "04-configuracion");

  // El worker evalúa y abre el incidente; la interfaz se entera por el stream.
  await irA(page, "Posiciones");
  await page.getByRole("link", { name: /Prestataria USDC/ }).click();
  await page.getByRole("button", { name: "Evaluar políticas ahora" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Evaluación en cola|Ya había una evaluación/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Alta: Health factor 1,2254 por debajo del umbral 1,5/ })).toBeVisible({ timeout: 30_000 });

  await irA(page, "Incidentes");
  await expect(page.getByLabel("1 activos")).toBeVisible();
  await page.getByRole("link", { name: /Health factor bajo/ }).click();
  await expect(page.getByText("Health factor 1,2254 por debajo del umbral 1,5.")).toBeVisible();
  await expect(page.getByText("Sin asignar")).toBeVisible();
  await expect(page.getByText("Versión 1", { exact: true })).toBeVisible();
  await expect(page.getByText("Canal de prueba")).toBeVisible();
  // Explicación por plantilla, con referencias; sin modelo habilitado no hay costo.
  await expect(page.getByText("Plantilla determinista")).toBeVisible();
  await expect(page.getByText(/\[snapshot:\d+, rule_version:1\]/).first()).toBeVisible();
  await page.getByRole("button", { name: "Generar explicación" }).click();
  await expect(page.getByText(/el modelo no está habilitado/)).toBeVisible();
  await capturar(page, "05-incidente-abierto");

  // Seguimiento y resolución.
  await page.getByRole("button", { name: "Tomar el incidente" }).click();
  await expect(page.getByText("En seguimiento", { exact: true })).toBeVisible();
  await expect(page.locator("dt", { hasText: "Responsable" }).locator("+ dd")).toHaveText(email);
  await page.getByLabel("Nota de resolución").fill("Repagué parte de la deuda; sigo mirando el umbral.");
  await page.getByRole("button", { name: "Resolver" }).click();
  await expect(page.getByText("Resuelto", { exact: true })).toBeVisible();
  await expect(page.locator("p", { hasText: "Nota de resolución:" })).toContainText("Repagué parte de la deuda; sigo mirando el umbral.");
  await capturar(page, "06-incidente-resuelto");

  await irA(page, "Incidentes");
  await expect(page.getByText("No hay incidentes activos")).toBeVisible();
  await page.getByRole("tab", { name: "Resueltos" }).click();
  await expect(page.getByRole("link", { name: /Health factor bajo/ })).toBeVisible();

  // Con todo hecho, la checklist desaparece del resumen.
  await irA(page, "Resumen");
  await expect(page.getByText(/Primeros pasos/)).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`/app/${org}/resumen$`));
  await capturar(page, "07-resumen-activado");
});
