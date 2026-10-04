import { expect, test } from "@playwright/test";
import { capturar } from "./ayudantes";

test("la landing explica alcance, permisos y piloto, y el contacto llega al backend", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alcance y permisos" })).toBeVisible();
  await expect(page.getByText(/no una tarifa definitiva/)).toBeVisible();
  await expect(page.locator("figure").getByText("Datos sintéticos")).toBeVisible();
  await page.getByText("¿ChainSignal puede mover mis fondos?").click();
  await expect(page.getByText(/No pido claves, firmas ni conexión de wallet/)).toBeVisible();
  await capturar(page, "11-landing-comercial");

  await page.getByLabel("Email", { exact: true }).fill("piloto@ejemplo.test");
  await page.getByLabel("Mensaje", { exact: true }).fill("Tenemos 4 posiciones en Aave V3 y las revisamos a mano.");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Enviar" }).click();
  await expect(page.getByText(/Recibí tu mensaje/)).toBeVisible();
});
