import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import {
  actividadCuenta,
  alertasCuenta,
  describirCondicion,
  describirError,
  describirVistaPrevia,
  frescuraDato,
  RESULTADO_ENTREGA,
  TEXTO_FRESCURA,
} from "./formato";
import { traducirErrorEntrega, traducirLimite } from "./traducciones";
import type { Posicion } from "./tipos";

const AHORA = 1_800_000_000;

function posicion(cambios: Partial<Posicion>): Posicion {
  return {
    account_id: "c", read_only: true, schema: "s", protocol: "aave-v3", market: "ethereum", chain_id: 1, user: "0x",
    block: { number: 1, hash: "0x", timestamp: AHORA - 30 }, data_quality: { status: "FRESH", reason: "none", detail: "" },
    status: "ACTIVE", collateral_base: "100", debt_base: "50", available_borrows_base: "10", health_factor: "1.7", no_debt: false,
    liquidation_threshold_pct: "80", ltv_pct: "75", emode_category: 0, assets: [], unread_reserves: [], reconciliation: {},
    limitations: [], read_at: AHORA - 20, synthetic: false, ...cambios,
  };
}

const HF_ABIERTO = { rule_type: "health_factor_below" as const, severity: "high" as const, last_observed: { health_factor: "1.2254", threshold: "1.5" } };

describe("señales de una cuenta", () => {
  it("la actividad es neutra: tener deuda no es bueno ni malo", () => {
    expect(actividadCuenta(posicion({}))).toEqual({ etiqueta: "Posición con deuda", tono: "neutro" });
    expect(actividadCuenta(posicion({ status: "COLLATERAL_ONLY", no_debt: true })).tono).toBe("neutro");
    expect(actividadCuenta(posicion({ status: "NO_POSITION", no_debt: true })).etiqueta).toBe("Sin posiciones en Aave V3");
    expect(actividadCuenta(null).etiqueta).toBe("Sin lectura todavía");
  });

  it("una cuenta con un incidente de HF abierto muestra su alerta explícitamente", () => {
    const alerta = alertasCuenta([HF_ABIERTO]);
    expect(alerta.etiqueta).toBe("Alerta abierta: health factor bajo el umbral");
    expect(alerta.tono).toBe("error");
    expect(alerta.detalle).toContain("umbral de alerta 1,5");
    expect(alerta.detalle).not.toMatch(/liquida/i);
  });

  it("sin alertas no dice que la posición sea segura", () => {
    const sin = alertasCuenta([]);
    expect(sin.etiqueta).toBe("Sin alertas abiertas");
    expect(sin.tono).toBe("neutro");
    expect(sin.detalle).toContain("No es una garantía");
  });

  it("el dato atrasado, parcial o caído se marca; el dato fresco no implica seguridad", () => {
    expect(frescuraDato(posicion({ data_quality: { status: "STALE", reason: "timeout", detail: "" } }), 300, AHORA)).toBe("atrasado");
    expect(frescuraDato(posicion({ read_at: AHORA - 3600 }), 300, AHORA)).toBe("atrasado");
    expect(frescuraDato(posicion({ data_quality: { status: "PARTIAL", reason: "component_missing", detail: "" } }), 300, AHORA)).toBe("parcial");
    expect(frescuraDato(posicion({ data_quality: { status: "UNAVAILABLE", reason: "timeout", detail: "" } }), 300, AHORA)).toBe("no_disponible");
    expect(frescuraDato(posicion({}), 300, AHORA)).toBe("actualizado");
    expect(TEXTO_FRESCURA.actualizado.tono).toBe("neutro");
    expect(TEXTO_FRESCURA.actualizado.detalle).toContain("No dice nada sobre el riesgo");
  });
});

describe("entregas y canales", () => {
  it("el sandbox dice que simuló sin envío externo y nadie 'recibió'", () => {
    expect(RESULTADO_ENTREGA.simulated.etiqueta).toBe("Simulación registrada, sin envío externo");
    expect(RESULTADO_ENTREGA.accepted_by_destination.etiqueta).toBe("Aceptada por el destino externo");
    for (const r of Object.values(RESULTADO_ENTREGA)) expect(r.etiqueta).not.toMatch(/recibid|leíd/i);
  });

  it("traduce errores de entrega a castellano", () => {
    expect(traducirErrorEntrega("webhooks_disabled")).toContain("deshabilitados");
    expect(traducirErrorEntrega("http_503")).toBe("El destino respondió HTTP 503 (error del destino).");
    expect(traducirErrorEntrega("destination_not_public")).toContain("dirección privada");
    expect(traducirErrorEntrega("redirect_not_followed_302")).toContain("no la sigo");
  });
});

describe("textos en castellano", () => {
  it("traduce los límites conocidos y conserva el original", () => {
    const t = traducirLimite("No debt: health factor is not applicable (the Pool returns uint256 max).");
    expect(t.traducido).toBe(true);
    expect(t.texto).toContain("Sin deuda");
    expect(t.original).toContain("No debt");
    expect(traducirLimite("Something new from the API").traducido).toBe(false);
  });

  it("los errores de la API no muestran inglés crudo; el original queda como detalle técnico", () => {
    const conocido = describirError(new ApiError(409, "conflict", "An organization must keep at least one owner."));
    expect(conocido.detalle).toBe("La organización tiene que conservar al menos una persona dueña.");
    const desconocido = describirError(new ApiError(422, "invalid_request", "rule.threshold must be a decimal"));
    expect(desconocido.detalle).not.toContain("rule.threshold");
    expect(desconocido.tecnico).toContain("rule.threshold");
    expect(describirError(new ApiError(0, "network_error", "")).titulo).toBe("El servidor no responde");
    expect(describirError(new ApiError(429, "x", "", 30)).detalle).toContain("30 s");
  });

  it("describe cuándo abre, despeja y escala una política", () => {
    const v = describirVistaPrevia({
      type: "health_factor_below", escalate_after_seconds: 3600,
      opens: { when: "health_factor_below", threshold: "1.5" },
      clears: { when: "health_factor_at_or_above", value: "1.575", consecutive_evaluations: 2 },
    });
    expect(v.abre).toBe("Abre cuando el health factor queda por debajo de 1,5, solo con datos actualizados.");
    expect(v.despeja).toContain("1,575 o más en 2 evaluaciones seguidas");
    expect(v.escala).toContain("60 min");
  });

  it("la condición habla de umbral de alerta, no de liquidación", () => {
    expect(describirCondicion(HF_ABIERTO)).toBe("Health factor 1,2254 por debajo del umbral de alerta 1,5.");
  });
});
