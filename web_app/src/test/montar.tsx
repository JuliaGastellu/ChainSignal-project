// Monta páginas de la app con una API simulada por ruta. Cada respuesta se
// define como [estado, cuerpo]; una ruta no definida responde 404.

import { render } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { crearQueryClient } from "@/lib/consultas";
import { SesionContext } from "@/lib/sesion";
import { AppLayout } from "@/components/AppLayout";
import type { Rol } from "@/lib/tipos";

export type Respuestas = Record<string, [number, unknown] | (() => [number, unknown])>;

export function apiSimulada(respuestas: Respuestas) {
  const llamadas: { metodo: string; ruta: string; cuerpo?: string }[] = [];
  const fetchMock = vi.fn(async (url: string, init: RequestInit = {}) => {
    const metodo = (init.method ?? "GET").toUpperCase();
    const ruta = url.replace(/\?.*$/, "");
    llamadas.push({ metodo, ruta: url, cuerpo: init.body as string | undefined });
    const definida = respuestas[`${metodo} ${ruta}`] ?? respuestas[`${metodo} ${url}`];
    const [estado, cuerpo] = typeof definida === "function" ? definida() : (definida ?? [404, { error: "not_found", message: "no" }]);
    return new Response(JSON.stringify(cuerpo), { status: estado, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return llamadas;
}

export const ORG = "org-1";

export function montarEnApp(ruta: string, patron: string, pagina: ReactElement, rol: Rol = "owner") {
  const sesion = {
    user: { id: "u-1", email: "persona@ejemplo.test" },
    expires_at: 0,
    memberships: [{ organization_id: ORG, organization_name: "Equipo", role: rol, membership_id: "m-1" }],
  };
  return render(
    <QueryClientProvider client={crearQueryClient()}>
      <SesionContext.Provider value={sesion}>
        <MemoryRouter initialEntries={[ruta]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            <Route path="/app/:org" element={<AppLayout />}>
              <Route path={patron} element={pagina} />
            </Route>
            <Route path="/login" element={<div>pantalla de login</div>} />
          </Routes>
        </MemoryRouter>
      </SesionContext.Provider>
    </QueryClientProvider>,
  );
}
