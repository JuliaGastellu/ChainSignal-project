import { createContext, useContext } from "react";
import { useOutletContext } from "react-router-dom";
import type { SesionApi } from "@/lib/api";
import type { Rol } from "@/lib/tipos";

// Sesión verificada por RequireSession, disponible para las páginas privadas.
export const SesionContext = createContext<SesionApi | null>(null);

export function useSesion(): SesionApi | null {
  return useContext(SesionContext);
}

const ORDEN_ROLES: Record<Rol, number> = { viewer: 0, operator: 1, owner: 2 };

export function rolAlcanza(rol: Rol, minimo: Rol): boolean {
  return ORDEN_ROLES[rol] >= ORDEN_ROLES[minimo];
}

// Organización activa dentro de /app/:org. El rol solo decide qué controles
// muestro; la API vuelve a autorizar cada pedido.
export interface OrgActual {
  org: string;
  rol: Rol;
  esDemo: boolean;
  puede: (minimo: Rol) => boolean;
}

export function useOrgActual(): OrgActual {
  return useOutletContext<OrgActual>();
}
