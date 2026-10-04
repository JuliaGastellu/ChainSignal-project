import { describe, expect, it } from "vitest";
import { describirCalidad, esDataQuality, type DataQuality } from "./calidad";

const base: DataQuality = { status: "FRESH", reason: "none", actionable_allowed: true, no_activity: false, complete_history: true };

describe("describirCalidad", () => {
  it("nunca presenta como sana una cuenta sin datos", () => {
    const d = describirCalidad({ ...base, status: "UNAVAILABLE", reason: "rate_limited", actionable_allowed: false });
    expect(d.tono).toBe("error");
    expect(d.datosSuficientes).toBe(false);
    expect(d.mensaje).toContain("no indica que la cuenta esté sana");
    expect(d.mensaje).toContain("limitó las consultas");
  });

  it("distingue sin actividad de una falla", () => {
    expect(describirCalidad({ ...base, no_activity: true }).etiqueta).toBe("Sin actividad observada");
    expect(describirCalidad({ ...base, status: "UNAVAILABLE", reason: "timeout" }).etiqueta).toBe("Datos no disponibles");
  });

  it("marca datos viejos, parciales e historial truncado", () => {
    expect(describirCalidad({ ...base, status: "STALE", reason: "timeout" }).tono).toBe("aviso");
    expect(describirCalidad({ ...base, status: "PARTIAL", reason: "pagination_incomplete" }).mensaje).toContain("faltaron páginas");
    expect(describirCalidad({ ...base, complete_history: false }).mensaje).toContain("más antigua no fue leída");
  });

  it("trata la ausencia de calidad como desconocida", () => {
    expect(describirCalidad(undefined).datosSuficientes).toBe(false);
    expect(esDataQuality({ status: "OK" })).toBe(false);
    expect(esDataQuality(base)).toBe(true);
  });
});
