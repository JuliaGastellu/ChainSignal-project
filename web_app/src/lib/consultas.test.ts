import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { debeReintentar, esperaReintento } from "./consultas";

describe("política de reintentos", () => {
  it("no reintenta errores del cliente", () => {
    for (const estado of [400, 401, 403, 404, 409, 422]) {
      expect(debeReintentar(0, new ApiError(estado, "x", "x"))).toBe(false);
    }
  });

  it("reintenta una vez un 429 respetando Retry-After", () => {
    const error = new ApiError(429, "rate_limited", "x", 7);
    expect(debeReintentar(0, error)).toBe(true);
    expect(debeReintentar(1, error)).toBe(false);
    expect(esperaReintento(0, error)).toBe(7000);
  });

  it("no reintenta un 429 que pide una espera larga", () => {
    expect(debeReintentar(0, new ApiError(429, "rate_limited", "x", 30))).toBe(false);
  });

  it("reintenta dos veces fallas de red y del servidor con backoff", () => {
    const caido = new ApiError(0, "network_error", "x");
    expect([0, 1, 2].map((i) => debeReintentar(i, caido))).toEqual([true, true, false]);
    expect(debeReintentar(0, new ApiError(503, "x", "x"))).toBe(true);
    expect(esperaReintento(0, caido)).toBe(500);
    expect(esperaReintento(3, caido)).toBe(4000);
  });
});
