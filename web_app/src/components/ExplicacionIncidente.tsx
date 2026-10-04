// Explicación del incidente: por defecto la plantilla determinista. Si una
// persona operadora la genera y el modelo está habilitado, muestro la del
// modelo solo si pasó la validación; si no, la API devuelve la plantilla y el
// motivo. Las referencias apuntan al snapshot, la versión de la regla y la
// evidencia que respaldan cada enunciado.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { claves, useExplicacion } from "@/lib/consultas";
import { useOrgActual } from "@/lib/sesion";
import { Cargando, ErrorVista, Insignia, Tarjeta } from "@/components/Estados";

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

export function ExplicacionIncidente({ incidente }: { incidente: string }) {
  const { org, puede } = useOrgActual();
  const { data, error, isLoading, refetch } = useExplicacion(org, incidente);
  const cliente = useQueryClient();
  // Muestro lo que devolvió la generación; no vuelvo a pedir la última guardada.
  const generar = useMutation({
    mutationFn: () => api.generarExplicacion(org, incidente),
    onSuccess: (nueva) => cliente.setQueryData(claves.explicacion(org, incidente), nueva),
  });

  return (
    <Tarjeta
      titulo="Explicación"
      accion={
        puede("operator") && (
          <button
            type="button"
            onClick={() => generar.mutate()}
            disabled={generar.isPending}
            className="rounded border border-border px-3 py-1 text-sm hover:border-primary disabled:opacity-50"
          >
            {generar.isPending ? "Generando…" : "Generar explicación"}
          </button>
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
                {e.text} <span className="font-mono text-xs text-muted-foreground">[{e.refs.join(", ")}]</span>
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
        </div>
      )}
      {generar.error && <div className="mt-3"><ErrorVista error={generar.error} /></div>}
    </Tarjeta>
  );
}
