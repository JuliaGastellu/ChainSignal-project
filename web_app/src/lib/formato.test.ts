import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { describirCondicion, describirError, estadoCuenta } from "./formato";
import type { Posicion } from "./tipos";

const AHORA = 1_800_000_000;

function posicion(cambios: Partial<Posicion>): Posicion {
  return {
    account_id: "c",
    read_only: true,
    schema: "s",
    protocol: "aave-v3",
    market: "ethereum",
    chain_id: 1,
    user: "0x",
    block: { number: 1, hash: "0x", timestamp: AHORA - 30 },
    data_quality: { status: "FRESH", reason: "none", detail: "" },
    status: "ACTIVE",
    collateral_base: "100",
    debt_base: "50",
    available_borrows_base: "10",
    health_factor: "1.7",
    no_debt: false,
    liquidation_threshold_pct: "80",
    ltv_pct: "75",
    emode_category: 0,
    assets: [],
    unread_reserves: [],
    reconciliation: {},
    limitations: [],
    read_at: AHORA - 20,
    synthetic: false,
    ...cambios,
  };
}

describe("estado de una cuenta", () => {
  it("sin snapshot, sin posiciones y sin deuda no son errores", () => {
    expect(estadoCuenta(null, 300, AHORA)).toBe("sin_lectura");
    expect(estadoCuenta(posicion({ status: "NO_POSITION", no_debt: true }), 300, AHORA)).toBe("sin_posicion");
    expect(estadoCuenta(posicion({ status: "COLLATERAL_ONLY", no_debt: true }), 300, AHORA)).toBe("sin_deuda");
    expect(estadoCuenta(posicion({}), 300, AHORA)).toBe("activa");
  });

  it("marca datos parciales, atrasados y caídos", () => {
    expect(estadoCuenta(posicion({ data_quality: { status: "PARTIAL", reason: "component_missing", detail: "" } }), 300, AHORA)).toBe("parcial");
    expect(estadoCuenta(posicion({ data_quality: { status: "STALE", reason: "timeout", detail: "" } }), 300, AHORA)).toBe("atrasada");
    expect(estadoCuenta(posicion({ read_at: AHORA - 3600 }), 300, AHORA)).toBe("atrasada");
    expect(estadoCuenta(posicion({ data_quality: { status: "UNAVAILABLE", reason: "timeout", detail: "" } }), 300, AHORA)).toBe("no_disponible");
  });
});

describe("errores presentables", () => {
  it("distingue caído, 401, 403 y 429", () => {
    expect(describirError(new ApiError(0, "network_error", "")).titulo).toBe("El servidor no responde");
    expect(describirError(new ApiError(401, "x", "")).accion?.href).toBe("/login");
    expect(describirError(new ApiError(403, "x", "")).titulo).toBe("Sin permiso");
    expect(describirError(new ApiError(429, "x", "", 30)).detalle).toContain("30 s");
    expect(describirError(new ApiError(502, "x", "")).titulo).toBe("Error del servidor");
  });
});

describe("condición de un incidente", () => {
  it("muestra el valor y el umbral", () => {
    const texto = describirCondicion({ rule_type: "health_factor_below", last_observed: { health_factor: "1.37", threshold: "1.5" } });
    expect(texto).toContain("1,37");
    expect(texto).toContain("1,5");
  });
});
