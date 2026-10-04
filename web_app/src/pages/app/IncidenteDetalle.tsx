import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { describirCalidad } from "@/lib/calidad";
import { useCanales, useCuentas, useIncidente, useMiembros, useMutacionOrg } from "@/lib/consultas";
import {
  acortarDireccion,
  describirCondicion,
  ESTADOS_INCIDENTE,
  formatearFecha,
  formatearNumero,
  haceCuanto,
  SEVERIDADES,
  TIPOS_REGLA,
  TONO_SEVERIDAD,
} from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import type { EstadoCalidad, Evidencia, IncidenteDetalle as Detalle } from "@/lib/tipos";
import { Cargando, Dato, ErrorVista, Insignia, Tarjeta } from "@/components/Estados";
import { ExplicacionIncidente } from "@/components/ExplicacionIncidente";

const TIPOS_EVIDENCIA: Record<Evidencia["kind"], string> = {
  opening: "Apertura",
  escalation: "Escalamiento",
  resolution: "Resolución",
  correction: "Corrección",
};

const ESTADOS_ENTREGA: Record<string, string> = {
  pending: "Pendiente",
  sending: "Enviando",
  sent: "Enviada",
  failed: "Falló",
  dead: "Sin entregar: agotó los reintentos",
};

function Umbral({ incidente }: { incidente: Detalle }) {
  const v = incidente.last_observed ?? {};
  if (incidente.rule_type === "health_factor_below") {
    return (
      <>
        Menor a {formatearNumero(v.threshold as string, 4)}
        {v.clear_above != null && (
          <span className="block text-xs font-normal text-muted-foreground">Se despeja sobre {formatearNumero(v.clear_above as string, 4)}</span>
        )}
      </>
    );
  }
  if (incidente.rule_type === "debt_change") return <>Cambio de {formatearNumero(v.change_pct_threshold as string)} % o más</>;
  return <>Máximo {Math.round(Number(v.max_age_seconds) / 60)} min sin dato fresco</>;
}

function Valor({ incidente }: { incidente: Detalle }) {
  const v = incidente.last_observed ?? {};
  if (incidente.rule_type === "health_factor_below") return <>{v.no_debt ? "Sin deuda" : formatearNumero(v.health_factor as string, 4)}</>;
  if (incidente.rule_type === "debt_change") return <>{v.change_pct ? `${formatearNumero(v.change_pct as string)} %` : "De cero a deuda"}</>;
  return <>{v.age_seconds == null ? "Sin lectura fresca" : `${Math.round(Number(v.age_seconds) / 60)} min`}</>;
}

function Acciones({ incidente }: { incidente: Detalle }) {
  const { org, puede } = useOrgActual();
  const [nota, setNota] = useState("");
  const reconocer = useMutacionOrg(org, () => api.reconocer(org, incidente.id));
  const resolver = useMutacionOrg(org, () => api.resolver(org, incidente.id, nota.trim()));

  if (incidente.status === "resolved") return null;
  if (!puede("operator")) {
    return <p className="text-sm text-muted-foreground">Tu rol es de lectura: una persona operadora puede tomar y resolver este incidente.</p>;
  }
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (nota.trim()) resolver.mutate(undefined, { onSuccess: () => setNota("") });
  };
  return (
    <Tarjeta titulo="Seguimiento">
      <div className="space-y-4">
        {incidente.status === "open" && (
          <div>
            <button
              type="button"
              onClick={() => reconocer.mutate(undefined)}
              disabled={reconocer.isPending}
              className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {reconocer.isPending ? "Tomando…" : "Tomar el incidente"}
            </button>
            <p className="mt-1 text-xs text-muted-foreground">Queda registrado que estás a cargo; las alertas siguen si la condición empeora.</p>
          </div>
        )}
        {reconocer.error && <ErrorVista error={reconocer.error} />}
        <form onSubmit={enviar} className="space-y-2">
          <label className="block text-sm">
            Nota de resolución
            <textarea
              value={nota}
              onChange={(e) => setNota(e.target.value)}
              maxLength={500}
              rows={3}
              required
              placeholder="Qué hiciste o por qué lo cerrás"
              className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={resolver.isPending || !nota.trim()}
            className="rounded border border-border px-4 py-2 text-sm hover:border-primary disabled:opacity-50"
          >
            {resolver.isPending ? "Resolviendo…" : "Resolver"}
          </button>
        </form>
        {resolver.error && <ErrorVista error={resolver.error} />}
      </div>
    </Tarjeta>
  );
}

export default function IncidenteDetalle() {
  const { incidente: id = "" } = useParams();
  const { org } = useOrgActual();
  const { data: incidente, error, isLoading, refetch } = useIncidente(org, id);
  const miembros = useMiembros(org);
  const cuentas = useCuentas(org);
  const canales = useCanales(org);

  if (isLoading) return <Cargando />;
  if (error || !incidente) return <ErrorVista error={error} reintentar={() => refetch()} />;

  const persona = (userId: string | null) =>
    userId ? (miembros.data?.find((m) => m.user_id === userId)?.email ?? "Persona fuera de la organización") : null;
  const cuenta = cuentas.data?.find((c) => c.id === incidente.account_id);
  const canal = (canalId: string) => canales.data?.find((c) => c.id === canalId)?.name ?? "Canal";
  const apertura = incidente.evidence.find((e) => e.kind === "opening");
  const calidad = describirCalidad({
    status: incidente.data_quality as EstadoCalidad,
    reason: "none",
    actionable_allowed: incidente.data_quality === "FRESH",
    no_activity: false,
    complete_history: true,
  });
  const responsable = persona(incidente.acknowledged_by_user_id) ?? persona(incidente.resolved_by_user_id);

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/app/${org}/incidentes`} className="text-sm text-primary underline-offset-4 hover:underline">
          ← Incidentes
        </Link>
        <h1 className="mt-2 text-xl font-semibold">{TIPOS_REGLA[incidente.rule_type] ?? incidente.rule_type}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Insignia tono={TONO_SEVERIDAD[incidente.severity]}>{SEVERIDADES[incidente.severity]}</Insignia>
          <Insignia tono="neutro">{ESTADOS_INCIDENTE[incidente.status]}</Insignia>
          {incidente.escalation_level > 0 && <Insignia tono="error">Escalado</Insignia>}
        </div>
      </div>

      <Tarjeta titulo="Condición">
        <p className="mb-4 text-sm">{describirCondicion(incidente)}</p>
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Dato etiqueta="Cuenta">
            {cuenta ? (
              <Link to={`/app/${org}/posiciones/${cuenta.id}`} className="text-primary underline-offset-4 hover:underline">
                {cuenta.label || acortarDireccion(cuenta.address)}
              </Link>
            ) : (
              "—"
            )}
          </Dato>
          <Dato etiqueta="Valor observado">
            <Valor incidente={incidente} />
          </Dato>
          <Dato etiqueta="Umbral">
            <Umbral incidente={incidente} />
          </Dato>
          <Dato etiqueta="Bloque de apertura">
            {apertura?.block_number ? apertura.block_number.toLocaleString("es-AR") : "—"}
            {apertura?.block_hash && <span className="block break-all font-mono text-xs font-normal text-muted-foreground">{apertura.block_hash}</span>}
          </Dato>
          <Dato etiqueta="Calidad del dato">{calidad.etiqueta}</Dato>
          <Dato etiqueta="Última evaluación">{haceCuanto(incidente.last_evaluated_at)}</Dato>
          <Dato etiqueta="Responsable">{responsable ?? "Sin asignar"}</Dato>
          <Dato etiqueta="Política">Versión {incidente.policy_version}</Dato>
        </dl>
        {incidente.resolution_note && (
          <p className="mt-4 rounded border border-border bg-muted p-3 text-sm">
            <span className="font-medium">Nota de resolución:</span> {incidente.resolution_note}
          </p>
        )}
      </Tarjeta>

      <ExplicacionIncidente incidente={incidente.id} />

      <Acciones incidente={incidente} />

      <Tarjeta titulo="Historial y evidencia">
        <ol className="space-y-3">
          {incidente.evidence.map((e) => (
            <li key={e.id} className="border-l-2 border-border pl-3 text-sm">
              <p className="font-medium">
                {TIPOS_EVIDENCIA[e.kind]} · <span className="font-normal text-muted-foreground">{formatearFecha(e.created_at)}</span>
              </p>
              {e.block_number && <p className="text-xs text-muted-foreground">Bloque {e.block_number.toLocaleString("es-AR")}</p>}
              {e.note && <p className="mt-1">{e.note}</p>}
              {e.corrects_evidence_id && <p className="text-xs text-muted-foreground">Corrige la evidencia #{e.corrects_evidence_id}; la original no se modifica.</p>}
              {persona(e.created_by_user_id) && <p className="text-xs text-muted-foreground">Por {persona(e.created_by_user_id)}</p>}
            </li>
          ))}
          {incidente.acknowledged_at && (
            <li className="border-l-2 border-primary pl-3 text-sm">
              <p className="font-medium">
                Tomado · <span className="font-normal text-muted-foreground">{formatearFecha(incidente.acknowledged_at)}</span>
              </p>
              <p className="text-xs text-muted-foreground">Por {persona(incidente.acknowledged_by_user_id) ?? "—"}</p>
            </li>
          )}
        </ol>
      </Tarjeta>

      <Tarjeta titulo="Notificaciones">
        {incidente.deliveries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay canales activos que recibieran este incidente.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {incidente.deliveries.map((d) => (
              <li key={`${d.alert_id}-${d.channel_id}`} className="flex flex-wrap gap-x-2">
                <span className="font-medium">{canal(d.channel_id)}</span>
                <span>{ESTADOS_ENTREGA[d.status] ?? d.status}</span>
                <span className="text-muted-foreground">
                  {d.sent_at ? formatearFecha(d.sent_at) : `${d.attempts} intento${d.attempts === 1 ? "" : "s"}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Tarjeta>
    </div>
  );
}
