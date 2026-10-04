// Eventos en vivo de una organización por SSE. Solo leo: el stream nunca dispara
// análisis ni escrituras. Cuando llega un evento invalido las consultas de la
// organización y React Query vuelve a pedir lo que esté en pantalla.
//
// EventSource no tiene onclose: uso onopen y onerror. Ante un corte de red el
// navegador reconecta solo y envía Last-Event-ID. Si el servidor responde con
// un error HTTP (401, 403, 429) el navegador cierra la conexión; en ese caso
// reconecto yo con backoff y con el último cursor recibido, salvo que la sesión
// haya terminado.

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE, ApiError, api } from "@/lib/api";

export type EstadoConexion = "conectando" | "conectado" | "reconectando" | "detenido";

export function esperaReconexion(intento: number): number {
  return Math.min(30_000, 1000 * 2 ** intento);
}

export function useEventosOrg(org: string | undefined): EstadoConexion {
  const cliente = useQueryClient();
  const [estado, setEstado] = useState<EstadoConexion>("conectando");
  const ultimoId = useRef<string | null>(null);

  useEffect(() => {
    if (!org || typeof EventSource === "undefined") {
      setEstado("detenido");
      return;
    }
    let fuente: EventSource | null = null;
    let temporizador: ReturnType<typeof setTimeout> | undefined;
    let invalidacion: ReturnType<typeof setTimeout> | undefined;
    let intento = 0;
    let activo = true;

    const invalidar = () => {
      clearTimeout(invalidacion);
      invalidacion = setTimeout(() => cliente.invalidateQueries({ queryKey: ["org", org] }), 300);
    };

    const abrir = () => {
      if (!activo) return;
      const cursor = ultimoId.current ? `?cursor=${encodeURIComponent(ultimoId.current)}` : "";
      fuente = new EventSource(`${API_BASE}/orgs/${org}/events/stream${cursor}`, { withCredentials: true });
      fuente.onopen = () => {
        intento = 0;
        setEstado("conectado");
      };
      fuente.addEventListener("org_event", (evento) => {
        const mensaje = evento as MessageEvent;
        if (mensaje.lastEventId) ultimoId.current = mensaje.lastEventId;
        invalidar();
      });
      fuente.addEventListener("session_ended", () => {
        fuente?.close();
        setEstado("detenido");
        invalidar();
      });
      fuente.onerror = () => {
        if (!activo || !fuente) return;
        if (fuente.readyState === EventSource.CONNECTING) {
          setEstado("reconectando");
          return;
        }
        // CLOSED: el servidor rechazó la conexión. Verifico la sesión antes de insistir.
        fuente.close();
        setEstado("reconectando");
        api.sesion().then(
          () => programar(),
          (error: unknown) => {
            if (error instanceof ApiError && error.status === 401) {
              setEstado("detenido");
              invalidar();
            } else programar();
          },
        );
      };
    };

    const programar = () => {
      if (!activo) return;
      clearTimeout(temporizador);
      temporizador = setTimeout(abrir, esperaReconexion(intento++));
    };

    // El cursor es de cada organización: uno ajeno devolvería 404.
    ultimoId.current = null;
    setEstado("conectando");
    abrir();
    return () => {
      activo = false;
      clearTimeout(temporizador);
      clearTimeout(invalidacion);
      fuente?.close();
    };
  }, [org, cliente]);

  return estado;
}
