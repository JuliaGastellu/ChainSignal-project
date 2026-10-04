// Explicación del incidente: por defecto la plantilla determinista. Si una
// persona operadora la genera y el modelo está habilitado, muestro la del
// modelo solo si pasó la validación; si no, la API devuelve la plantilla y el
// motivo.
//
// Cada enunciado cita referencias internas (snapshot:N, rule_version:N,
// evidence:N). Las convierto en enlaces legibles hacia la evidencia de este
// mismo incidente, que ya llegó autorizada para esta organización. Una
// referencia que no está en el incidente no se enlaza. Las referencias
// originales quedan en "Procedencia".

import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { claves, useExplicacion } from "@/lib/consultas";
import { useOrgActual } from "@/lib/sesion";
import { enlaceDeReferencia } from "@/lib/referencias";
import type { IncidenteDetalle } from "@/lib/tipos";
import { Boton, Cargando, DetalleTecnico, ErrorVista, Insignia, Tarjeta } from "@/components/Estados";

const MOTIVOS: Record<string, string> = {
  model_disabled: "el modelo no está habilitado",
  budget_exceeded: "se alcanzó el presupuesto diario",
  timeout: "el modelo no respondió a tiempo",
  rate_limited: "el proveedor del modelo limitó las consultas",
  provider_error: "el proveedor del modelo falló",
  invalid_response: "el proveedor devolvió una respuesta inválida",
  invalid_json: "el modelo no devolvió JSON",
  validation_failed: "la salida del modelo no pasó la validación",
};

function Referencias({ refs, incidente, org }: { refs: string[]; incidente: IncidenteDetalle; org: string }) {
  return (
    <span className="text-xs text-muted-foreground">
      {" ("}
      {refs.map((ref, i) => {
        const e = enlaceDeReferencia(ref, incidente, org);
        const separador = i < refs.length - 1 ? ", " : "";
        if (!e.href) return <span key={ref}>{e.texto}{separador}</span>;
        return (
          <span key={ref}>
            {e.interno ? (
              <a href={e.href} className="text-primary underline-offset-4 hover:underline">{e.texto}</a>
            ) : (
              <Link to={e.href} className="text-primary underline-offset-4 hover:underline">{e.texto}</Link>
            )}
            {separador}
          </span>
        );
      })}
      {")"}
    </span>
  );
}

export function ExplicacionIncidente({ incidente }: { incidente: IncidenteDetalle }) {
  const { org, puede } = useOrgActual();
  const { data, error, isLoading, refetch } = useExplicacion(org, incidente.id);
  const cliente = useQueryClient();
  // Muestro lo que devolvió la generación; no vuelvo a pedir la última guardada.
  const generar = useMutation({
    mutationFn: () => api.generarExplicacion(org, incidente.id),
    onSuccess: (nueva) => cliente.setQueryData(claves.explicacion(org, incidente.id), nueva),
  });

  return (
    <Tarjeta
      titulo="Explicación"
      accion={
        puede("operator") && (
          <Boton onClick={() => generar.mutate()} disabled={generar.isPending}>
            {generar.isPending ? "Generando…" : "Generar explicación"}
          </Boton>
        )
      }
    >
      {isLoading ? (
        <Cargando />
      ) : error || !data ? (
        <ErrorVista error={error} reintentar={() => refetch()} />
      ) : (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Insignia tono="neutro">{data.source === "model" ? `Redactada por modelo (${data.model})` : "Plantilla determinista"}</Insignia>
            {data.fallback_reason && data.fallback_reason !== "not_generated" && (
              <span className="text-xs text-muted-foreground">Usé la plantilla porque {MOTIVOS[data.fallback_reason] ?? data.fallback_reason}.</span>
            )}
          </div>
          <p className="font-medium">{data.explanation.summary}</p>
          <ul className="space-y-1">
            {data.explanation.statements.map((e, i) => (
              <li key={i}>
                {e.text}
                <Referencias refs={e.refs} incidente={incidente} org={org} />
              </li>
            ))}
          </ul>
          {data.explanation.caveats.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
              {data.explanation.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
          <DetalleTecnico titulo="Procedencia">
            <ul className="space-y-0.5">
              {data.explanation.statements.map((e, i) => (
                <li key={i}>
                  enunciado {i + 1}: {e.refs.join(", ")}
                </li>
              ))}
              {data.validation_errors.length > 0 && <li>validación: {data.validation_errors.join("; ")}</li>}
            </ul>
          </DetalleTecnico>
        </div>
      )}
      {generar.error && <div className="mt-3"><ErrorVista error={generar.error} /></div>}
    </Tarjeta>
  );
}
