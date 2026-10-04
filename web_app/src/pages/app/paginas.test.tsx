import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiSimulada, montarEnApp, ORG } from "@/test/montar";
import Configuracion from "./Configuracion";
import IncidenteDetalle from "./IncidenteDetalle";
import PosicionDetalle from "./PosicionDetalle";
import Posiciones from "./Posiciones";
import Resumen from "./Resumen";

const AHORA = Date.now() / 1000;
type R = [number, unknown];

const CUENTA = {
  id: "c-1", chain_id: 1, address: "0x" + "a".repeat(40), label: "Tesorería", priority: "medium", interval_seconds: 300,
  relationship: "observed", created_at: 0, last_evaluation_at: AHORA - 60, last_data_quality: "FRESH",
};

function posicion(cambios: Record<string, unknown> = {}) {
  return {
    account_id: "c-1", status: "ACTIVE", no_debt: false, health_factor: "1.2254", debt_base: "39378.56", collateral_base: "58138.96",
    available_borrows_base: "7423.3", liquidation_threshold_pct: "83", data_quality: { status: "FRESH", reason: "none", detail: "" },
    read_at: AHORA - 30, block: { number: 26_116_392, hash: "0xabc", timestamp: AHORA - 60 }, assets: [],
    limitations: ["Addresses resolved on-chain from PoolAddressesProvider; reference: bgd-labs/aave-address-book."], synthetic: false, ...cambios,
  };
}

const INCIDENTE = {
  id: "i-1", account_id: "c-1", policy_id: "p-1", policy_version: 2, rule_type: "health_factor_below", status: "open", severity: "high",
  escalation_level: 0, data_quality: "FRESH", opened_at: AHORA - 600, escalated_at: null, acknowledged_at: null, acknowledged_by_user_id: null,
  resolved_at: null, resolved_by_user_id: null, resolution: null, resolution_note: null, last_evaluated_at: AHORA - 60,
  last_observed: { health_factor: "1.2254", threshold: "1.5", clear_above: "1.575" },
  evidence: [{ id: 1, kind: "opening", snapshot_id: 9, block_number: 20_000_000, block_hash: "0xabc", observed: {}, data_quality: "FRESH",
               note: null, corrects_evidence_id: null, created_at: AHORA - 600, created_by_user_id: null }],
  alerts: [],
  deliveries: [{ alert_id: "a-1", channel_id: "ch-1", channel_kind: "sandbox", status: "sent", outcome: "simulated", attempts: 1, sent_at: AHORA - 590, last_error: null }],
};

function preparacion(cambios: Record<string, unknown> = {}) {
  return {
    account_observed: true, valid_read: true, policy_enabled: true, external_channel_verified: false, ready: false, simulated: false,
    configured: false, issues: { valid_read: null, policy_enabled: null, external_channel_verified: "none" }, ...cambios,
  };
}

function resumen(cambios: Record<string, unknown> = {}) {
  return {
    organization: { id: ORG, name: "Equipo", is_demo: false, expires_at: null },
    attention: [], accounts: 1, accounts_by_data_quality: { FRESH: 1 }, active_incidents: 0, active_incidents_by_severity: {},
    enabled_policies: 1, last_evaluation_at: AHORA - 60, practice: { incident_reviewed: false },
    readiness: preparacion(),
    channels: { total: 1, simulated: 1, external: 0, external_verified: 0, webhooks_enabled: true },
    ...cambios,
  };
}

const CANAL_SANDBOX = { id: "ch-1", kind: "sandbox", name: "Canal simulado", config: {}, enabled: true, verified_at: null, created_at: 0, last_test: null };

const base: Record<string, R> = {
  [`GET /orgs/${ORG}/summary`]: [200, resumen()],
  [`GET /orgs/${ORG}/accounts`]: [200, { accounts: [CUENTA] }],
  [`GET /orgs/${ORG}/incidents`]: [200, { incidents: [] }],
  [`GET /orgs/${ORG}/members`]: [200, { members: [{ membership_id: "m-1", user_id: "u-1", email: "persona@ejemplo.test", role: "owner", created_at: 0 }] }],
  [`GET /orgs/${ORG}/channels`]: [200, { channels: [CANAL_SANDBOX], webhooks_enabled: false }],
  [`GET /orgs/${ORG}/policies`]: [200, { policies: [] }],
  [`GET /orgs/${ORG}/invitations`]: [200, { invitations: [] }],
  [`GET /orgs/${ORG}/incidents/i-1`]: [200, INCIDENTE],
  [`GET /orgs/${ORG}/accounts/c-1/positions/aave-v3/latest`]: [200, posicion()],
  [`GET /orgs/${ORG}/incidents/i-1/explanation`]: [200, {
    incident_id: "i-1", source: "template", model: null, validation_errors: [], fallback_reason: "not_generated", cost_usd: "0", created_at: null,
    explanation: { summary: "El health factor (1,2254) está por debajo del umbral 1,5.",
                   statements: [{ text: "El health factor fue 1,2254.", refs: ["snapshot:9", "rule_version:2", "evidence:1"] }], caveats: [] },
  }],
};

describe("Resumen", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("pone primero el incidente abierto, con motivo, frescura y enlace", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/summary`]: [200, resumen({
        active_incidents: 1,
        attention: [{ kind: "incident", incident_id: "i-1", account_id: "c-1", account_label: "Tesorería", account_address: CUENTA.address,
                      rule_type: "health_factor_below", severity: "high", status: "open", observed: INCIDENTE.last_observed,
                      data_quality: "FRESH", opened_at: AHORA - 600, last_evaluated_at: AHORA - 60 }],
      })],
    });
    montarEnApp(`/app/${ORG}/resumen`, "resumen", <Resumen />);
    const lista = await screen.findByRole("list", { name: "Elementos que necesitan atención" });
    expect(within(lista).getByText("Health factor 1,2254 por debajo del umbral de alerta 1,5.")).toBeInTheDocument();
    expect(within(lista).getByText(/dato actualizado/)).toBeInTheDocument();
    expect(within(lista).getByRole("link", { name: "Revisar el incidente" })).toHaveAttribute("href", `/app/${ORG}/incidentes/i-1`);
  });

  it("una posición sana puede quedar preparada sin incidentes y la preparación se reduce a una línea", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/summary`]: [200, resumen({ readiness: preparacion({ external_channel_verified: true, ready: true, configured: true,
                                                                  issues: { valid_read: null, policy_enabled: null, external_channel_verified: null } }) })],
    });
    montarEnApp(`/app/${ORG}/resumen`, "resumen", <Resumen />);
    expect(await screen.findByText(/Nada requiere atención ahora/)).toBeInTheDocument();
    expect(screen.getByText("Monitoreo preparado")).toBeInTheDocument();
    expect(screen.queryByText(/Siguiente paso/)).toBeNull();
  });

  it("sin canal externo indica el siguiente paso y explica si los webhooks están deshabilitados", async () => {
    apiSimulada({ ...base, [`GET /orgs/${ORG}/summary`]: [200, resumen({
      channels: { total: 1, simulated: 1, external: 0, external_verified: 0, webhooks_enabled: false },
      readiness: preparacion({ issues: { valid_read: null, policy_enabled: null, external_channel_verified: "webhooks_disabled" } }),
    })] });
    montarEnApp(`/app/${ORG}/resumen`, "resumen", <Resumen />);
    expect(await screen.findByText("Monitoreo preparado: 3 de 4")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver por qué no hay envíos externos" })).toBeInTheDocument();
    expect(screen.getByText(/tiene apagados los envíos externos/)).toBeInTheDocument();
    expect(screen.getByText(/1 canal\(es\) simulados no cuentan/)).toBeInTheDocument();
  });

  it("datos no disponibles: lo dice y ofrece el siguiente paso", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/summary`]: [200, resumen({
        attention: [{ kind: "data", account_id: "c-1", account_label: "Tesorería", account_address: CUENTA.address, data_quality: "UNAVAILABLE",
                      stale: false, last_evaluated_at: AHORA - 60 }],
      })],
    });
    montarEnApp(`/app/${ORG}/resumen`, "resumen", <Resumen />);
    expect(await screen.findByText("Dato no disponible")).toBeInTheDocument();
    expect(screen.getByText(/Sin datos no puedo decir si la posición está bien/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver la cuenta y reintentar la lectura" })).toBeInTheDocument();
  });

  it("en la demo dice que el recorrido es simulado y no ofrece práctica", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/summary`]: [200, resumen({ organization: { id: ORG, name: "Demo", is_demo: true, expires_at: AHORA + 3600 },
                                                    readiness: preparacion({ simulated: true }) })],
    });
    montarEnApp(`/app/${ORG}/resumen`, "resumen", <Resumen />);
    expect(await screen.findByText(/No cuenta como preparación del monitoreo de una organización real/)).toBeInTheDocument();
    expect(screen.getByText("Demo del monitoreo")).toBeInTheDocument();
    expect(screen.queryByText(/Monitoreo preparado/)).toBeNull();
    expect(screen.queryByText("Practicar un incidente (opcional)")).toBeNull();
  });

  it("configuración completa pero dato no disponible: no dice preparado y da el siguiente paso", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/summary`]: [200, resumen({ readiness: preparacion({ valid_read: false, external_channel_verified: true, configured: true,
        issues: { valid_read: "unavailable", policy_enabled: null, external_channel_verified: null } }) })],
    });
    montarEnApp(`/app/${ORG}/resumen`, "resumen", <Resumen />);
    expect(await screen.findByText("Monitoreo no disponible ahora")).toBeInTheDocument();
    expect(screen.queryByText("Monitoreo preparado")).toBeNull();
    expect(screen.getByText(/La última lectura falló/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver las cuentas y reintentar la lectura" })).toBeInTheDocument();
  });

  it("configuración completa con envíos apagados después de una prueba aceptada", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/summary`]: [200, resumen({ readiness: preparacion({ configured: true,
        issues: { valid_read: null, policy_enabled: null, external_channel_verified: "webhooks_disabled" } }) })],
    });
    montarEnApp(`/app/${ORG}/resumen`, "resumen", <Resumen />);
    expect(await screen.findByText("Monitoreo no disponible ahora")).toBeInTheDocument();
    expect(screen.getByText(/tiene apagados los envíos externos/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver por qué no hay envíos externos" })).toBeInTheDocument();
  });
});

describe("Posiciones", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("una cuenta con incidente de HF abierto muestra su alerta; la deuda es neutra", async () => {
    apiSimulada({ ...base, [`GET /orgs/${ORG}/incidents`]: [200, { incidents: [INCIDENTE] }] });
    montarEnApp(`/app/${ORG}/posiciones`, "posiciones", <Posiciones />);
    expect(await screen.findByText("Alerta abierta: health factor bajo el umbral")).toBeInTheDocument();
    expect(screen.getByText("Posición con deuda").closest("span")).toHaveClass("text-foreground/85"); // tono neutro
    expect(screen.getByText("Dato actualizado")).toBeInTheDocument();
  });

  it("dato atrasado: se marca aparte y no oculta la alerta", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/incidents`]: [200, { incidents: [] }],
      [`GET /orgs/${ORG}/accounts/c-1/positions/aave-v3/latest`]: [200, posicion({ read_at: AHORA - 7200, data_quality: { status: "STALE", reason: "timeout", detail: "" } })],
    });
    montarEnApp(`/app/${ORG}/posiciones`, "posiciones", <Posiciones />);
    expect(await screen.findByText("Dato atrasado")).toBeInTheDocument();
    expect(screen.getByText("Sin alertas abiertas")).toBeInTheDocument();
  });

  it("el detalle diferencia umbral de alerta y liquidación, y traduce los límites", async () => {
    apiSimulada({ ...base, [`GET /orgs/${ORG}/incidents`]: [200, { incidents: [INCIDENTE] }] });
    montarEnApp(`/app/${ORG}/posiciones/c-1`, "posiciones/:cuenta", <PosicionDetalle />);
    expect(await screen.findByRole("region", { name: "Alertas abiertas" })).toBeInTheDocument();
    expect(screen.getByText(/Aave permite liquidar una posición cuando el health factor queda por debajo de 1/)).toBeInTheDocument();
    expect(screen.getByText("Direcciones de los contratos de Aave tomadas de bgd-labs/aave-address-book.")).toBeInTheDocument();
    expect(screen.getByText(/Addresses resolved on-chain/).closest("details")).not.toHaveAttribute("open");
  });

  it("si la primera lectura falla, muestra el dato no disponible en lugar de 'sin lectura'", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/accounts/c-1/positions/aave-v3/latest`]: [404, { error: "not_found", message: "No snapshot yet for this account." }],
      [`GET /orgs/${ORG}/accounts/c-1/positions/aave-v3`]: [200, posicion({ status: "UNKNOWN", health_factor: null, debt_base: null, block: null,
        data_quality: { status: "UNAVAILABLE", reason: "invalid_response", detail: "eth_call not recorded" }, limitations: [] })],
    });
    montarEnApp(`/app/${ORG}/posiciones/c-1`, "posiciones/:cuenta", <PosicionDetalle />);
    fireEvent.click(await screen.findByRole("button", { name: "Obtener primer snapshot" }));
    expect(await screen.findByText("Dato no disponible")).toBeInTheDocument();
    expect(screen.getByText("Actividad desconocida")).toBeInTheDocument();
    expect(screen.getByText(/Esto no indica que la cuenta esté sana/)).toBeInTheDocument();
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

  it("un 403 se explica como falta de permiso", async () => {
    apiSimulada({ ...base, [`GET /orgs/${ORG}/accounts`]: [403, { error: "forbidden", message: "no" }] });
    montarEnApp(`/app/${ORG}/posiciones`, "posiciones", <Posiciones />, "viewer");
    expect(await screen.findByText("Sin permiso")).toBeInTheDocument();
  });
});

describe("Incidente", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("las referencias de la explicación son enlaces legibles y la procedencia queda plegada", async () => {
    apiSimulada(base);
    montarEnApp(`/app/${ORG}/incidentes/i-1`, "incidentes/:incidente", <IncidenteDetalle />);
    expect(await screen.findByRole("link", { name: "Lectura del bloque 20.000.000" })).toHaveAttribute("href", "#evidencia-1");
    expect(screen.getByRole("link", { name: "Política, versión 2" })).toHaveAttribute("href", `/app/${ORG}/configuracion#politica-p-1`);
    expect(screen.getByRole("link", { name: "Evidencia de apertura" })).toHaveAttribute("href", "#evidencia-1");
    expect(screen.getByText(/enunciado 1: snapshot:9, rule_version:2, evidence:1/)).toBeInTheDocument();
  });

  it("una entrega por sandbox dice que fue una simulación sin envío externo", async () => {
    apiSimulada(base);
    montarEnApp(`/app/${ORG}/incidentes/i-1`, "incidentes/:incidente", <IncidenteDetalle />);
    expect(await screen.findByText("Simulación registrada, sin envío externo")).toBeInTheDocument();
    expect(screen.getByText(/No puedo confirmar que una persona la haya leído/)).toBeInTheDocument();
  });

  it("si la API rechaza el acknowledgement no muestra éxito", async () => {
    apiSimulada({ ...base, [`POST /orgs/${ORG}/incidents/i-1/acknowledge`]: [409, { error: "conflict", message: "Incident is acknowledged; only open incidents can be acknowledged." }] });
    montarEnApp(`/app/${ORG}/incidentes/i-1`, "incidentes/:incidente", <IncidenteDetalle />, "operator");
    fireEvent.click(await screen.findByRole("button", { name: "Tomar el incidente" }));
    expect(await screen.findByText("No se pudo completar")).toBeInTheDocument();
    expect(screen.getByText("Abierto")).toBeInTheDocument();
  });

  it("una persona de solo lectura no ve acciones", async () => {
    apiSimulada(base);
    montarEnApp(`/app/${ORG}/incidentes/i-1`, "incidentes/:incidente", <IncidenteDetalle />, "viewer");
    expect(await screen.findByText(/Tu rol es de lectura/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tomar el incidente" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Generar explicación" })).toBeNull();
  });
});

describe("Configuración", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("la prueba de un canal sandbox dice que registró una simulación", async () => {
    apiSimulada({ ...base, [`POST /orgs/${ORG}/channels/ch-1/test`]: [202, { outbox_id: 1, status: "sent", kind: "sandbox", outcome: "simulated", error: null }] });
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />, "operator");
    fireEvent.click(await screen.findByRole("button", { name: /Enviar prueba/ }));
    expect(await screen.findByText(/Registré una simulación: el mensaje no salió del sistema/)).toBeInTheDocument();
  });

  it("con webhooks deshabilitados explica el siguiente paso y no ofrece crearlos", async () => {
    apiSimulada(base);
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />, "owner");
    expect(await screen.findByText("Los envíos externos están deshabilitados en esta instancia")).toBeInTheDocument();
    expect(screen.queryByLabelText("URL del webhook (https)")).toBeNull();
  });

  it("con webhooks habilitados muestra el secreto una sola vez y traduce los errores del destino", async () => {
    apiSimulada({
      ...base,
      [`GET /orgs/${ORG}/channels`]: [200, { channels: [], webhooks_enabled: true }],
      [`POST /orgs/${ORG}/channels`]: [201, { id: "w-1", kind: "webhook", name: "Alertas", config: { host: "hooks.ejemplo.test" }, enabled: true,
                                              verified_at: null, created_at: 0, last_test: null, signing_secret: "secreto-de-firma-de-prueba" }],
    });
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />, "owner");
    fireEvent.change(await screen.findByLabelText("URL del webhook (https)"), { target: { value: "https://hooks.ejemplo.test/x" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear webhook" }));
    expect(await screen.findByText("secreto-de-firma-de-prueba")).toBeInTheDocument();
    expect(screen.getByText(/no lo vuelvo a mostrar/)).toBeInTheDocument();
  });

  it("no guarda una política sin mostrar antes cuándo abre y cuándo despeja", async () => {
    const llamadas = apiSimulada({
      ...base,
      [`POST /orgs/${ORG}/policies/preview`]: [200, { type: "health_factor_below", severity: "high", escalate_after_seconds: 3600,
        opens: { when: "health_factor_below", threshold: "1.5", requires_fresh_data: true },
        clears: { when: "health_factor_at_or_above", value: "1.575", consecutive_evaluations: 2, also_when: "no_debt" } }],
      [`POST /orgs/${ORG}/policies`]: [201, { id: "p-9" }],
    });
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />, "operator");
    fireEvent.click(await screen.findByRole("button", { name: "Nueva política" }));
    fireEvent.click(screen.getByRole("button", { name: "Ver cuándo abre y cuándo despeja" }));
    expect(await screen.findByText(/Se despeja cuando el health factor llega a 1,575 o más en 2 evaluaciones seguidas/)).toBeInTheDocument();
    expect(llamadas.some((l) => l.metodo === "POST" && l.ruta === `/orgs/${ORG}/policies`)).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Crear política" }));
    await waitFor(() => expect(llamadas.some((l) => l.metodo === "POST" && l.ruta === `/orgs/${ORG}/policies`)).toBe(true));
  });

  it("la invitación muestra el enlace una vez y solo la ve la persona dueña", async () => {
    apiSimulada({ ...base, [`POST /orgs/${ORG}/invitations`]: [201, { id: "inv-1", email: "nueva@ejemplo.test", role: "viewer", created_at: 0,
                                                                     expires_at: AHORA + 3600, accepted_at: null, revoked_at: null, token: "token-de-invitacion-123" }] });
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />, "owner");
    fireEvent.change(await screen.findByLabelText("Email de la persona"), { target: { value: "nueva@ejemplo.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Invitar" }));
    expect(await screen.findByText(/\/invitacion#token=token-de-invitacion-123/)).toBeInTheDocument();
    expect(screen.getByText(/no envío correos/)).toBeInTheDocument();
  });

  it("una persona operadora no ve invitaciones ni cambio de roles", async () => {
    apiSimulada(base);
    montarEnApp(`/app/${ORG}/configuracion`, "configuracion", <Configuracion />, "operator");
    await screen.findByText("persona@ejemplo.test");
    expect(screen.queryByLabelText("Email de la persona")).toBeNull();
    expect(screen.queryByLabelText(/Rol de/)).toBeNull();
  });
});
