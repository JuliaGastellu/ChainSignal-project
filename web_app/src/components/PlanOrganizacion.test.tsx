import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { crearQueryClient } from "@/lib/consultas";
import Landing from "@/pages/Landing";
import { apiSimulada, montarEnApp, ORG } from "@/test/montar";
import Configuracion from "@/pages/app/Configuracion";

const AHORA = 1_800_000_000;

function suscripcion(cambios: Record<string, unknown> = {}) {
  return {
    plan: { id: "pilot", name: "Piloto de lectura", guided_onboarding: true, reference_price_usd_per_month: "150",
            price_is_hypothesis: true, billing: "assisted_invoice" },
    status: "trialing", service_active: true, is_demo: false, trial_ends_at: AHORA + 10 * 86400, current_period_end: null,
    grace_ends_at: null, cancel_at_period_end: false, canceled_at: null,
    limits: { max_accounts: 10, min_interval_seconds: 60, chains: [1], markets: ["aave-v3-ethereum"] },
    usage: { accounts: 3 }, confirmed_payments: [], server_time: AHORA, ...cambios,
  };
}

const base = (sub: unknown) => ({
  [`GET /orgs/${ORG}/summary`]: [200, { organization: { id: ORG, name: "Equipo", is_demo: false, expires_at: null }, active_incidents: 0 }] as [number, unknown],
  [`GET /orgs/${ORG}/subscription`]: [200, sub] as [number, unknown],
  [`GET /orgs/${ORG}/policies`]: [200, { policies: [] }] as [number, unknown],
  [`GET /orgs/${ORG}/channels`]: [200, { channels: [] }] as [number, unknown],
  [`GET /orgs/${ORG}/members`]: [200, { members: [] }] as [number, unknown],
});

describe("plan de la organización", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("muestra prueba, uso, límites y el precio como hipótesis", async () => {
    apiSimulada(base(suscripcion()));
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />);
    expect(await screen.findByText("Prueba")).toBeInTheDocument();
    expect(screen.getByText("3 de 10")).toBeInTheDocument();
    expect(screen.getByText(/Precio de piloto en validación, no tarifa definitiva/)).toBeInTheDocument();
    expect(screen.getByText(/No pedimos tarjeta ni cobramos de forma automática/)).toBeInTheDocument();
  });

  it("cancelar pide confirmación y muestra la cancelación programada", async () => {
    const llamadas = apiSimulada({
      ...base(suscripcion()),
      [`POST /orgs/${ORG}/subscription/cancel`]: [200, suscripcion({ cancel_at_period_end: true, canceled_at: AHORA })],
    });
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />, "owner");
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar el plan" }));
    expect(llamadas.some((l) => l.metodo === "POST")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Confirmar cancelación" }));
    expect(await screen.findAllByText("Prueba con cancelación programada")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: /Mantener el plan/ })).toBeInTheDocument();
  });

  it("una persona operadora no puede cancelar", async () => {
    apiSimulada(base(suscripcion()));
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />, "operator");
    await screen.findByText("3 de 10");
    expect(screen.queryByRole("button", { name: "Cancelar el plan" })).toBeNull();
  });

  it("sin servicio, el aviso es visible en toda la app", async () => {
    apiSimulada(base(suscripcion({ status: "expired", service_active: false })));
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />);
    const avisos = await screen.findAllByText(/El monitoreo está pausado/);
    expect(avisos.length).toBeGreaterThanOrEqual(2); // aviso global y tarjeta del plan
  });
});

describe("landing", () => {
  afterEach(() => vi.unstubAllGlobals());

  function montarLanding() {
    return render(
      <QueryClientProvider client={crearQueryClient()}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Landing />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("no promete evitar pérdidas ni certificaciones y marca el ejemplo como sintético", () => {
    apiSimulada({});
    const { container } = montarLanding();
    const texto = container.textContent ?? "";
    expect(texto).not.toMatch(/evita(mos)? (las )?pérdidas|garantiza|certificad[oa] por|auditado por/i);
    expect(screen.getByText("Ejemplo de incidente").closest("figure")).toHaveTextContent("Datos sintéticos");
    expect(texto).toContain("no una tarifa definitiva");
  });

  it("el contacto exige consentimiento antes de enviar", async () => {
    const llamadas = apiSimulada({ "POST /contact": [201, { status: "received" }] });
    montarLanding();
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "persona@ejemplo.test" } });
    fireEvent.change(screen.getByLabelText("Mensaje"), { target: { value: "Quiero un piloto." } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(/Necesito tu consentimiento/)).toBeInTheDocument();
    expect(llamadas.some((l) => l.ruta === "/contact")).toBe(false);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    await waitFor(() => expect(screen.getByText(/Recibí tu mensaje/)).toBeInTheDocument());
    expect(JSON.parse(llamadas.find((l) => l.ruta === "/contact")!.cuerpo!)).toMatchObject({ consent: true });
  });
});
