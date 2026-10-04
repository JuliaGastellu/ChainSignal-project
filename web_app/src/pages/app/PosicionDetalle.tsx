import { Link, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { describirCalidad } from "@/lib/calidad";
import { useCuentas, useIncidentes, useMutacionOrg, usePoliticas, usePosicion } from "@/lib/consultas";
import {
  describirCondicion,
  estadoCuenta,
  formatearFecha,
  formatearMontoBase,
  formatearNumero,
  haceCuanto,
  SEVERIDADES,
  TEXTO_ESTADO_CUENTA,
} from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import type { Posicion } from "@/lib/tipos";
import { Cargando, Dato, ErrorVista, Insignia, Tarjeta, Vacio } from "@/components/Estados";

function Calidad({ posicion }: { posicion: Posicion }) {
  const d = describirCalidad({
    status: posicion.data_quality.status,
    reason: posicion.data_quality.reason,
    actionable_allowed: posicion.data_quality.status === "FRESH",
    no_activity: false,
    complete_history: true,
  });
  return (
    <div className="space-y-1">
      <Insignia tono={d.tono === "ok" ? "ok" : d.tono === "aviso" ? "aviso" : "error"}>{d.etiqueta}</Insignia>
      {posicion.data_quality.status !== "FRESH" && <p className="text-sm text-muted-foreground">{d.mensaje}</p>}
    </div>
  );
}

function Activos({ posicion }: { posicion: Posicion }) {
  if (!posicion.assets.length) return null;
  return (
    <Tarjeta titulo="Activos en la posición">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="py-1 pr-3 font-medium">Activo</th>
              <th scope="col" className="py-1 pr-3 font-medium">Depositado</th>
              <th scope="col" className="py-1 pr-3 font-medium">Deuda variable</th>
              <th scope="col" className="py-1 pr-3 font-medium">Como colateral</th>
              <th scope="col" className="py-1 font-medium">Umbral de liquidación</th>
            </tr>
          </thead>
          <tbody>
            {posicion.assets.map((a) => (
              <tr key={a.asset} className="border-t border-border">
                <th scope="row" className="py-2 pr-3 text-left font-medium">{a.symbol}</th>
                <td className="py-2 pr-3">{formatearNumero(a.supplied, 4)}</td>
                <td className="py-2 pr-3">{formatearNumero(a.variable_debt, 4)}</td>
                <td className="py-2 pr-3">{a.used_as_collateral ? "Sí" : "No"}</td>
                <td className="py-2">{formatearNumero(a.liquidation_threshold_pct)} %</td>
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
  if (!cuenta) return <Vacio titulo="No encontramos esta cuenta">Puede haber sido eliminada o pertenecer a otra organización.</Vacio>;

  const datos = posicion.data;
  const estado = estadoCuenta(datos, cuenta.interval_seconds);
  const texto = TEXTO_ESTADO_CUENTA[estado];
  const umbrales = (politicas.data ?? [])
    .filter((p) => p.enabled && p.rule.type === "health_factor_below" && (p.account_id === null || p.account_id === cuentaId))
    .map((p) => String(p.rule.threshold));
  const abiertos = (incidentes.data ?? []).filter((i) => i.account_id === cuentaId);

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/app/${org}/posiciones`} className="text-sm text-primary underline-offset-4 hover:underline">
          ← Posiciones
        </Link>
        <h1 className="mt-2 text-xl font-semibold">{cuenta.label || "Cuenta observada"}</h1>
        <p className="break-all font-mono text-xs text-muted-foreground">{cuenta.address}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Insignia tono={texto.tono}>{texto.etiqueta}</Insignia>
        {datos?.synthetic && <Insignia tono="aviso">Datos sintéticos</Insignia>}
        {puede("viewer") && (
          <button
            type="button"
            onClick={() => leer.mutate(undefined)}
            disabled={leer.isPending}
            className="rounded border border-border px-3 py-1.5 text-sm hover:border-primary disabled:opacity-50"
          >
            {leer.isPending ? "Leyendo…" : datos ? "Leer de nuevo" : "Obtener primer snapshot"}
          </button>
        )}
        {puede("operator") && (
          <button
            type="button"
            onClick={() => evaluar.mutate(undefined)}
            disabled={evaluar.isPending}
            className="rounded border border-border px-3 py-1.5 text-sm hover:border-primary disabled:opacity-50"
          >
            Evaluar políticas ahora
          </button>
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
                {datos.no_debt ? "Sin deuda: no hay riesgo de liquidación" : formatearNumero(datos.health_factor, 4)}
              </Dato>
              <Dato etiqueta="Umbral de alerta">{umbrales.length ? umbrales.map((u) => formatearNumero(u, 4)).join(", ") : "Sin política de health factor"}</Dato>
              <Dato etiqueta="Colateral">{formatearMontoBase(datos.collateral_base)}</Dato>
              <Dato etiqueta="Deuda">{formatearMontoBase(datos.debt_base)}</Dato>
              <Dato etiqueta="Disponible para pedir">{formatearMontoBase(datos.available_borrows_base)}</Dato>
              <Dato etiqueta="Umbral de liquidación">{datos.liquidation_threshold_pct ? `${formatearNumero(datos.liquidation_threshold_pct)} %` : "—"}</Dato>
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
              <Dato etiqueta="Frescura">
                Leída {haceCuanto(datos.read_at)}
                <span className="block text-xs font-normal text-muted-foreground">Se evalúa cada {Math.round(cuenta.interval_seconds / 60)} min</span>
              </Dato>
            </dl>
            <div className="mt-4">
              <Calidad posicion={datos} />
            </div>
            {estado === "sin_posicion" && (
              <p className="mt-4 text-sm text-muted-foreground">Esta dirección no tiene depósitos ni deuda en Aave V3. No es un error: no hay nada que vigilar todavía.</p>
            )}
          </Tarjeta>
          <Activos posicion={datos} />
          {datos.limitations.length > 0 && (
            <Tarjeta titulo="Límites de esta lectura">
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {datos.limitations.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </Tarjeta>
          )}
        </>
      )}

      <Tarjeta titulo="Incidentes activos de esta cuenta">
        {abiertos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Ninguno.</p>
        ) : (
          <ul className="space-y-2">
            {abiertos.map((i) => (
              <li key={i.id}>
                <Link to={`/app/${org}/incidentes/${i.id}`} className="text-sm text-primary underline-offset-4 hover:underline">
                  {SEVERIDADES[i.severity]}: {describirCondicion(i)}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Tarjeta>
    </div>
  );
}
