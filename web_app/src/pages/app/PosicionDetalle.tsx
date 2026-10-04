import { Link, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { describirCalidad } from "@/lib/calidad";
import { useCuentas, useIncidentes, useMutacionOrg, usePoliticas, usePosicion } from "@/lib/consultas";
import {
  actividadCuenta,
  alertasCuenta,
  describirCondicion,
  formatearFecha,
  formatearMontoBase,
  formatearNumero,
  frescuraDato,
  haceCuanto,
  SEVERIDADES,
  TEXTO_FRESCURA,
  TONO_SEVERIDAD,
} from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import { traducirDetalle, traducirLimite } from "@/lib/traducciones";
import type { Posicion } from "@/lib/tipos";
import { Boton, Cargando, Dato, DetalleTecnico, ErrorVista, Insignia, Senales, Tarjeta, Titulo, Vacio } from "@/components/Estados";

function Calidad({ posicion }: { posicion: Posicion }) {
  const calidad = posicion.data_quality;
  if (calidad.status === "FRESH") return null;
  const d = describirCalidad({ status: calidad.status, reason: calidad.reason, actionable_allowed: false, no_activity: false, complete_history: true });
  const detalle = calidad.detail ? traducirDetalle(calidad.detail) : null;
  return (
    <div className="mt-4 rounded border border-risk-medium/40 bg-risk-medium/10 p-3 text-sm">
      <p className="font-medium">{d.etiqueta}</p>
      <p className="mt-1">{d.mensaje}</p>
      {detalle?.traducido && <p className="mt-1">{detalle.texto}</p>}
      {calidad.detail && <DetalleTecnico>{`${calidad.status} · ${calidad.reason} · ${calidad.detail}`}</DetalleTecnico>}
    </div>
  );
}

function Activos({ posicion }: { posicion: Posicion }) {
  if (!posicion.assets.length) return null;
  return (
    <Tarjeta titulo="Activos en la posición">
      {/* En pantallas angostas, una tarjeta por activo en lugar de una tabla con scroll horizontal. */}
      <ul className="space-y-2 sm:hidden" aria-label="Activos">
        {posicion.assets.map((a) => (
          <li key={a.asset} className="rounded border border-border p-3 text-sm">
            <p className="font-medium">{a.symbol}</p>
            <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1">
              <dt className="text-muted-foreground">Depositado</dt>
              <dd className="text-right tabular-nums">{formatearNumero(a.supplied, 4)}</dd>
              <dt className="text-muted-foreground">Deuda variable</dt>
              <dd className="text-right tabular-nums">{formatearNumero(a.variable_debt, 4)}</dd>
              <dt className="text-muted-foreground">Como colateral</dt>
              <dd className="text-right">{a.used_as_collateral ? "Sí" : "No"}</dd>
              <dt className="text-muted-foreground">Umbral de liquidación</dt>
              <dd className="text-right tabular-nums">{formatearNumero(a.liquidation_threshold_pct)} %</dd>
            </dl>
          </li>
        ))}
      </ul>
      <div className="hidden sm:block">
        <table className="w-full text-sm">
          <caption className="sr-only">Activos de la posición</caption>
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="py-1 pr-3 font-medium">Activo</th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">Depositado</th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">Deuda variable</th>
              <th scope="col" className="py-1 pr-3 font-medium">Como colateral</th>
              <th scope="col" className="py-1 text-right font-medium">Umbral de liquidación</th>
            </tr>
          </thead>
          <tbody>
            {posicion.assets.map((a) => (
              <tr key={a.asset} className="border-t border-border">
                <th scope="row" className="py-2 pr-3 text-left font-medium">{a.symbol}</th>
                <td className="py-2 pr-3 text-right tabular-nums">{formatearNumero(a.supplied, 4)}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{formatearNumero(a.variable_debt, 4)}</td>
                <td className="py-2 pr-3">{a.used_as_collateral ? "Sí" : "No"}</td>
                <td className="py-2 text-right tabular-nums">{formatearNumero(a.liquidation_threshold_pct)} %</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Tarjeta>
  );
}

export default function PosicionDetalle() {
  const { cuenta: cuentaId = "" } = useParams();
  const { org, puede } = useOrgActual();
  const cuentas = useCuentas(org);
  const posicion = usePosicion(org, cuentaId);
  const politicas = usePoliticas(org);
  const incidentes = useIncidentes(org, "active");
  const leer = useMutacionOrg(org, () => api.leerPosicion(org, cuentaId));
  const evaluar = useMutacionOrg(org, () => api.evaluar(org, cuentaId));

  if (cuentas.isLoading || posicion.isLoading) return <Cargando />;
  if (cuentas.error) return <ErrorVista error={cuentas.error} reintentar={() => cuentas.refetch()} />;
  const cuenta = cuentas.data?.find((c) => c.id === cuentaId);
  if (!cuenta) return <Vacio titulo="No encontré esta cuenta">Puede haber sido eliminada o pertenecer a otra organización.</Vacio>;

  // Una lectura en vivo que falló (dato no disponible) no se guarda como snapshot:
  // si es más reciente que el último guardado, la muestro para no esconder la falla.
  const enVivo = leer.data;
  const datos = enVivo && (!posicion.data || (enVivo.read_at ?? 0) > (posicion.data.read_at ?? 0)) ? enVivo : posicion.data;
  const abiertos = (incidentes.data ?? []).filter((i) => i.account_id === cuentaId);
  const alertas = alertasCuenta(abiertos);
  const frescura = frescuraDato(datos, cuenta.interval_seconds);
  const umbrales = (politicas.data ?? [])
    .filter((p) => p.enabled && p.rule.type === "health_factor_below" && (p.account_id === null || p.account_id === cuentaId))
    .map((p) => String(p.rule.threshold));

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/app/${org}/posiciones`} className="text-sm text-primary underline-offset-4 hover:underline">
          ← Posiciones
        </Link>
        <div className="mt-2">
          <Titulo>{cuenta.label || "Cuenta observada"}</Titulo>
        </div>
        <p className="break-all font-mono text-xs text-muted-foreground">{cuenta.address}</p>
      </div>

      <Senales alertas={alertas} dato={TEXTO_FRESCURA[frescura]} actividad={actividadCuenta(datos)} />

      {abiertos.length > 0 && (
        <section aria-label="Alertas abiertas" className="rounded-lg border border-risk-high/50 bg-risk-high/10 p-4">
          <h2 className="text-base font-semibold">Alertas abiertas</h2>
          <ul className="mt-2 space-y-2">
            {abiertos.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2 text-sm">
                <Insignia tono={TONO_SEVERIDAD[i.severity]}>{SEVERIDADES[i.severity]}</Insignia>
                <Link to={`/app/${org}/incidentes/${i.id}`} className="text-primary underline-offset-4 hover:underline">
                  {describirCondicion(i)}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {datos?.synthetic && <Insignia tono="aviso">Datos sintéticos</Insignia>}
        {puede("viewer") && (
          <Boton onClick={() => leer.mutate(undefined)} disabled={leer.isPending}>
            {leer.isPending ? "Leyendo…" : datos ? "Leer de nuevo" : "Obtener primer snapshot"}
          </Boton>
        )}
        {puede("operator") && (
          <Boton onClick={() => evaluar.mutate(undefined)} disabled={evaluar.isPending}>
            Evaluar políticas ahora
          </Boton>
        )}
        {evaluar.data && (
          <span role="status" className="text-sm text-muted-foreground">
            {evaluar.data.status === "done" ? "Evaluación hecha." : evaluar.data.status === "already_queued" ? "Ya había una evaluación en cola." : "Evaluación en cola."}
          </span>
        )}
      </div>
      {leer.error && <ErrorVista error={leer.error} />}
      {evaluar.error && <ErrorVista error={evaluar.error} />}
      {posicion.error && <ErrorVista error={posicion.error} reintentar={() => posicion.refetch()} />}

      {!datos ? (
        !posicion.error && (
          <Vacio titulo="Todavía no hay un snapshot de esta cuenta">
            El monitoreo la lee en su próximo ciclo. También podés obtener el primer snapshot ahora.
          </Vacio>
        )
      ) : (
        <>
          <Tarjeta titulo="Estado de la posición">
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Dato etiqueta="Health factor">
                {datos.no_debt ? "No aplica (sin deuda)" : <span className="text-xl tabular-nums">{formatearNumero(datos.health_factor, 4)}</span>}
              </Dato>
              <Dato etiqueta="Umbral de alerta (tu política)">
                {umbrales.length ? umbrales.map((u) => formatearNumero(u, 4)).join(", ") : "Sin política de health factor"}
              </Dato>
              <Dato etiqueta="Colateral">{formatearMontoBase(datos.collateral_base)}</Dato>
              <Dato etiqueta="Deuda">{formatearMontoBase(datos.debt_base)}</Dato>
              <Dato etiqueta="Disponible para pedir">{formatearMontoBase(datos.available_borrows_base)}</Dato>
              <Dato etiqueta="Umbral de liquidación del protocolo">
                {datos.liquidation_threshold_pct ? `${formatearNumero(datos.liquidation_threshold_pct)} % del colateral` : "—"}
              </Dato>
              <Dato etiqueta="Bloque">
                {datos.block ? (
                  <>
                    {datos.block.number.toLocaleString("es-AR")}
                    <span className="block text-xs font-normal text-muted-foreground">{formatearFecha(datos.block.timestamp)}</span>
                  </>
                ) : (
                  "—"
                )}
              </Dato>
              <Dato etiqueta="Última lectura">
                {haceCuanto(datos.read_at)}
                <span className="block text-xs font-normal text-muted-foreground">Se evalúa cada {Math.round(cuenta.interval_seconds / 60)} min</span>
              </Dato>
            </dl>
            <p className="mt-4 text-xs text-muted-foreground">
              El umbral de alerta es tu política para avisarte antes. Aave permite liquidar una posición cuando el health factor queda por debajo de 1;
              no son la misma cosa.
            </p>
            <Calidad posicion={datos} />
            {actividadCuenta(datos).etiqueta === "Sin posiciones en Aave V3" && (
              <p className="mt-4 text-sm text-muted-foreground">Esta dirección no tiene depósitos ni deuda en Aave V3. No es un error: no hay nada que vigilar todavía.</p>
            )}
          </Tarjeta>
          <Activos posicion={datos} />
          {datos.limitations.length > 0 && (
            <Tarjeta titulo="Límites de esta lectura">
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {datos.limitations.map((l) => (
                  <li key={l}>{traducirLimite(l).texto}</li>
                ))}
              </ul>
              <DetalleTecnico titulo="Texto original y procedencia">
                <ul className="space-y-1">
                  {datos.limitations.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                  {datos.block && <li>bloque {datos.block.number} · {datos.block.hash}</li>}
                </ul>
              </DetalleTecnico>
            </Tarjeta>
          )}
        </>
      )}
    </div>
  );
}
