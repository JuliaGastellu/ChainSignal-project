import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { esperaReconexion, useEventosOrg } from "./useEventosOrg";

// EventSource controlado: registro cada instancia para disparar sus eventos.
class FuenteFalsa {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instancias: FuenteFalsa[] = [];
  readyState = FuenteFalsa.CONNECTING;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  oyentes: Record<string, ((e: MessageEvent) => void)[]> = {};
  cerrada = false;
  constructor(public url: string) {
    FuenteFalsa.instancias.push(this);
  }
  addEventListener(tipo: string, oyente: (e: MessageEvent) => void) {
    (this.oyentes[tipo] ??= []).push(oyente);
  }
  close() {
    this.cerrada = true;
    this.readyState = FuenteFalsa.CLOSED;
  }
  emitir(tipo: string, id: string) {
    for (const oyente of this.oyentes[tipo] ?? []) oyente(new MessageEvent(tipo, { data: "{}", lastEventId: id }));
  }
}

function envoltorio(cliente: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={cliente}>{children}</QueryClientProvider>;
}

describe("useEventosOrg", () => {
  beforeEach(() => {
    FuenteFalsa.instancias = [];
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", FuenteFalsa);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("pasa a conectado con onopen e invalida las consultas de la organización al recibir eventos", async () => {
    const cliente = new QueryClient();
    const invalidar = vi.spyOn(cliente, "invalidateQueries");
    const { result } = renderHook(() => useEventosOrg("org-1"), { wrapper: envoltorio(cliente) });
    const fuente = FuenteFalsa.instancias[0];
    expect(fuente.url).toBe("/orgs/org-1/events/stream");
    expect(result.current).toBe("conectando");
    act(() => fuente.onopen?.());
    expect(result.current).toBe("conectado");
    act(() => fuente.emitir("org_event", "41"));
    await act(async () => vi.advanceTimersByTime(400));
    expect(invalidar).toHaveBeenCalledWith({ queryKey: ["org", "org-1"] });
  });

  it("si el servidor cierra la conexión, verifica la sesión y reabre desde el último cursor", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ user: {}, memberships: [] }), { status: 200 })));
    const { result } = renderHook(() => useEventosOrg("org-1"), { wrapper: envoltorio(new QueryClient()) });
    const primera = FuenteFalsa.instancias[0];
    act(() => primera.onopen?.());
    act(() => primera.emitir("org_event", "57"));
    primera.readyState = FuenteFalsa.CLOSED;
    await act(async () => primera.onerror?.());
    expect(result.current).toBe("reconectando");
    expect(primera.cerrada).toBe(true);
    await act(async () => vi.advanceTimersByTime(esperaReconexion(0)));
    expect(FuenteFalsa.instancias).toHaveLength(2);
    expect(FuenteFalsa.instancias[1].url).toBe("/orgs/org-1/events/stream?cursor=57");
  });

  it("un corte transitorio queda en manos del navegador, sin abrir otra conexión", async () => {
    const { result } = renderHook(() => useEventosOrg("org-1"), { wrapper: envoltorio(new QueryClient()) });
    const fuente = FuenteFalsa.instancias[0];
    act(() => fuente.onopen?.());
    fuente.readyState = FuenteFalsa.CONNECTING;
    act(() => fuente.onerror?.());
    expect(result.current).toBe("reconectando");
    await act(async () => vi.advanceTimersByTime(60_000));
    expect(FuenteFalsa.instancias).toHaveLength(1);
  });

  it("se detiene sin reintentar si la sesión terminó", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "not_authenticated" }), { status: 401 })));
    const { result } = renderHook(() => useEventosOrg("org-1"), { wrapper: envoltorio(new QueryClient()) });
    const fuente = FuenteFalsa.instancias[0];
    fuente.readyState = FuenteFalsa.CLOSED;
    await act(async () => fuente.onerror?.());
    await act(async () => vi.advanceTimersByTime(60_000));
    expect(result.current).toBe("detenido");
    expect(FuenteFalsa.instancias).toHaveLength(1);
  });

  it("cierra la conexión al desmontar", () => {
    const { unmount } = renderHook(() => useEventosOrg("org-1"), { wrapper: envoltorio(new QueryClient()) });
    unmount();
    expect(FuenteFalsa.instancias[0].cerrada).toBe(true);
  });
});
