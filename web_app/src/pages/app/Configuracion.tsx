import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useCanales, useMiembros, useMutacionOrg, usePoliticas } from "@/lib/consultas";
import { formatearNumero, haceCuanto, SEVERIDADES, TIPOS_REGLA } from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import type { Politica, Severidad } from "@/lib/tipos";
import { Cargando, ErrorVista, Insignia, Tarjeta, Vacio } from "@/components/Estados";
import { PlanOrganizacion } from "@/components/PlanOrganizacion";

const ROLES = { owner: "Dueña o dueño", operator: "Operación", viewer: "Lectura" } as const;

function describirRegla(p: Politica): string {
  const r = p.rule;
  if (r.type === "health_factor_below") return `Health factor menor a ${formatearNumero(r.threshold as string, 4)}; se despeja sobre ${formatearNumero(r.clear_above as string, 4)}.`;
  if (r.type === "debt_change") return `La deuda cambia ${formatearNumero(r.change_pct as string)} % o más.`;
  return `Más de ${Math.round(Number(r.max_age_seconds) / 60)} min sin un dato fresco.`;
}

function NuevaPolitica({ org }: { org: string }) {
  const [tipo, setTipo] = useState<"health_factor_below" | "debt_change" | "stale_data">("health_factor_below");
  const [nombre, setNombre] = useState("Health factor bajo");
  const [valor, setValor] = useState("1.5");
  const [severidad, setSeveridad] = useState<Severidad>("high");
  const crear = useMutacionOrg(org, () => {
    const regla: Record<string, unknown> = { type: tipo, severity: severidad };
    if (tipo === "health_factor_below") regla.threshold = valor;
    else if (tipo === "debt_change") regla.change_pct = valor;
    else regla.max_age_seconds = Math.round(Number(valor) * 60);
    return api.crearPolitica(org, nombre.trim(), regla);
  });

  const cambiarTipo = (nuevo: typeof tipo) => {
    setTipo(nuevo);
    setNombre(TIPOS_REGLA[nuevo]);
    setValor(nuevo === "health_factor_below" ? "1.5" : nuevo === "debt_change" ? "20" : "30");
    setSeveridad(nuevo === "health_factor_below" ? "high" : "medium");
  };
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    crear.mutate(undefined);
  };
  const etiquetaValor = tipo === "health_factor_below" ? "Umbral de health factor" : tipo === "debt_change" ? "Cambio de deuda (%)" : "Antigüedad máxima (min)";

  return (
    <form onSubmit={enviar} className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-5 lg:items-end">
      <label className="text-sm">
        Tipo
        <select value={tipo} onChange={(e) => cambiarTipo(e.target.value as typeof tipo)} className="mt-1 w-full rounded border border-border bg-background px-3 py-2">
          {Object.entries(TIPOS_REGLA).map(([clave, texto]) => (
            <option key={clave} value={clave}>
              {texto}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        Nombre
        <input value={nombre} onChange={(e) => setNombre(e.target.value)} required maxLength={200} className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
      </label>
      <label className="text-sm">
        {etiquetaValor}
        <input
          value={valor}
          onChange={(e) => setValor(e.target.value)}
          required
          inputMode="decimal"
          className="mt-1 w-full rounded border border-border bg-background px-3 py-2"
        />
      </label>
      <label className="text-sm">
        Severidad
        <select value={severidad} onChange={(e) => setSeveridad(e.target.value as Severidad)} className="mt-1 w-full rounded border border-border bg-background px-3 py-2">
          {Object.entries(SEVERIDADES).map(([clave, texto]) => (
            <option key={clave} value={clave}>
              {texto}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={crear.isPending} className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
        {crear.isPending ? "Creando…" : "Crear política"}
      </button>
      {crear.error && (
        <div className="sm:col-span-2 lg:col-span-5">
          <ErrorVista error={crear.error} />
        </div>
      )}
    </form>
  );
}

function Politicas() {
  const { org, puede } = useOrgActual();
  const { data, error, isLoading, refetch } = usePoliticas(org);
  return (
    <Tarjeta titulo="Políticas de alerta">
      {isLoading ? (
        <Cargando />
      ) : error ? (
        <ErrorVista error={error} reintentar={() => refetch()} />
      ) : !data?.length ? (
        <Vacio titulo="Sin políticas">Una política define cuándo abrir un incidente; se aplica a todas las cuentas de la organización.</Vacio>
      ) : (
        <ul className="divide-y divide-border">
          {data.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <div>
                <p className="font-medium">{p.name}</p>
                <p className="text-muted-foreground">{describirRegla(p)}</p>
              </div>
              <div className="flex gap-2">
                <Insignia tono="neutro">{SEVERIDADES[p.rule.severity]}</Insignia>
                <Insignia tono="neutro">v{p.version}</Insignia>
                {!p.enabled && <Insignia tono="aviso">Pausada</Insignia>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {puede("operator") && <NuevaPolitica org={org} />}
    </Tarjeta>
  );
}

function Canales() {
  const { org, puede, esDemo } = useOrgActual();
  const { data, error, isLoading, refetch } = useCanales(org);
  const [nombre, setNombre] = useState("Canal de prueba");
  const crear = useMutacionOrg(org, () => api.crearCanal(org, nombre.trim()));
  const probar = useMutacionOrg(org, (id: string) => api.probarCanal(org, id));

  return (
    <Tarjeta titulo="Canales de notificación">
      {isLoading ? (
        <Cargando />
      ) : error ? (
        <ErrorVista error={error} reintentar={() => refetch()} />
      ) : !data?.length ? (
        <Vacio titulo="Sin canales">Sin un canal, los incidentes se registran pero no avisan a nadie.</Vacio>
      ) : (
        <ul className="divide-y divide-border">
          {data.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <div>
                <p className="font-medium">{c.name}</p>
                <p className="text-muted-foreground">
                  {c.kind === "sandbox" ? "Sandbox: registra el mensaje sin enviarlo fuera del sistema" : `Webhook a ${String(c.config.host ?? "—")}`}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {c.verified_at ? <Insignia tono="ok">Probado {haceCuanto(c.verified_at)}</Insignia> : <Insignia tono="aviso">Sin probar</Insignia>}
                {puede("operator") && (
                  <button
                    type="button"
                    onClick={() => probar.mutate(c.id)}
                    disabled={probar.isPending}
                    className="rounded border border-border px-3 py-1 hover:border-primary disabled:opacity-50"
                  >
                    Enviar prueba
                    <span className="sr-only"> a {c.name}</span>
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {probar.data && (
        <p role="status" className="mt-2 text-sm">
          {probar.data.status === "sent" ? "La prueba llegó al canal." : probar.data.status === "failed" ? "La prueba falló; revisá la configuración." : "La prueba quedó en cola."}
        </p>
      )}
      {probar.error && <div className="mt-2"><ErrorVista error={probar.error} /></div>}
      {puede("owner") && !esDemo && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            crear.mutate(undefined);
          }}
          className="mt-4 flex flex-wrap items-end gap-3 border-t border-border pt-4"
        >
          <label className="text-sm">
            Nombre del canal sandbox
            <input value={nombre} onChange={(e) => setNombre(e.target.value)} required maxLength={200} className="mt-1 block rounded border border-border bg-background px-3 py-2" />
          </label>
          <button type="submit" disabled={crear.isPending} className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
            Crear canal
          </button>
          {crear.error && <ErrorVista error={crear.error} />}
        </form>
      )}
    </Tarjeta>
  );
}

function Miembros() {
  const { org } = useOrgActual();
  const { data, error, isLoading, refetch } = useMiembros(org);
  return (
    <Tarjeta titulo="Personas">
      {isLoading ? (
        <Cargando />
      ) : error ? (
        <ErrorVista error={error} reintentar={() => refetch()} />
      ) : (
        <ul className="divide-y divide-border text-sm">
          {data?.map((m) => (
            <li key={m.membership_id} className="flex flex-wrap justify-between gap-2 py-2">
              <span className="break-all">{m.email}</span>
              <span className="text-muted-foreground">{ROLES[m.role]}</span>
            </li>
          ))}
        </ul>
      )}
    </Tarjeta>
  );
}

export default function Configuracion() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Configuración</h1>
      <PlanOrganizacion />
      <Politicas />
      <Canales />
      <Miembros />
    </div>
  );
}
