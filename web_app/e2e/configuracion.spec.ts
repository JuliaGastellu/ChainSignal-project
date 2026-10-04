import { expect, test, type Browser } from "@playwright/test";
import { capturar, CONTRASENA, crearOrganizacion, crearPoliticaHF, crearWebhook, emailUnico, irA, WEBHOOK_FALLA } from "./ayudantes";

// Invito a alguien con un rol y acepto la invitación en otro navegador.
async function invitarYAceptar(browser: Browser, page: import("@playwright/test").Page, rol: "viewer" | "operator") {
  const email = emailUnico(rol === "viewer" ? "lectura" : "operacion");
  const personas = page.getByRole("region", { name: "Personas" });
  await personas.getByLabel("Email de la persona").fill(email);
  await personas.locator("#rol-invitacion").selectOption(rol);
  await personas.getByRole("button", { name: "Invitar" }).click();
  await expect(personas.getByRole("status")).toContainText(`Invitación creada para ${email}.`);
  const enlace = (await personas.locator("code").textContent()) ?? "";
  expect(enlace).toContain("/invitacion#token=");
  const contexto = await browser.newContext();
  const invitada = await contexto.newPage();
  await invitada.goto(new URL(enlace).pathname + new URL(enlace).hash);
  await invitada.getByLabel(/Contraseña/).fill(CONTRASENA);
  await invitada.getByRole("button", { name: "Crear cuenta y aceptar" }).click();
  await expect(invitada).toHaveURL(/\/app\/[0-9a-f]+\/resumen$/);
  return { contexto, invitada, email };
}

test("dueña, operación y lectura: cada rol ve y puede lo suyo", async ({ browser, page }) => {
  const { org } = await crearOrganizacion(page, "Equipo de roles");
  await irA(page, "Configuración");
  await crearPoliticaHF(page, "1.4");

  const lectura = await invitarYAceptar(browser, page, "viewer");
  const operacion = await invitarYAceptar(browser, page, "operator");

  // Lectura: ve políticas y personas, sin acciones.
  await lectura.invitada.goto(`/app/${org}/configuracion`);
  await expect(lectura.invitada.getByText("Health factor menor a 1,4;", { exact: false })).toBeVisible();
  await expect(lectura.invitada.getByRole("button", { name: "Nueva política" })).toHaveCount(0);
  await expect(lectura.invitada.getByRole("button", { name: "Editar" })).toHaveCount(0);
  await expect(lectura.invitada.getByLabel("Email de la persona")).toHaveCount(0);

  // Operación: edita la política (nueva versión), la pausa y la reactiva; no crea canales ni invita.
  const op = operacion.invitada;
  await op.goto(`/app/${org}/configuracion`);
  await op.getByRole("button", { name: "Editar" }).click();
  await op.getByLabel("Umbral de alerta (health factor)").fill("1.3");
  await op.getByRole("button", { name: "Ver cuándo abre y cuándo despeja" }).click();
  await expect(op.getByText(/Abre cuando el health factor queda por debajo de 1,3/)).toBeVisible();
  await op.getByRole("button", { name: "Guardar como versión nueva" }).click();
  await expect(op.getByText("v2", { exact: true })).toBeVisible();
  await op.getByRole("button", { name: "Pausar" }).click();
  await expect(op.getByText(/no abre incidentes nuevos/)).toBeVisible();
  await op.getByRole("button", { name: "Confirmar pausa" }).click();
  await expect(op.getByText("Pausada", { exact: true })).toBeVisible();
  await op.getByRole("button", { name: "Reactivar" }).click();
  await expect(op.getByText("Habilitada", { exact: true })).toBeVisible();
  await expect(op.getByLabel("URL del webhook (https)")).toHaveCount(0);
  await expect(op.getByLabel("Email de la persona")).toHaveCount(0);
  await capturar(op, "12-configuracion-operacion");

  // Dueña: no puede dejar la organización sin responsable.
  await page.reload();
  const personas = page.getByRole("region", { name: "Personas" });
  const propia = personas.locator("li", { hasText: "(vos)" });
  await propia.getByLabel(/Rol de/).selectOption("viewer");
  await expect(personas.getByText("La organización tiene que conservar al menos una persona dueña.")).toBeVisible();
  // Y sí puede cambiar el rol de otra persona.
  await personas.locator("li", { hasText: lectura.email }).getByLabel(/Rol de/).selectOption("operator");
  await expect(personas.locator("li", { hasText: lectura.email }).getByLabel(/Rol de/)).toHaveValue("operator");
  await capturar(page, "13-configuracion-duena");

  await lectura.contexto.close();
  await operacion.contexto.close();
});

test("un webhook que falla muestra el motivo en castellano", async ({ page }) => {
  await crearOrganizacion(page, "Equipo con destino caído");
  await irA(page, "Configuración");
  await crearWebhook(page, WEBHOOK_FALLA, "Destino que falla");
  const canales = page.getByRole("region", { name: "Canales de notificación" });
  await canales.getByRole("button", { name: /Enviar prueba/ }).click();
  await expect(canales.getByText(/La prueba falló\. El destino respondió HTTP 500 \(error del destino\)\./)).toBeVisible();
  await expect(canales.getByText("Falló", { exact: true })).toBeVisible();
  // Un destino privado se rechaza al crearlo, con un motivo claro.
  await canales.getByLabel("URL del webhook (https)").fill("https://127.0.0.1/hooks");
  await canales.getByRole("button", { name: "Crear webhook" }).click();
  await expect(canales.getByText("Destino no permitido")).toBeVisible();
  await expect(canales.getByText(/dirección privada o reservada/)).toBeVisible();
  await capturar(page, "14-webhook-fallido");
});
