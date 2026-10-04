// Consultas y mutaciones con React Query. Política de reintentos coherente con
// la API: nunca reintento 4xx; un 429 lo reintento una vez solo si Retry-After
// pide una espera corta (si es larga, muestro cuánto esperar); reintento dos
// veces errores de red y 5xx con backoff.

import { QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";

const ESPERA_MAXIMA_429 = 10;

export function debeReintentar(intento: number, error: unknown): boolean {
  if (error instanceof ApiError) {
    if (error.status === 429) return intento < 1 && (error.retryAfter ?? 0) <= ESPERA_MAXIMA_429;
    if (error.status >= 400 && error.status < 500) return false;
  }
  return intento < 2;
}

export function esperaReintento(intento: number, error: unknown): number {
  if (error instanceof ApiError && error.status === 429 && error.retryAfter) return error.retryAfter * 1000;
  return Math.min(8000, 500 * 2 ** intento);
}

export function crearQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: debeReintentar, retryDelay: esperaReintento, staleTime: 15_000, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

export const claves = {
  resumen: (org: string) => ["org", org, "resumen"] as const,
  cuentas: (org: string) => ["org", org, "cuentas"] as const,
  posicion: (org: string, cuenta: string) => ["org", org, "posicion", cuenta] as const,
  incidentes: (org: string, estado: string) => ["org", org, "incidentes", estado] as const,
  incidente: (org: string, id: string) => ["org", org, "incidente", id] as const,
  explicacion: (org: string, id: string) => ["org", org, "explicacion", id] as const,
  politicas: (org: string) => ["org", org, "politicas"] as const,
  canales: (org: string) => ["org", org, "canales"] as const,
  miembros: (org: string) => ["org", org, "miembros"] as const,
  suscripcion: (org: string) => ["org", org, "suscripcion"] as const,
};

export const useResumen = (org: string) =>
  useQuery({ queryKey: claves.resumen(org), queryFn: () => api.resumen(org), enabled: Boolean(org) });
export const useCuentas = (org: string) => useQuery({ queryKey: claves.cuentas(org), queryFn: () => api.cuentas(org) });
export const useIncidentes = (org: string, estado: "active" | "resolved") =>
  useQuery({ queryKey: claves.incidentes(org, estado), queryFn: () => api.incidentes(org, estado) });
export const useIncidente = (org: string, id: string) => useQuery({ queryKey: claves.incidente(org, id), queryFn: () => api.incidente(org, id) });
export const useExplicacion = (org: string, id: string) =>
  useQuery({ queryKey: claves.explicacion(org, id), queryFn: () => api.explicacion(org, id) });
export const useSuscripcion = (org: string) =>
  useQuery({ queryKey: claves.suscripcion(org), queryFn: () => api.suscripcion(org), enabled: Boolean(org) });
export const usePoliticas = (org: string) => useQuery({ queryKey: claves.politicas(org), queryFn: () => api.politicas(org) });
export const useCanales = (org: string) => useQuery({ queryKey: claves.canales(org), queryFn: () => api.canales(org) });
export const useMiembros = (org: string) => useQuery({ queryKey: claves.miembros(org), queryFn: () => api.miembros(org) });

// "Sin snapshot todavía" (404) es un estado de la cuenta, no un error: lo devuelvo como null.
export const usePosicion = (org: string, cuenta: string) =>
  useQuery({
    queryKey: claves.posicion(org, cuenta),
    queryFn: async () => {
      try {
        return await api.ultimaPosicion(org, cuenta);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
  });

export function useInvalidarOrg(org: string) {
  const cliente = useQueryClient();
  return () => cliente.invalidateQueries({ queryKey: ["org", org] });
}

export function useMutacionOrg<A, R>(org: string, funcion: (args: A) => Promise<R>) {
  const invalidar = useInvalidarOrg(org);
  return useMutation({ mutationFn: funcion, onSuccess: () => invalidar() });
}
