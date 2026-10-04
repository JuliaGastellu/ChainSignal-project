// Textos y formatos de la interfaz. Los montos llegan como texto decimal; los
// convierto a número solo para mostrarlos, nunca para calcular.

import { ApiError } from "./api";
import { traducirErrorEntrega, traducirMensajeApi } from "./traducciones";
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

export const ORDEN_SEVERIDAD: Severidad[] = ["critical", "high", "medium", "low"];

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
      return `Health factor ${formatearNumero(v.health_factor as string, 4)} por debajo del umbral de alerta ${formatearNumero(v.threshold as string, 4)}.`;
    case "debt_change":
      return v.change_pct
        ? `La deuda cambió ${formatearNumero(v.change_pct as string)} % (la política avisa desde ${formatearNumero(v.change_pct_threshold as string)} %).`
        : "La cuenta pasó de no tener deuda a tener deuda.";
    case "stale_data":
      return v.age_seconds == null
        ? "Todavía no hay una lectura actualizada de la cuenta."
        : `La última lectura actualizada tiene ${Math.round(Number(v.age_seconds) / 60)} min (la política admite ${Math.round(Number(v.max_age_seconds) / 60)} min).`;
    default:
      return "Condición de la política.";
  }
}

export const TIPOS_REGLA: Record<string, string> = {
  health_factor_below: "Health factor bajo",
  debt_change: "Cambio material de deuda",
  stale_data: "Dato atrasado",
};

// Tres señales separadas por cuenta, para no mezclar conceptos:
// - actividad: qué hay en la posición. Es neutra: tener deuda no es bueno ni malo.
// - alertas: si alguna política de la organización tiene un incidente abierto.
//   "Sin alertas" no significa "segura": solo que ninguna política se cumplió.
// - dato: qué tan reciente y completa es la lectura. Un dato fresco no dice nada
//   sobre el riesgo de la posición.

export interface Senal {
  etiqueta: string;
  tono: Tono;
  detalle?: string;
}

export function actividadCuenta(posicion: Posicion | null | undefined): Senal {
  if (!posicion) return { etiqueta: "Sin lectura todavía", tono: "neutro" };
  if (posicion.data_quality.status === "UNAVAILABLE") return { etiqueta: "Actividad desconocida", tono: "neutro", detalle: "No hay datos para saberlo." };
  if (posicion.status === "NO_POSITION") return { etiqueta: "Sin posiciones en Aave V3", tono: "neutro" };
  if (posicion.no_debt) return { etiqueta: "Solo colateral, sin deuda", tono: "neutro" };
  if (posicion.status === "ACTIVE") return { etiqueta: "Posición con deuda", tono: "neutro" };
  return { etiqueta: "Actividad desconocida", tono: "neutro" };
}

const NOMBRE_ALERTA: Record<string, string> = {
  health_factor_below: "health factor bajo el umbral",
  debt_change: "cambio de deuda",
  stale_data: "dato atrasado",
};

export function alertasCuenta(incidentes: Pick<Incidente, "rule_type" | "severity" | "last_observed">[]): Senal {
  if (incidentes.length === 0) {
    return { etiqueta: "Sin alertas abiertas", tono: "neutro", detalle: "Ninguna política se cumplió. No es una garantía sobre la posición." };
  }
  const principal = [...incidentes].sort((a, b) => ORDEN_SEVERIDAD.indexOf(a.severity) - ORDEN_SEVERIDAD.indexOf(b.severity))[0];
  const extra = incidentes.length > 1 ? ` (+${incidentes.length - 1})` : "";
  return {
    etiqueta: `Alerta abierta: ${NOMBRE_ALERTA[principal.rule_type] ?? principal.rule_type}${extra}`,
    tono: principal.severity === "low" ? "aviso" : "error",
    detalle: describirCondicion(principal),
  };
}

export type Frescura = "sin_lectura" | "actualizado" | "parcial" | "atrasado" | "no_disponible";

export function frescuraDato(posicion: Posicion | null | undefined, intervaloSegundos: number, ahora = Date.now() / 1000): Frescura {
  if (!posicion) return "sin_lectura";
  const calidad = posicion.data_quality.status;
  if (calidad === "UNAVAILABLE") return "no_disponible";
  const lectura = posicion.read_at ?? posicion.block?.timestamp ?? null;
  // Atrasado: STALE o más de dos intervalos de monitoreo sin leer (mínimo 15 min).
  if (calidad === "STALE" || (lectura !== null && ahora - lectura > Math.max(2 * intervaloSegundos, 900))) return "atrasado";
  if (calidad === "PARTIAL") return "parcial";
  return "actualizado";
}

export const TEXTO_FRESCURA: Record<Frescura, Senal> = {
  sin_lectura: { etiqueta: "Dato: sin lectura", tono: "neutro" },
  actualizado: { etiqueta: "Dato actualizado", tono: "neutro", detalle: "La lectura es reciente. No dice nada sobre el riesgo." },
  parcial: { etiqueta: "Dato parcial", tono: "aviso" },
  atrasado: { etiqueta: "Dato atrasado", tono: "aviso" },
  no_disponible: { etiqueta: "Dato no disponible", tono: "error" },
};

export interface ErrorPresentable {
  titulo: string;
  detalle: string;
  accion?: { texto: string; href: string };
  tecnico?: string; // código y mensaje original, para el desplegable de detalle técnico
}

export function describirError(error: unknown): ErrorPresentable {
  if (!(error instanceof ApiError)) {
    return { titulo: "Algo salió mal", detalle: "Ocurrió un error inesperado en la interfaz." };
  }
  return { ...describirErrorApi(error), tecnico: `${error.status} ${error.code}${error.message ? `: ${error.message}` : ""}` };
}

function describirErrorApi(error: ApiError): ErrorPresentable {
  const traducido = traducirMensajeApi(error.message);
  if (error.code === "webhooks_disabled") {
    return { titulo: "Envíos externos deshabilitados", detalle: "Esta instancia no envía webhooks. No lo reemplazo por una simulación." };
  }
  if (error.code === "webhook_destination_invalid") {
    return { titulo: "Destino no permitido", detalle: traducirErrorEntrega(error.message) };
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
      return { titulo: "No se pudo completar", detalle: traducido ?? "El estado cambió o la acción no es posible ahora. Actualizá y volvé a intentar." };
    case 422:
      return { titulo: "Revisá los datos", detalle: traducido ?? "Algún dato no es válido. El detalle técnico dice cuál." };
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

// Lo que puedo afirmar de una entrega, en palabras. Nunca digo "recibida por una persona".
export const RESULTADO_ENTREGA: Record<"simulated" | "accepted_by_destination" | "failed" | "pending", Senal> = {
  simulated: { etiqueta: "Simulación registrada, sin envío externo", tono: "neutro" },
  accepted_by_destination: { etiqueta: "Aceptada por el destino externo", tono: "ok" },
  failed: { etiqueta: "Falló", tono: "error" },
  pending: { etiqueta: "Pendiente", tono: "aviso" },
};

// Vista previa de una política, en palabras, con los valores que normalizó la API.
export function describirVistaPrevia(v: {
  type: string;
  escalate_after_seconds: number;
  opens: Record<string, unknown>;
  clears: Record<string, unknown>;
}): { abre: string; despeja: string; escala: string } {
  const minutos = (s: unknown) => Math.round(Number(s) / 60);
  const escala = `Si nadie toma el incidente en ${minutos(v.escalate_after_seconds)} min, sube un nivel de severidad.`;
  if (v.type === "health_factor_below") {
    const veces = Number(v.clears.consecutive_evaluations);
    return {
      abre: `Abre cuando el health factor queda por debajo de ${formatearNumero(v.opens.threshold as string, 4)}, solo con datos actualizados.`,
      despeja: `Se despeja cuando el health factor llega a ${formatearNumero(v.clears.value as string, 4)} o más en ${veces === 1 ? "1 evaluación" : `${veces} evaluaciones seguidas`}, o si la cuenta deja de tener deuda.`,
      escala,
    };
  }
  if (v.type === "debt_change") {
    return {
      abre: `Abre cuando la deuda cambia ${formatearNumero(v.opens.change_pct as string)} % o más respecto de la línea base, solo con datos actualizados.`,
      despeja: "No se despeja sola: la cierra una persona al resolverla, y la línea base se reinicia.",
      escala,
    };
  }
  return {
    abre: `Abre cuando pasan más de ${minutos(v.opens.max_age_seconds)} min sin una lectura actualizada.`,
    despeja: "Se despeja con la primera lectura actualizada.",
    escala,
  };
}
