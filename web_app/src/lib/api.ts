// Cliente HTTP tipado de la interfaz. La sesión viaja en una cookie HttpOnly que
// este código no puede leer; en mutaciones agrego el token CSRF que la API dejó
// en la cookie legible cs_csrf. No hay ninguna clave global en el bundle.
// Una respuesta no OK nunca se trata como éxito: siempre termina en ApiError.

import type {
  Canal, Invitacion, ListaCanales, PruebaCanal, VersionPolitica, VistaPreviaPolitica,
  Cuenta, Explicacion, Suscripcion, IncidenteDetalle, Incidente, Miembro, Politica, Posicion, Resumen } from "./tipos";

const baseConfigurada = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();

// Sin VITE_API_BASE uso el mismo origen: en desarrollo y en preview el proxy de
// Vite reenvía a la API, y en producción la sirvo detrás del mismo dominio.
export const API_BASE = baseConfigurada ? baseConfigurada.replace(/\/$/, "") : "";

const METODOS_SEGUROS = new Set(["GET", "HEAD", "OPTIONS"]);

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryAfter: number | null = null,
  ) {
    super(message);
  }
}

export function leerCookie(nombre: string, cookies: string = document.cookie): string | null {
  for (const parte of cookies.split(";")) {
    const [clave, ...valor] = parte.trim().split("=");
    if (clave === nombre) return decodeURIComponent(valor.join("="));
  }
  return null;
}

export async function apiFetch(ruta: string, init: RequestInit = {}): Promise<Response> {
  const metodo = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!METODOS_SEGUROS.has(metodo)) {
    const csrf = leerCookie("cs_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    return await fetch(`${API_BASE}${ruta}`, { ...init, method: metodo, headers, credentials: "include" });
  } catch {
    // fetch solo lanza si no hubo respuesta: servidor caído o sin red.
    throw new ApiError(0, "network_error", "No pudimos conectar con el servidor.");
  }
}

export async function apiJson<T>(ruta: string, init: RequestInit = {}): Promise<T> {
  const respuesta = await apiFetch(ruta, init);
  if (!respuesta.ok) {
    let codigo = "http_error";
    let mensaje = `HTTP ${respuesta.status}`;
    try {
      const cuerpo = await respuesta.json();
      codigo = cuerpo.error ?? codigo;
      mensaje = cuerpo.message ?? mensaje;
    } catch {
      // cuerpo no JSON: me quedo con el estado HTTP
    }
    const espera = Number(respuesta.headers.get("Retry-After"));
    throw new ApiError(respuesta.status, codigo, mensaje, Number.isFinite(espera) && espera > 0 ? espera : null);
  }
  if (respuesta.status === 204) return undefined as T;
  return (await respuesta.json()) as T;
}

const json = (cuerpo: unknown): RequestInit => ({ body: JSON.stringify(cuerpo) });

export interface Membresia {
  organization_id: string;
  organization_name: string;
  role: "owner" | "operator" | "viewer";
  membership_id: string;
}

export interface SesionApi {
  user: { id: string; email: string };
  expires_at: number;
  memberships: Membresia[];
}

// Endpoints tipados. Cada función devuelve el contrato de la API o lanza ApiError.
export const api = {
  sesion: () => apiJson<SesionApi>("/auth/session"),
  login: (email: string, password: string) => apiJson<SesionApi>("/auth/login", { method: "POST", ...json({ email, password }) }),
  alta: (email: string, password: string, organization_name: string) =>
    apiJson<SesionApi & { organization_id: string }>("/auth/signup", { method: "POST", ...json({ email, password, organization_name }) }),
  logout: () => apiJson<unknown>("/auth/logout", { method: "POST" }),
  demo: () => apiJson<{ organization_id: string; expires_at: number }>("/demo", { method: "POST" }),

  resumen: (org: string) => apiJson<Resumen>(`/orgs/${org}/summary`),
  cuentas: (org: string) => apiJson<{ accounts: Cuenta[] }>(`/orgs/${org}/accounts`).then((r) => r.accounts),
  crearCuenta: (org: string, address: string, chain_id: number, label: string | null) =>
    apiJson<Cuenta>(`/orgs/${org}/accounts`, { method: "POST", ...json({ address, chain_id, label: label || null }) }),
  ultimaPosicion: (org: string, cuenta: string) => apiJson<Posicion>(`/orgs/${org}/accounts/${cuenta}/positions/aave-v3/latest`),
  leerPosicion: (org: string, cuenta: string) => apiJson<Posicion>(`/orgs/${org}/accounts/${cuenta}/positions/aave-v3`),
  evaluar: (org: string, cuenta: string) =>
    apiJson<{ queued: boolean; status: string }>(`/orgs/${org}/accounts/${cuenta}/evaluate`, { method: "POST" }),

  incidentes: (org: string, estado: "active" | "resolved") =>
    apiJson<{ incidents: Incidente[] }>(`/orgs/${org}/incidents?status=${estado}`).then((r) => r.incidents),
  incidente: (org: string, id: string) => apiJson<IncidenteDetalle>(`/orgs/${org}/incidents/${id}`),
  reconocer: (org: string, id: string) => apiJson<Incidente>(`/orgs/${org}/incidents/${id}/acknowledge`, { method: "POST" }),
  resolver: (org: string, id: string, note: string) =>
    apiJson<Incidente>(`/orgs/${org}/incidents/${id}/resolve`, { method: "POST", ...json({ note }) }),

  explicacion: (org: string, id: string) => apiJson<Explicacion>(`/orgs/${org}/incidents/${id}/explanation`),
  generarExplicacion: (org: string, id: string) =>
    apiJson<Explicacion>(`/orgs/${org}/incidents/${id}/explanation`, { method: "POST" }),

  politicas: (org: string) => apiJson<{ policies: Politica[] }>(`/orgs/${org}/policies`).then((r) => r.policies),
  crearPolitica: (org: string, name: string, rule: Record<string, unknown>) =>
    apiJson<Politica>(`/orgs/${org}/policies`, { method: "POST", ...json({ name, rule }) }),
  actualizarPolitica: (org: string, id: string, cambios: { name?: string; rule?: Record<string, unknown>; enabled?: boolean }) =>
    apiJson<Politica>(`/orgs/${org}/policies/${id}`, { method: "PATCH", ...json(cambios) }),
  versionesPolitica: (org: string, id: string) =>
    apiJson<{ versions: VersionPolitica[] }>(`/orgs/${org}/policies/${id}/versions`).then((r) => r.versions),
  vistaPreviaPolitica: (org: string, rule: Record<string, unknown>) =>
    apiJson<VistaPreviaPolitica>(`/orgs/${org}/policies/preview`, { method: "POST", ...json({ rule }) }),

  canales: (org: string) => apiJson<ListaCanales>(`/orgs/${org}/channels`),
  crearCanal: (org: string, kind: "sandbox" | "webhook", name: string, config: Record<string, unknown> = {}) =>
    apiJson<Canal>(`/orgs/${org}/channels`, { method: "POST", ...json({ kind, name, config }) }),
  probarCanal: (org: string, id: string) => apiJson<PruebaCanal>(`/orgs/${org}/channels/${id}/test`, { method: "POST" }),

  invitaciones: (org: string) => apiJson<{ invitations: Invitacion[] }>(`/orgs/${org}/invitations`).then((r) => r.invitations),
  invitar: (org: string, email: string, role: string) =>
    apiJson<Invitacion>(`/orgs/${org}/invitations`, { method: "POST", ...json({ email, role }) }),
  revocarInvitacion: (org: string, id: string) => apiJson<void>(`/orgs/${org}/invitations/${id}`, { method: "DELETE" }),
  aceptarInvitacion: (token: string, password?: string) =>
    apiJson<{ organization_id: string; new_user: boolean }>("/invitations/accept", { method: "POST", ...json({ token, password: password || null }) }),
  cambiarRol: (org: string, membresia: string, role: string) =>
    apiJson<{ role: string }>(`/orgs/${org}/members/${membresia}`, { method: "PATCH", ...json({ role }) }),
  quitarMiembro: (org: string, membresia: string) => apiJson<void>(`/orgs/${org}/members/${membresia}`, { method: "DELETE" }),
  practica: () => apiJson<{ organization_id: string; expires_at: number; created: boolean }>("/practice", { method: "POST" }),

  suscripcion: (org: string) => apiJson<Suscripcion>(`/orgs/${org}/subscription`),
  cancelarSuscripcion: (org: string) => apiJson<Suscripcion>(`/orgs/${org}/subscription/cancel`, { method: "POST" }),
  reanudarSuscripcion: (org: string) => apiJson<Suscripcion>(`/orgs/${org}/subscription/resume`, { method: "POST" }),
  contacto: (email: string, organization: string, message: string, consent: boolean) =>
    apiJson<{ status: string }>("/contact", { method: "POST", ...json({ email, organization: organization || null, message, consent }) }),

  miembros: (org: string) => apiJson<{ members: Miembro[] }>(`/orgs/${org}/members`).then((r) => r.members),
};
