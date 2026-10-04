// Convierto una referencia interna de una explicación (snapshot:N,
// rule_version:N, evidence:N) en un enlace legible. Solo enlazo lo que existe
// en el incidente, que ya llegó autorizado para esta organización.

import type { Evidencia, IncidenteDetalle } from "./tipos";

const TIPOS_EVIDENCIA: Record<Evidencia["kind"], string> = {
  opening: "apertura",
  escalation: "escalamiento",
  resolution: "resolución",
  correction: "corrección",
};

export interface Enlace {
  texto: string;
  href?: string;
  interno?: boolean; // ancla dentro de esta página
}

export function enlaceDeReferencia(ref: string, incidente: IncidenteDetalle, org: string): Enlace {
  const [tipo, valor] = ref.split(":");
  if (tipo === "evidence") {
    const ev = incidente.evidence.find((e) => String(e.id) === valor);
    return ev ? { texto: `Evidencia de ${TIPOS_EVIDENCIA[ev.kind]}`, href: `#evidencia-${ev.id}`, interno: true } : { texto: "Evidencia no disponible" };
  }
  if (tipo === "snapshot") {
    const ev = incidente.evidence.find((e) => String(e.snapshot_id) === valor);
    if (ev?.block_number) return { texto: `Lectura del bloque ${ev.block_number.toLocaleString("es-AR")}`, href: `#evidencia-${ev.id}`, interno: true };
    return { texto: "Lectura de la posición", href: `/app/${org}/posiciones/${incidente.account_id}` };
  }
  if (tipo === "rule_version" && Number(valor) === incidente.policy_version) {
    return { texto: `Política, versión ${valor}`, href: `/app/${org}/configuracion#politica-${incidente.policy_id}` };
  }
  return { texto: "Referencia no disponible" };
}

