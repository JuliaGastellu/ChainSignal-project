import { Link } from "react-router-dom";
import { useResumen } from "@/lib/consultas";
import { haceCuanto, SEVERIDADES } from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import type { Resumen as DatosResumen, Severidad } from "@/lib/tipos";
import { Cargando, ErrorVista, Tarjeta } from "@/components/Estados";
import { cn } from "@/lib/utils";

const PASOS: { clave: keyof DatosResumen["checklist"]; texto: string; ruta: string }[] = [
  { clave: "account_added", texto: "Agregar una dirección de Ethereum para observar", ruta: "posiciones" },
  { clave: "first_snapshot", texto: "Obtener el primer snapshot de Aave V3", ruta: "posiciones" },
  { clave: "policy_created", texto: "Crear una política de alerta", ruta: "configuracion" },
  { clave: "channel_verified", texto: "Probar un canal de notificación", ruta: "configuracion" },
  { clave: "incident_reviewed", texto: "Revisar un incidente", ruta: "incidentes" },
];

const ORDEN_SEVERIDAD: Severidad[] = ["critical", "high", "medium", "low"];

const CALIDADES: Record<string, string> = {
  FRESH: "Actualizadas",
  STALE: "Atrasadas",
  PARTIAL: "Parciales",
  UNAVAILABLE: "Sin datos",
  NOT_EVALUATED: "Sin evaluar",
};

export default function Resumen() {
  const { org } = useOrgActual();
  const { data, error, isLoading, refetch } = useResumen(org);

  if (isLoading) return <Cargando />;
  if (error || !data) return <ErrorVista error={error} reintentar={() => refetch()} />;

  const completos = PASOS.filter((p) => data.checklist[p.clave]).length;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Resumen</h1>

      {completos < PASOS.length && (
        <Tarjeta titulo={`Primeros pasos (${completos} de ${PASOS.length})`}>
          <ol className="space-y-2">
            {PASOS.map((paso) => {
              const hecho = data.checklist[paso.clave];
              return (
                <li key={paso.clave} className="flex items-center gap-3 text-sm">
                  <span
                    aria-hidden
                    className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs",
                      hecho ? "border-risk-low bg-risk-low text-background" : "border-border")}
                  >
                    {hecho ? "✓" : ""}
                  </span>
                  <span className="sr-only">{hecho ? "Hecho:" : "Pendiente:"}</span>
                  {hecho ? (
                    <span className="text-muted-foreground line-through">{paso.texto}</span>
                  ) : (
                    <Link to={`/app/${org}/${paso.ruta}`} className="text-primary underline-offset-4 hover:underline">
                      {paso.texto}
                    </Link>
                  )}
                </li>
              );
            })}
          </ol>
        </Tarjeta>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tarjeta titulo="Incidentes activos">
          <p className="text-3xl font-semibold">{data.active_incidents}</p>
          {data.active_incidents > 0 ? (
            <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
              {ORDEN_SEVERIDAD.filter((s) => data.active_incidents_by_severity[s]).map((s) => (
                <li key={s}>
                  {SEVERIDADES[s]}: {data.active_incidents_by_severity[s]}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">Ninguna condición abierta.</p>
          )}
          <Link to={`/app/${org}/incidentes`} className="mt-3 inline-block text-sm text-primary underline-offset-4 hover:underline">
            Ver incidentes
          </Link>
        </Tarjeta>
        <Tarjeta titulo="Cuentas observadas">
          <p className="text-3xl font-semibold">{data.accounts}</p>
          <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
            {Object.entries(data.accounts_by_data_quality).map(([calidad, n]) => (
              <li key={calidad}>
                {CALIDADES[calidad] ?? calidad}: {n}
              </li>
            ))}
          </ul>
          <Link to={`/app/${org}/posiciones`} className="mt-3 inline-block text-sm text-primary underline-offset-4 hover:underline">
            Ver posiciones
          </Link>
        </Tarjeta>
        <Tarjeta titulo="Políticas activas">
          <p className="text-3xl font-semibold">{data.enabled_policies}</p>
          <p className="mt-2 text-xs text-muted-foreground">
            Canales probados: {data.verified_channels} de {data.channels}
          </p>
        </Tarjeta>
        <Tarjeta titulo="Última evaluación">
          <p className="text-lg font-semibold">{haceCuanto(data.last_evaluation_at)}</p>
          <p className="mt-2 text-xs text-muted-foreground">Solo lectura en Aave V3, Ethereum mainnet.</p>
        </Tarjeta>
      </div>
    </div>
  );
}
