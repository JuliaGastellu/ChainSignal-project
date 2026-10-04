import { render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { crearQueryClient } from "@/lib/consultas";
import { useSesion } from "@/lib/sesion";
import { RequireSession } from "./RequireSession";

function Privado() {
  return <div>contenido privado de {useSesion()?.user.email}</div>;
}

function montar() {
  return render(
    <QueryClientProvider client={crearQueryClient()}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/login" element={<div>pantalla de login</div>} />
          <Route path="/" element={<RequireSession><Privado /></RequireSession>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequireSession", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("redirige al login cuando la API responde 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "not_authenticated" }), { status: 401 })));
    montar();
    await waitFor(() => expect(screen.getByText("pantalla de login")).toBeInTheDocument());
    expect(screen.queryByText(/contenido privado/)).toBeNull();
  });

  it("expone la sesión a las páginas privadas", async () => {
    const sesion = { user: { id: "u", email: "persona@ejemplo.test" }, expires_at: 0, memberships: [] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(sesion), { status: 200 })));
    montar();
    await waitFor(() => expect(screen.getByText("contenido privado de persona@ejemplo.test")).toBeInTheDocument());
  });

  it("no muestra contenido privado si la verificación falla por otra causa", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "forbidden" }), { status: 403 })));
    montar();
    await waitFor(() => expect(screen.getByText(/No pudimos verificar tu sesión/)).toBeInTheDocument());
    expect(screen.getByText("Sin permiso")).toBeInTheDocument();
    expect(screen.queryByText(/contenido privado/)).toBeNull();
  });
});
