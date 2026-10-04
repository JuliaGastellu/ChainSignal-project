// Textos y formatos de la interfaz. Los montos llegan como texto decimal; los
// convierto a número solo para mostrarlos, nunca para calcular.

import { ApiError } from "./api";
import type { EstadoIncidente, Incidente, Posicion, Severidad } from "./tipos";

const numero = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 });
const monto = new Intl.NumberFormat("es-AR", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export function formatearNumero(valor: string | number | null | undefined, decimales = 2): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = Number(valor);
  if (!Number.isFinite(n)) return String(valor);
  return decimales === 2 ? numero.format(n) : new Intl.NumberFormat("es-AR", { maximumFractionDigits: decimales }).format(n);
}

// La moneda base de Aave V3 en Ethereum es USD con 8 decimales.
export function formatearMontoBase(valor: string | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  const n = Number(valor);
  return Number.isFinite(n) ? monto.format(n) : valor;
}

export function formatearFecha(segundos: number | null | undefined): string {
  if (!segundos) return "—";
  return new Date(segundos * 1000).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}

export function haceCuanto(segundos: number | null | undefined, ahora: number = Date.now() / 1000): string {
  if (!segundos) return "nunca";
  const diferencia = Math.max(0, Math.round(ahora - segundos));
  if (diferencia < 60) return "hace menos de un minuto";
  if (diferencia < 3600) return `hace ${Math.floor(diferencia / 60)} min`;
  if (diferencia < 86400) return `hace ${Math.floor(diferencia / 3600)} h`;
  return `hace ${Math.floor(diferencia / 86400)} d`;
}

export function acortarDireccion(direccion: string): string {
  return direccion.length > 12 ? `${direccion.slice(0, 6)}…${direccion.slice(-4)}` : direccion;
}

export const DIRECCION_VALIDA = /^0x[0-9a-fA-F]{40}$/;

export type Tono = "ok" | "neutro" | "aviso" | "error";

export const TONO_SEVERIDAD: Record<Severidad, Tono> = { low: "neutro", medium: "aviso", high: "error", critical: "error" };

export const SEVERIDADES: Record<Severidad, string> = { low: "Baja", medium: "Media", high: "Alta", critical: "Crítica" };

export const ESTADOS_INCIDENTE: Record<EstadoIncidente, string> = {
  open: "Abierto",
  acknowledged: "En seguimiento",
  resolved: "Resuelto",
};

export function describirCondicion(incidente: Pick<Incidente, "rule_type" | "last_observed">): string {
  const v = incidente.last_observed ?? {};
  switch (incidente.rule_type) {
    case "health_factor_below":
      if (v.no_debt) return "La cuenta ya no tiene deuda.";
      return `Health factor ${formatearNumero(v.health_factor as string, 4)} por debajo del umbral ${formatearNumero(v.threshold as string, 4)}.`;
    case "debt_change":
      return v.change_pct
        ? `La deuda cambió ${formatearNumero(v.change_pct as string)} % (umbral ${formatearNumero(v.change_pct_threshold as string)} %).`
        : "La cuenta pasó de no tener deuda a tener deuda.";
    case "stale_data":
      return v.age_seconds == null
        ? "Todavía no hay una lectura fresca de la cuenta."
        : `La última lectura fresca tiene ${Math.round(Number(v.age_seconds) / 60)} min (máximo ${Math.round(Number(v.max_age_seconds) / 60)} min).`;
    default:
      return "Condición de la política.";
  }
}

export const TIPOS_REGLA: Record<string, string> = {
  health_factor_below: "Health factor bajo",
  debt_change: "Cambio material de deuda",
  stale_data: "Dato atrasado",
};

// Estado de la cuenta según su último snapshot. "Sin posiciones" y "sin deuda"
// son estados normales, no errores.
export type EstadoCuenta = "sin_lectura" | "sin_posicion" | "sin_deuda" | "activa" | "parcial" | "atrasada" | "no_disponible";

export function estadoCuenta(posicion: Posicion | null | undefined, intervaloSegundos: number, ahora = Date.now() / 1000): EstadoCuenta {
  if (!posicion) return "sin_lectura";
  const calidad = posicion.data_quality.status;
  if (calidad === "UNAVAILABLE") return "no_disponible";
  const lectura = posicion.read_at ?? posicion.block?.timestamp ?? null;
  // Considero atrasada una lectura que superó dos intervalos de monitoreo (mínimo 15 min).
  if (calidad === "STALE" || (lectura !== null && ahora - lectura > Math.max(2 * intervaloSegundos, 900))) return "atrasada";
  if (calidad === "PARTIAL") return "parcial";
  if (posicion.status === "NO_POSITION") return "sin_posicion";
  if (posicion.no_debt) return "sin_deuda";
  return "activa";
}

export const TEXTO_ESTADO_CUENTA: Record<EstadoCuenta, { etiqueta: string; tono: Tono }> = {
  sin_lectura: { etiqueta: "Sin lectura todavía", tono: "neutro" },
  sin_posicion: { etiqueta: "Sin posiciones en Aave V3", tono: "neutro" },
  sin_deuda: { etiqueta: "Sin deuda", tono: "ok" },
  activa: { etiqueta: "Posición con deuda", tono: "ok" },
  parcial: { etiqueta: "Datos parciales", tono: "aviso" },
  atrasada: { etiqueta: "Datos atrasados", tono: "aviso" },
  no_disponible: { etiqueta: "No pudimos leer la cuenta", tono: "error" },
};

export interface ErrorPresentable {
  titulo: string;
  detalle: string;
  accion?: { texto: string; href: string };
}

export function describirError(error: unknown): ErrorPresentable {
  if (!(error instanceof ApiError)) {
    return { titulo: "Algo salió mal", detalle: "Ocurrió un error inesperado en la interfaz." };
  }
  if (error.code === "plan_limit") {
    return { titulo: "Límite del plan", detalle: "Tu plan no permite esta acción (cantidad de cuentas o frecuencia). Revisá el plan en Configuración." };
  }
  if (error.code === "plan_inactive") {
    return {
      titulo: "Plan sin servicio",
      detalle: "El monitoreo y las lecturas nuevas están pausados. Tu historial sigue disponible; para continuar, escribinos desde la página de inicio.",
      accion: { texto: "Contacto", href: "/#contacto" },
    };
  }
  switch (error.status) {
    case 0:
      return { titulo: "El servidor no responde", detalle: "No pudimos conectar con ChainSignal. Revisá tu conexión; reintentamos solos en unos segundos." };
    case 401:
      return { titulo: "Tu sesión terminó", detalle: "Iniciá sesión de nuevo para continuar.", accion: { texto: "Iniciar sesión", href: "/login" } };
    case 403:
      return { titulo: "Sin permiso", detalle: "Tu rol en esta organización no permite esta acción o esta vista." };
    case 404:
      return { titulo: "No encontrado", detalle: "El recurso no existe o pertenece a otra organización." };
    case 409:
      return { titulo: "Cambió mientras lo mirabas", detalle: error.message };
    case 422:
      return { titulo: "Revisá los datos", detalle: error.message };
    case 429:
      return {
        titulo: "Demasiadas solicitudes",
        detalle: error.retryAfter ? `Esperá ${error.retryAfter} s antes de reintentar.` : "Esperá un momento antes de reintentar.",
      };
    default:
      return { titulo: "Error del servidor", detalle: "El servidor no pudo completar la solicitud. Reintentá en unos segundos." };
  }
}

// Estado del plan en palabras, con la fecha que importa en cada caso.
export function describirPlan(s: {
  status: string;
  trial_ends_at: number | null;
  current_period_end: number | null;
  grace_ends_at: number | null;
  cancel_at_period_end: boolean;
}): { etiqueta: string; detalle: string; tono: Tono } {
  const fecha = (t: number | null) => (t ? new Date(t * 1000).toLocaleDateString("es-AR", { dateStyle: "long" }) : "—");
  switch (s.status) {
    case "trialing":
      return s.cancel_at_period_end
        ? { etiqueta: "Prueba con cancelación programada", detalle: `El servicio termina el ${fecha(s.trial_ends_at)}.`, tono: "aviso" }
        : { etiqueta: "Prueba", detalle: `La prueba termina el ${fecha(s.trial_ends_at)}.`, tono: "neutro" };
    case "active":
      return s.cancel_at_period_end
        ? { etiqueta: "Activo, cancelación programada", detalle: `El servicio termina el ${fecha(s.current_period_end)}.`, tono: "aviso" }
        : { etiqueta: "Activo", detalle: `Período pago hasta el ${fecha(s.current_period_end)}.`, tono: "ok" };
    case "past_due":
      return { etiqueta: "Pago pendiente", detalle: `Seguís con servicio hasta el ${fecha(s.grace_ends_at)} (gracia).`, tono: "aviso" };
    case "canceled":
      return { etiqueta: "Cancelado", detalle: "El monitoreo está pausado. El historial sigue disponible.", tono: "error" };
    case "expired":
      return { etiqueta: "Vencido", detalle: "El monitoreo está pausado. El historial sigue disponible.", tono: "error" };
    case "demo":
      return { etiqueta: "Demo", detalle: "Datos sintéticos; la demo vence sola.", tono: "neutro" };
    default:
      return { etiqueta: "Sin plan", detalle: "La organización no tiene un plan con servicio.", tono: "error" };
  }
}
