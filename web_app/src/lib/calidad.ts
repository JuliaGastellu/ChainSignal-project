// Calidad de los datos on-chain que devuelve la API (E03). La interfaz nunca
// presenta una cuenta como sana cuando los datos faltan, están viejos o
// incompletos: lo dice explícitamente.

export type EstadoCalidad = "FRESH" | "STALE" | "PARTIAL" | "UNAVAILABLE";

export interface ProcedenciaApi {
  proveedor: string;
  chain_id: number;
  red: string;
  referencia: { numero: number; hash: string; timestamp: number } | null;
  obtenido_en: number | null;
  desde_bloque: number | null;
  hasta_bloque: number | null;
  historial_completo: boolean;
}

export interface DataQuality {
  status: EstadoCalidad;
  reason: string;
  actionable_allowed: boolean;
  no_activity: boolean;
  complete_history: boolean;
  components?: Record<string, { status: EstadoCalidad; reason: string; provenance: ProcedenciaApi }>;
}

export interface DescripcionCalidad {
  etiqueta: string;
  tono: "ok" | "aviso" | "error";
  mensaje: string;
  // true solo si los datos alcanzan para afirmar algo sobre la cuenta.
  datosSuficientes: boolean;
}

const MOTIVOS: Record<string, string> = {
  timeout: "el proveedor no respondió a tiempo",
  rate_limited: "el proveedor limitó las consultas",
  invalid_response: "el proveedor devolvió una respuesta inválida",
  pagination_incomplete: "faltaron páginas del historial",
  provider_error: "el proveedor devolvió un error",
  wrong_network: "el proveedor apunta a otra red",
  not_configured: "falta configurar el proveedor",
  component_missing: "faltó parte de los datos (por ejemplo, el balance)",
  archive_unavailable: "el proveedor no tiene datos históricos de ese bloque",
  reconciliation_mismatch: "los saldos no coincidieron con la verificación independiente",
  reorg_during_read: "la cadena se reorganizó durante la lectura",
};

export function esDataQuality(valor: unknown): valor is DataQuality {
  if (!valor || typeof valor !== "object") return false;
  const estado = (valor as Record<string, unknown>).status;
  return estado === "FRESH" || estado === "STALE" || estado === "PARTIAL" || estado === "UNAVAILABLE";
}

export function describirCalidad(calidad: DataQuality | undefined | null): DescripcionCalidad {
  if (!calidad) {
    return { etiqueta: "Calidad desconocida", tono: "aviso", mensaje: "La respuesta no informa la calidad de los datos.", datosSuficientes: false };
  }
  const motivo = MOTIVOS[calidad.reason] ?? calidad.reason;
  switch (calidad.status) {
    case "UNAVAILABLE":
      return {
        etiqueta: "Datos no disponibles",
        tono: "error",
        mensaje: `No pudimos leer la cuenta: ${motivo}. Esto no indica que la cuenta esté sana.`,
        datosSuficientes: false,
      };
    case "STALE":
      return { etiqueta: "Datos desactualizados", tono: "aviso", mensaje: `Mostramos la última lectura guardada porque ${motivo}.`, datosSuficientes: true };
    case "PARTIAL":
      return { etiqueta: "Datos parciales", tono: "aviso", mensaje: `La lectura está incompleta: ${motivo}.`, datosSuficientes: true };
    default:
      if (calidad.no_activity) {
        return { etiqueta: "Sin actividad observada", tono: "ok", mensaje: "La cuenta no tiene actividad en la ventana leída.", datosSuficientes: true };
      }
      return {
        etiqueta: "Datos actualizados",
        tono: "ok",
        mensaje: calidad.complete_history
          ? "Historial completo leído."
          : "Ventana reciente completa; la actividad más antigua no fue leída.",
        datosSuficientes: true,
      };
  }
}
