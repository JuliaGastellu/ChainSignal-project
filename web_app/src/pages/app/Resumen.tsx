// Resumen: primero lo que necesita atención, después si el monitoreo está
// preparado y, al final, contadores como información secundaria. No muestro
// tendencias ni exposición: no tengo historia suficiente para hacerlo sin inventar.

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useResumen } from "@/lib/consultas";
import { acortarDireccion, describirCondicion, haceCuanto, SEVERIDADES, TIPOS_REGLA, TONO_SEVERIDAD } from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import type { ItemAtencion, Resumen as DatosResumen } from "@/lib/tipos";
import { Boton, Cargando, ErrorVista, Insignia, Metrica, Tarjeta, Titulo } from "@/components/Estados";

const CALIDAD: Record<string, string> = {
  FRESH: "dato actualizado",
  STALE: "dato atrasado",
  PARTIAL: "dato parcial",
  UNAVAILABLE: "dato no disponible",
};

function nombreCuenta(item: ItemAtencion): string {
  return item.account_label || (item.account_address ? acortarDireccion(item.account_address) : "Cuenta");
}

function Atencion({ org, item }: { org: string; item: ItemAtencion }) {
  if (item.kind === "incident") {
    return (
      <li className="rounded-lg border border-risk-high/40 bg-card p-4">
        <div className="flex flex-wrap items-center gap-2">
          {item.severity && <Insignia tono={TONO_SEVERIDAD[item.severity]}>{SEVERIDADES[item.severity]}</Insignia>}
          <span className="font-medium">{TIPOS_REGLA[item.rule_type ?? ""] ?? "Alerta"}</span>
          <span className="text-sm text-muted-foreground">· {nombreCuenta(item)}</span>
        </div>
        <p className="mt-2 text-sm">{describirCondicion({ rule_type: item.rule_type!, last_observed: item.observed ?? {} })}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {item.status === "acknowledged" ? "En seguimiento" : "Sin tomar"} · evaluado {haceCuanto(item.last_evaluated_at)} ·{" "}
          {CALIDAD[item.data_quality ?? ""] ?? "calidad desconocida"}
        </p>
        <Link to={`/app/${org}/incidentes/${item.incident_id}`} className="mt-2 inline-block text-sm font-medium text-primary underline-offset-4 hover:underline">
          Revisar el incidente
        </Link>
      </li>
    );
  }
  const noDisponible = item.data_quality === "UNAVAILABLE";
  return (
    <li className="rounded-lg border border-risk-medium/40 bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Insignia tono={noDisponible ? "error" : "aviso"}>
          {noDisponible ? "Dato no disponible" : item.stale ? "Dato atrasado" : CALIDAD[item.data_quality ?? ""] ?? "Dato con problemas"}
        </Insignia>
        <span className="font-medium">{nombreCuenta(item)}</span>
      </div>
      <p className="mt-2 text-sm">
        {noDisponible
          ? "No pude leer la cuenta en la última evaluación (proveedor de datos sin respuesta o con error). Sin datos no puedo decir si la posición está bien."
          : "La lectura está incompleta o atrasada: las alertas de health factor no se evalúan con datos así."}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">Última evaluación {haceCuanto(item.last_evaluated_at)}</p>
      <Link to={`/app/${org}/posiciones/${item.account_id}`} className="mt-2 inline-block text-sm font-medium text-primary underline-offset-4 hover:underline">
        Ver la cuenta y reintentar la lectura
      </Link>
    </li>
  );
}

type Clave = "account_observed" | "valid_read" | "policy_enabled" | "external_channel_verified";

interface Paso {
  clave: Clave;
  texto: string;
  accion: string;
  ruta: string;
  motivo?: string;
}

const MOTIVO_LECTURA: Record<string, string> = {
  unavailable: "La última lectura falló: el proveedor de datos no respondió o no devolvió la posición.",
  partial: "La última lectura llegó incompleta.",
  stale: "La última lectura está atrasada respecto de la red.",
  outdated: "No hay una lectura fresca reciente: el monitoreo no confirmó el dato en los últimos minutos.",
  no_read: "Todavía no hay una lectura válida de ninguna cuenta.",
};
const MOTIVO_CANAL: Record<string, string> = {
  webhooks_disabled: "Esta instancia tiene apagados los envíos externos. Hasta que la persona que la opera los habilite, las alertas solo se ven en la app.",
  channel_disabled: "El webhook está deshabilitado.",
  last_delivery_failed: "La última entrega al webhook falló.",
  not_tested: "El webhook todavía no aceptó una prueba.",
};

// Cada paso describe el estado vigente; el motivo y la acción cambian según por qué no se cumple.
function pasos(d: DatosResumen): Paso[] {
  const { issues } = d.readiness;
  const canal = issues.external_channel_verified;
  const accionCanal =
    canal === "webhooks_disabled"
      ? "Ver por qué no hay envíos externos"
      : canal === "last_delivery_failed" || canal === "channel_disabled"
        ? "Revisar el webhook y enviar una prueba"
        : "Configurar y probar un webhook";
  return [
    { clave: "account_observed", texto: "Una dirección observada", accion: "Agregar una dirección", ruta: "posiciones" },
    {
      clave: "valid_read",
      texto: "Una lectura válida y actual",
      accion: issues.valid_read && issues.valid_read !== "no_read" ? "Ver las cuentas y reintentar la lectura" : "Obtener una lectura",
      ruta: "posiciones",
      motivo: issues.valid_read ? MOTIVO_LECTURA[issues.valid_read] : undefined,
    },
    {
      clave: "policy_enabled",
      texto: "Una política de alerta habilitada",
      accion: issues.policy_enabled === "paused" ? "Reactivar una política" : "Crear una política",
      ruta: "configuracion#politicas",
      motivo: issues.policy_enabled === "paused" ? "Las políticas están pausadas: no abren incidentes." : undefined,
    },
    {
      clave: "external_channel_verified",
      texto: "Un webhook habilitado cuyo destino aceptó la prueba",
      accion: accionCanal,
      ruta: "configuracion#canales",
      motivo: canal ? MOTIVO_CANAL[canal] : undefined,
    },
  ];
}

function SiguientePaso({ org, paso }: { org: string; paso: Paso }) {
  return (
    <p className="mt-3 text-sm">
      Siguiente paso:{" "}
      <Link to={`/app/${org}/${paso.ruta}`} className="font-medium text-primary underline-offset-4 hover:underline">
        {paso.accion}
      </Link>
    </p>
  );
}

function ListaPasos({ lista, r }: { lista: Paso[]; r: DatosResumen["readiness"] }) {
  return (
    <ol className="space-y-2 text-sm">
      {lista.map((p) => (
        <li key={p.clave}>
          <span className="flex flex-wrap items-center gap-2">
            <Insignia tono={r[p.clave] ? "ok" : "neutro"}>{r[p.clave] ? "Listo" : "Pendiente"}</Insignia>
            <span>{p.texto}</span>
          </span>
          {!r[p.clave] && p.motivo && <span className="mt-1 block text-xs text-muted-foreground">{p.motivo}</span>}
        </li>
      ))}
    </ol>
  );
}

function Preparacion({ org, d }: { org: string; d: DatosResumen }) {
  const r = d.readiness;
  if (r.simulated) {
    return (
      <Tarjeta titulo="Demo del monitoreo">
        <p className="text-sm">
          Esto es una demo o una práctica: los datos, el recorrido y los canales son simulados. No cuenta como preparación del monitoreo de una
          organización real.
        </p>
      </Tarjeta>
    );
  }
  if (r.ready) {
    return (
      <details className="rounded-lg border border-border bg-card p-4">
        <summary className="cursor-pointer text-sm">
          <Insignia tono="ok">Monitoreo preparado</Insignia>{" "}
          <span className="text-muted-foreground">Lectura actual válida, política habilitada y webhook que acepta entregas.</span>
        </summary>
        <p className="mt-2 text-xs text-muted-foreground">
          "Preparado" describe el estado actual: el último dato es fresco, hay una política habilitada y el webhook aceptó la prueba y su última
          entrega. No dice nada sobre el riesgo de tus posiciones ni confirma que alguien haya leído un aviso.
        </p>
      </details>
    );
  }
  const lista = pasos(d);
  const fallan = lista.filter((p) => !r[p.clave]);
  if (r.configured) {
    // La configuración se completó alguna vez, pero el circuito no funciona ahora.
    return (
      <Tarjeta titulo="Monitoreo no disponible ahora">
        <p className="text-sm">La configuración está completa, pero hoy no puedo asegurar que una alerta se detecte y se entregue:</p>
        <ul className="mt-2 space-y-2 text-sm">
          {fallan.map((p) => (
            <li key={p.clave}>
              <Insignia tono="aviso">{p.texto}</Insignia>
              {p.motivo && <span className="mt-1 block">{p.motivo}</span>}
            </li>
          ))}
        </ul>
        {fallan[0] && <SiguientePaso org={org} paso={fallan[0]} />}
      </Tarjeta>
    );
  }
  return (
    <Tarjeta titulo={`Monitoreo preparado: ${lista.length - fallan.length} de ${lista.length}`}>
      <ListaPasos lista={lista} r={r} />
      {fallan[0] && <SiguientePaso org={org} paso={fallan[0]} />}
      <p className="mt-3 text-xs text-muted-foreground">No hace falta esperar un incidente: una posición sana también puede quedar preparada.</p>
    </Tarjeta>
  );
}

function Practica({ d }: { d: DatosResumen }) {
  const navigate = useNavigate();
  const cliente = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [creando, setCreando] = useState(false);
  if (d.readiness.simulated) return null;

  const abrir = async () => {
    setCreando(true);
    setError(null);
    try {
      const practica = await api.practica();
      await cliente.invalidateQueries({ queryKey: ["sesion"] });
      navigate(`/app/${practica.organization_id}/resumen`);
    } catch (e) {
      setError(e);
    } finally {
      setCreando(false);
    }
  };

  return (
    <details className="rounded-lg border border-border bg-card p-4">
      <summary className="cursor-pointer text-sm font-medium">Practicar un incidente (opcional)</summary>
      <p className="mt-2 text-sm text-muted-foreground">
        Abro una organización de práctica con datos sintéticos y un incidente de ejemplo. Está separada de esta organización, vence sola y no cuenta en
        las métricas. {d.practice.incident_reviewed && "En esta organización ya hay un incidente revisado."}
      </p>
      <Boton className="mt-3" onClick={abrir} disabled={creando}>
        {creando ? "Preparando…" : "Abrir la práctica"}
      </Boton>
      {error !== null && <div className="mt-3"><ErrorVista error={error} /></div>}
    </details>
  );
}

export default function Resumen() {
  const { org } = useOrgActual();
  const { data, error, isLoading, refetch } = useResumen(org);

  if (isLoading) return <Cargando texto="Cargando el resumen…" />;
  if (error || !data) return <ErrorVista error={error} reintentar={() => refetch()} />;

  const incidentes = data.attention.filter((a) => a.kind === "incident");
  const datos = data.attention.filter((a) => a.kind === "data");

  return (
    <div className="space-y-6">
      <Titulo>Resumen</Titulo>

      <section aria-labelledby="titulo-atencion" className="space-y-3">
        <h2 id="titulo-atencion" className="text-base font-semibold">
          Qué necesita atención
        </h2>
        {data.accounts === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-4 text-sm">
            Todavía no observás ninguna dirección.{" "}
            <Link to={`/app/${org}/posiciones`} className="font-medium text-primary underline-offset-4 hover:underline">
              Agregá la primera
            </Link>
            .
          </p>
        ) : data.attention.length === 0 ? (
          <p className="rounded-lg border border-border bg-card p-4 text-sm">
            Nada requiere atención ahora: no hay alertas abiertas y los datos están al día.
            <span className="mt-1 block text-xs text-muted-foreground">Es lo que dicen tus políticas, no una garantía sobre las posiciones.</span>
          </p>
        ) : (
          <ul className="space-y-2" aria-label="Elementos que necesitan atención">
            {[...incidentes, ...datos].map((item) => (
              <Atencion key={item.incident_id ?? `dato-${item.account_id}`} org={org} item={item} />
            ))}
          </ul>
        )}
      </section>

      <Preparacion org={org} d={data} />
      <Practica d={data} />

      <section aria-label="Contadores" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metrica etiqueta="Incidentes activos" valor={data.active_incidents} />
        <Metrica etiqueta="Cuentas observadas" valor={data.accounts} />
        <Metrica etiqueta="Políticas habilitadas" valor={data.enabled_policies} />
        <Metrica etiqueta="Canales externos verificados" valor={`${data.channels.external_verified} de ${data.channels.external}`}>
          {data.channels.simulated > 0 && `${data.channels.simulated} canal(es) simulados no cuentan`}
        </Metrica>
      </section>
      <p className="text-xs text-muted-foreground">Última evaluación {haceCuanto(data.last_evaluation_at)}.</p>
    </div>
  );
}
