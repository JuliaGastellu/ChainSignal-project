import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, apiJson, leerCookie } from "./api";

describe("cliente de la API", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    document.cookie = "cs_csrf=token-csrf-de-prueba";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "cs_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("envía credenciales y no agrega CSRF en lecturas", async () => {
    await apiFetch("/orgs/x/accounts");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/orgs/x/accounts");
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBeNull();
  });

  it("agrega el token CSRF de la cookie en mutaciones", async () => {
    await apiFetch("/orgs/x/accounts", { method: "post", body: JSON.stringify({ address: "0x1" }) });
    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init.headers);
    expect(init.method).toBe("POST");
    expect(headers.get("X-CSRF-Token")).toBe("token-csrf-de-prueba");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("nunca envía una clave global de API", async () => {
    await apiFetch("/auth/session");
    await apiFetch("/auth/logout", { method: "POST" });
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init.headers).get("X-API-Key")).toBeNull();
    }
  });

  it("convierte errores de la API en ApiError con su código", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ error: "forbidden", message: "No." }), { status: 403 }));
    await expect(apiJson("/orgs/x/policies")).rejects.toMatchObject({ status: 403, code: "forbidden" });
    fetchMock.mockResolvedValueOnce(new Response("<html>", { status: 502 }));
    await expect(apiJson("/orgs/x/policies")).rejects.toBeInstanceOf(ApiError);
  });

  it("lee cookies por nombre exacto", () => {
    expect(leerCookie("cs_csrf", "a=1; cs_csrf=x%3Dy; cs_csrf_extra=z")).toBe("x=y");
    expect(leerCookie("cs_session", "cs_csrf=x")).toBeNull();
  });
});
