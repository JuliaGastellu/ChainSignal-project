import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { crearQueryClient } from "@/lib/consultas";
import { apiSimulada } from "@/test/montar";
import Invitacion from "./Invitacion";

function montar(ruta: string) {
  return render(
    <QueryClientProvider client={crearQueryClient()}>
      <MemoryRouter initialEntries={[ruta]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/invitacion" element={<Invitacion />} />
          <Route path="/app/:org/resumen" element={<div>resumen de la organización</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("aceptar invitación", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sin token explica que el enlace no sirve", () => {
    apiSimulada({ "GET /auth/session": [401, { error: "not_authenticated", message: "no" }] });
    montar("/invitacion");
    expect(screen.getByText(/no tiene una invitación válida/)).toBeInTheDocument();
  });

  it("una persona nueva elige contraseña y entra a la organización", async () => {
    const llamadas = apiSimulada({
      "GET /auth/session": [401, { error: "not_authenticated", message: "no" }],
      "POST /invitations/accept": [200, { organization_id: "org-9", user_id: "u-9", new_user: true }],
    });
    montar("/invitacion#token=token-de-invitacion-123");
    fireEvent.change(await screen.findByLabelText(/Contraseña/), { target: { value: "contrasena-larga-segura" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta y aceptar" }));
    expect(await screen.findByText("resumen de la organización")).toBeInTheDocument();
    const cuerpo = JSON.parse(llamadas.find((l) => l.ruta === "/invitations/accept")!.cuerpo!);
    expect(cuerpo).toEqual({ token: "token-de-invitacion-123", password: "contrasena-larga-segura" });
  });

  it("si el email ya tiene cuenta, pide iniciar sesión y volver al enlace", async () => {
    apiSimulada({
      "GET /auth/session": [401, { error: "not_authenticated", message: "no" }],
      "POST /invitations/accept": [401, { error: "not_authenticated", message: "Log in with the invited email to accept this invitation." }],
    });
    montar("/invitacion#token=token-de-invitacion-123");
    fireEvent.change(await screen.findByLabelText(/Contraseña/), { target: { value: "contrasena-larga-segura" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta y aceptar" }));
    const enlace = await screen.findByRole("link", { name: "Iniciá sesión" });
    expect(enlace).toHaveAttribute("href", `/login?siguiente=${encodeURIComponent("/invitacion#token=token-de-invitacion-123")}`);
  });
});
