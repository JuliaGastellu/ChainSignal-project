import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiSimulada, montarEnApp, ORG } from "@/test/montar";
import IncidenteDetalle from "./IncidenteDetalle";
import Posiciones from "./Posiciones";
import Resumen from "./Resumen";

const RESUMEN = {
  organization: { id: ORG, name: "Equipo", is_demo: false, expires_at: null },
  accounts: 1,
  accounts_by_data_quality: { FRESH: 1 },
  active_incidents: 1,
  active_incidents_by_severity: { high: 1 },
  enabled_policies: 1,
  channels: 1,
  verified_channels: 1,
  last_evaluation_at: null,
  checklist: { account_added: true, first_snapshot: true, policy_created: true, channel_verified: true, incident_reviewed: false },
};

const CUENTA = {
  id: "c-1",
  chain_id: 1,
  address: "0x" + "a".repeat(40),
  label: "Tesorería",
  priority: "medium",
  interval_seconds: 300,
  relationship: "observed",
  created_at: 0,
  last_evaluation_at: null,
  last_data_quality: "FRESH",
};

const INCIDENTE = {
  id: "i-1",
  account_id: "c-1",
  policy_id: "p-1",
  policy_version: 2,
  rule_type: "health_factor_below",
  status: "open",
  severity: "high",
  escalation_level: 0,
  data_quality: "FRESH",
  opened_at: 1_700_000_000,
  escalated_at: null,
  acknowledged_at: null,
  acknowledged_by_user_id: null,
  resolved_at: null,
  resolved_by_user_id: null,
  resolution: null,
  resolution_note: null,
  last_evaluated_at: 1_700_000_000,
  last_observed: { health_factor: "1.37", threshold: "1.5", clear_above: "1.6" },
  evidence: [
    { id: 1, kind: "opening", snapshot_id: 9, block_number: 20_000_000, block_hash: "0xabc", observed: {}, data_quality: "FRESH", note: null,
      corrects_evidence_id: null, created_at: 1_700_000_000, created_by_user_id: null },
  ],
  alerts: [],
  deliveries: [],
};

const base = {
  [`GET /orgs/${ORG}/summary`]: [200, RESUMEN] as [number, unknown],
  [`GET /orgs/${ORG}/accounts`]: [200, { accounts: [CUENTA] }] as [number, unknown],
  [`GET /orgs/${ORG}/members`]: [200, { members: [{ membership_id: "m-1", user_id: "u-1", email: "persona@ejemplo.test", role: "owner", created_at: 0 }] }] as [number, unknown],
  [`GET /orgs/${ORG}/channels`]: [200, { channels: [] }] as [number, unknown],
  [`GET /orgs/${ORG}/incidents/i-1`]: [200, INCIDENTE] as [number, unknown],
  [`GET /orgs/${ORG}/incidents/i-1/explanation`]: [200, {
    incident_id: "i-1", source: "template", model: null, validation_errors: [], fallback_reason: "not_generated", cost_usd: "0",
    created_at: null,
    explanation: { summary: "El health factor (1,37) está por debajo del umbral 1,5.",
                   statements: [{ text: "El health factor fue 1,37.", refs: ["snapshot:9", "rule_version:2"] }], caveats: [] },
  }] as [number, unknown],
};

describe("páginas de la app", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("el resumen muestra la checklist pendiente y los contadores", async () => {
    apiSimulada(base);
    montarEnApp(`/app/${ORG}/resumen`, "resumen", <Resumen />);
    expect(await screen.findByText("Primeros pasos (4 de 5)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Revisar un incidente" })).toHaveAttribute("href", `/app/${ORG}/incidentes`);
  });

  it("una cuenta sin posiciones no se muestra como error", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/accounts/c-1/positions/aave-v3/latest`]: [200, {
        account_id: "c-1", status: "NO_POSITION", no_debt: true, data_quality: { status: "FRESH", reason: "none", detail: "" },
        read_at: Date.now() / 1000, block: null, assets: [], limitations: [], synthetic: false,
      }],
    });
    montarEnApp(`/app/${ORG}/posiciones`, "posiciones", <Posiciones />);
    expect(await screen.findByText("Sin posiciones en Aave V3")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("una cuenta sin snapshot muestra 'sin lectura', no un error", async () => {
    apiSimulada(base);
    montarEnApp(`/app/${ORG}/posiciones`, "posiciones", <Posiciones />);
    expect(await screen.findByText("Sin lectura todavía")).toBeInTheDocument();
  });

  it("sin cuentas muestra el estado vacío y valida la dirección antes de enviar", async () => {
    const llamadas = apiSimulada({ ...base, [`GET /orgs/${ORG}/accounts`]: [200, { accounts: [] }] });
    montarEnApp(`/app/${ORG}/posiciones`, "posiciones", <Posiciones />);
    expect(await screen.findByText("Todavía no observás ninguna dirección")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Dirección"), { target: { value: "0x123" } });
    fireEvent.click(screen.getByRole("button", { name: "Agregar" }));
    expect(await screen.findByText(/40 caracteres hexadecimales/)).toBeInTheDocument();
    expect(llamadas.some((l) => l.metodo === "POST")).toBe(false);
  });

  it("un 403 en la lista se explica como falta de permiso", async () => {
    apiSimulada({ ...base, [`GET /orgs/${ORG}/accounts`]: [403, { error: "forbidden", message: "no" }] });
    montarEnApp(`/app/${ORG}/posiciones`, "posiciones", <Posiciones />, "viewer");
    expect(await screen.findByText("Sin permiso")).toBeInTheDocument();
    expect(screen.queryByLabelText("Dirección")).toBeNull();
  });

  it("el detalle del incidente muestra condición, bloque, umbral y responsable", async () => {
    apiSimulada(base);
    montarEnApp(`/app/${ORG}/incidentes/i-1`, "incidentes/:incidente", <IncidenteDetalle />);
    expect(await screen.findByText("1,37")).toBeInTheDocument();
    expect(screen.getByText(/Menor a 1,5/)).toBeInTheDocument();
    expect(screen.getByText("20.000.000")).toBeInTheDocument();
    expect(screen.getByText("Sin asignar")).toBeInTheDocument();
    expect(screen.getByText("Versión 2")).toBeInTheDocument();
  });

  it("muestra la explicación con sus referencias y el motivo del fallback", async () => {
    apiSimulada({
      ...base,
      [`POST /orgs/${ORG}/incidents/i-1/explanation`]: [201, {
        incident_id: "i-1", source: "template", model: "m", validation_errors: ["figures: unsupported figure 0,98"],
        fallback_reason: "validation_failed", cost_usd: "0.006", created_at: 1,
        explanation: { summary: "Resumen de plantilla.", statements: [{ text: "Enunciado.", refs: ["rule_version:2"] }], caveats: [] },
      }],
    });
    montarEnApp(`/app/${ORG}/incidentes/i-1`, "incidentes/:incidente", <IncidenteDetalle />, "operator");
    expect(await screen.findByText("Plantilla determinista")).toBeInTheDocument();
    expect(screen.getByText("[snapshot:9, rule_version:2]")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Generar explicación" }));
    expect(await screen.findByText(/la salida del modelo no pasó la validación/)).toBeInTheDocument();
  });

  it("una persona de solo lectura no ve acciones sobre el incidente", async () => {
    apiSimulada(base);
    montarEnApp(`/app/${ORG}/incidentes/i-1`, "incidentes/:incidente", <IncidenteDetalle />, "viewer");
    expect(await screen.findByText(/Tu rol es de lectura/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tomar el incidente" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Generar explicación" })).toBeNull();
  });

  it("si la API rechaza el acknowledgement no muestra éxito", async () => {
    const llamadas = apiSimulada({
      ...base,
      [`POST /orgs/${ORG}/incidents/i-1/acknowledge`]: [409, { error: "conflict", message: "Incident is acknowledged; only open incidents can be acknowledged." }],
    });
    montarEnApp(`/app/${ORG}/incidentes/i-1`, "incidentes/:incidente", <IncidenteDetalle />, "operator");
    fireEvent.click(await screen.findByRole("button", { name: "Tomar el incidente" }));
    expect(await screen.findByText("Cambió mientras lo mirabas")).toBeInTheDocument();
    expect(screen.getByText("Abierto")).toBeInTheDocument();
    expect(llamadas.filter((l) => l.metodo === "POST")).toHaveLength(1);
  });

  it("un 429 al resolver indica cuánto esperar", async () => {
    apiSimulada({
      ...base,
      [`POST /orgs/${ORG}/incidents/i-1/resolve`]: () => [429, { error: "rate_limited", message: "slow down" }],
    });
    montarEnApp(`/app/${ORG}/incidentes/i-1`, "incidentes/:incidente", <IncidenteDetalle />, "operator");
    fireEvent.change(await screen.findByLabelText("Nota de resolución"), { target: { value: "Repagué deuda" } });
    fireEvent.click(screen.getByRole("button", { name: "Resolver" }));
    await waitFor(() => expect(screen.getByText("Demasiadas solicitudes")).toBeInTheDocument());
  });
});
