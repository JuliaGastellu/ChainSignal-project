// Estructura de la app privada: encabezado con organización, conexión en vivo y
// sesión; navegación entre Resumen, Posiciones, Incidentes y Configuración.

import { useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { useResumen } from "@/lib/consultas";
import { formatearFecha } from "@/lib/formato";
import { rolAlcanza, useSesion, type OrgActual } from "@/lib/sesion";
import { useEventosOrg, type EstadoConexion } from "@/hooks/useEventosOrg";
import { ErrorVista } from "@/components/Estados";
import { AvisoPlan } from "@/components/PlanOrganizacion";
import { cn } from "@/lib/utils";

const SECCIONES = [
  { ruta: "resumen", texto: "Resumen" },
  { ruta: "posiciones", texto: "Posiciones" },
  { ruta: "incidentes", texto: "Incidentes" },
  { ruta: "configuracion", texto: "Configuración" },
];

const CONEXION: Record<EstadoConexion, { texto: string; clase: string }> = {
  conectando: { texto: "Conectando…", clase: "bg-muted-foreground" },
  conectado: { texto: "En vivo", clase: "bg-risk-low" },
  reconectando: { texto: "Reconectando…", clase: "bg-risk-medium" },
  detenido: { texto: "Sin actualizaciones en vivo", clase: "bg-risk-high" },
};

export function AppLayout() {
  const { org = "" } = useParams();
  const sesion = useSesion();
  const navigate = useNavigate();
  const cliente = useQueryClient();
  const membresia = sesion?.memberships.find((m) => m.organization_id === org);
  const resumen = useResumen(membresia ? org : "");
  const conexion = useEventosOrg(membresia ? org : undefined);

  const cerrarSesion = async () => {
    try {
      await api.logout();
    } finally {
      cliente.clear();
      navigate("/login", { replace: true });
    }
  };

  if (!sesion) return null;
  if (!membresia) {
    return (
      <main className="mx-auto max-w-lg p-6">
        <ErrorVista error={new ApiError(403, "forbidden", "")} />
        <p className="mt-4 text-sm text-muted-foreground">No sos miembro de esta organización.</p>
      </main>
    );
  }

  const esDemo = resumen.data?.organization.is_demo ?? false;
  const contexto: OrgActual = { org, rol: membresia.role, esDemo, puede: (minimo) => rolAlcanza(membresia.role, minimo) };
  const activos = resumen.data?.active_incidents ?? 0;

  return (
    <div className="min-h-screen bg-background">
      <a href="#contenido" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-card focus:px-3 focus:py-2">
        Saltar al contenido
      </a>
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <span className="font-semibold">ChainSignal</span>
          {sesion.memberships.length > 1 ? (
            <label className="flex items-center gap-2 text-sm">
              <span className="sr-only">Organización</span>
              <select
                value={org}
                onChange={(e) => navigate(`/app/${e.target.value}/resumen`)}
                className="max-w-[12rem] rounded border border-border bg-background px-2 py-1 text-sm"
              >
                {sesion.memberships.map((m) => (
                  <option key={m.organization_id} value={m.organization_id}>
                    {m.organization_name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <span className="text-sm text-muted-foreground">{membresia.organization_name}</span>
          )}
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground" role="status" aria-live="polite">
            <span aria-hidden className={cn("inline-block h-2 w-2 rounded-full", CONEXION[conexion].clase)} />
            {CONEXION[conexion].texto}
          </span>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="hidden text-muted-foreground sm:inline">{sesion.user.email}</span>
            <button type="button" onClick={cerrarSesion} className="text-primary underline-offset-4 hover:underline">
              Cerrar sesión
            </button>
          </div>
        </div>
        <nav aria-label="Secciones" className="mx-auto max-w-6xl overflow-x-auto px-4">
          <ul className="flex gap-1">
            {SECCIONES.map((s) => (
              <li key={s.ruta}>
                <NavLink
                  to={`/app/${org}/${s.ruta}`}
                  className={({ isActive }) =>
                    cn(
                      "inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2 text-sm",
                      isActive ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                    )
                  }
                >
                  {s.texto}
                  {s.ruta === "incidentes" && activos > 0 && (
                    <span className="rounded-full bg-risk-high px-1.5 text-xs font-semibold text-background" aria-label={`${activos} activos`}>
                      {activos}
                    </span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      {esDemo && (
        <div className="border-b border-risk-medium/40 bg-risk-medium/10 px-4 py-2 text-center text-sm">
          Estás en una demo con datos sintéticos, aislada de cualquier cuenta real. Vence el {formatearFecha(resumen.data?.organization.expires_at)}
        </div>
      )}
      <main id="contenido" className="mx-auto max-w-6xl px-4 py-6">
        <AvisoPlan org={org} />
        <Outlet context={contexto} />
      </main>
    </div>
  );
}
