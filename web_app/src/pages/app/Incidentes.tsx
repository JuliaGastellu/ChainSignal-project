import { useState } from "react";
import { Link } from "react-router-dom";
import { useCuentas, useIncidentes } from "@/lib/consultas";
import { acortarDireccion, describirCondicion, ESTADOS_INCIDENTE, haceCuanto, SEVERIDADES, TIPOS_REGLA, TONO_SEVERIDAD } from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import { Cargando, ErrorVista, Insignia, Vacio } from "@/components/Estados";
import { cn } from "@/lib/utils";

export default function Incidentes() {
  const { org } = useOrgActual();
  const [vista, setVista] = useState<"active" | "resolved">("active");
  const { data, error, isLoading, refetch } = useIncidentes(org, vista);
  const cuentas = useCuentas(org);
  const nombre = (id: string) => {
    const c = cuentas.data?.find((x) => x.id === id);
    return c ? c.label || acortarDireccion(c.address) : "Cuenta";
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Incidentes</h1>
      <div role="tablist" aria-label="Estado de los incidentes" className="flex gap-2">
        {(["active", "resolved"] as const).map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={vista === v}
            onClick={() => setVista(v)}
            className={cn("rounded-full border px-3 py-1 text-sm", vista === v ? "border-primary bg-primary/10" : "border-border text-muted-foreground")}
          >
            {v === "active" ? "Activos" : "Resueltos"}
          </button>
        ))}
      </div>
      {isLoading ? (
        <Cargando />
      ) : error ? (
        <ErrorVista error={error} reintentar={() => refetch()} />
      ) : !data?.length ? (
        <Vacio titulo={vista === "active" ? "No hay incidentes activos" : "Todavía no hay incidentes resueltos"}>
          {vista === "active" && "Cuando una política detecte una condición, el incidente aparece aquí."}
        </Vacio>
      ) : (
        <ul className="space-y-2" aria-label={vista === "active" ? "Incidentes activos" : "Incidentes resueltos"}>
          {data.map((i) => (
            <li key={i.id}>
              <Link to={`/app/${org}/incidentes/${i.id}`} className="block rounded-lg border border-border bg-card p-4 hover:border-primary/60">
                <div className="flex flex-wrap items-center gap-2">
                  <Insignia tono={TONO_SEVERIDAD[i.severity]}>{SEVERIDADES[i.severity]}</Insignia>
                  <Insignia tono="neutro">{ESTADOS_INCIDENTE[i.status]}</Insignia>
                  <span className="text-sm font-medium">{TIPOS_REGLA[i.rule_type] ?? i.rule_type}</span>
                  <span className="text-sm text-muted-foreground">· {nombre(i.account_id)}</span>
                </div>
                <p className="mt-2 text-sm">{describirCondicion(i)}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Abierto {haceCuanto(i.opened_at)} · Última evaluación {haceCuanto(i.last_evaluated_at)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
