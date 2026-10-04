// Políticas de alerta: crear, editar (cada cambio de regla es una versión
// nueva), pausar y reactivar. Antes de guardar muestro cuándo abre, cuándo se
// despeja y cuándo escala, con los valores que normaliza la API. Editar no
// toca la evidencia ni los incidentes: siguen apuntando a la versión que los abrió.

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useInvalidarOrg, usePoliticas, useVersiones } from "@/lib/consultas";
import { describirVistaPrevia, formatearFecha, formatearNumero, SEVERIDADES, TIPOS_REGLA } from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import type { Politica, Severidad, VistaPreviaPolitica } from "@/lib/tipos";
import { Boton, Cargando, ErrorVista, Insignia, Tarjeta, Vacio } from "@/components/Estados";

type Tipo = "health_factor_below" | "debt_change" | "stale_data";

interface Borrador {
  tipo: Tipo;
  nombre: string;
  valor: string; // umbral, % o minutos según el tipo
  despeje: string; // solo health factor: valor de despeje (vacío = por defecto)
  consecutivas: string; // solo health factor
  severidad: Severidad;
  escalaMin: string;
}

function borradorDe(p?: Politica): Borrador {
  const r = (p?.rule ?? {}) as Record<string, unknown>;
  const tipo = (r.type as Tipo) ?? "health_factor_below";
  const valor = tipo === "health_factor_below" ? r.threshold : tipo === "debt_change" ? r.change_pct : r.max_age_seconds ? Number(r.max_age_seconds) / 60 : undefined;
  return {
    tipo,
    nombre: p?.name ?? TIPOS_REGLA[tipo],
    valor: valor !== undefined ? String(valor) : tipo === "health_factor_below" ? "1.5" : tipo === "debt_change" ? "20" : "30",
    despeje: r.clear_above ? String(r.clear_above) : "",
    consecutivas: r.clear_after ? String(r.clear_after) : "2",
    severidad: (r.severity as Severidad) ?? (tipo === "health_factor_below" ? "high" : "medium"),
    escalaMin: r.escalate_after_seconds ? String(Number(r.escalate_after_seconds) / 60) : "60",
  };
}

function reglaDe(b: Borrador): Record<string, unknown> {
  const regla: Record<string, unknown> = { type: b.tipo, severity: b.severidad, escalate_after_seconds: Math.round(Number(b.escalaMin) * 60) };
  if (b.tipo === "health_factor_below") {
    regla.threshold = b.valor;
    if (b.despeje.trim()) regla.clear_above = b.despeje.trim();
    regla.clear_after = Number(b.consecutivas);
  } else if (b.tipo === "debt_change") {
    regla.change_pct = b.valor;
  } else {
    regla.max_age_seconds = Math.round(Number(b.valor) * 60);
  }
  return regla;
}

function VistaPrevia({ vista }: { vista: VistaPreviaPolitica }) {
  const texto = describirVistaPrevia(vista);
  return (
    <div className="rounded border border-primary/40 bg-primary/5 p-3 text-sm" aria-live="polite">
      <p className="font-medium">Así va a funcionar</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5">
        <li>{texto.abre}</li>
        <li>{texto.despeja}</li>
        <li>{texto.escala}</li>
      </ul>
    </div>
  );
}

function Editor({ politica, onListo }: { politica?: Politica; onListo: () => void }) {
  const { org } = useOrgActual();
  const invalidar = useInvalidarOrg(org);
  const [b, setB] = useState<Borrador>(borradorDe(politica));
  const [vista, setVista] = useState<{ clave: string; datos: VistaPreviaPolitica } | null>(null);
  const clave = JSON.stringify({ ...reglaDe(b), nombre: b.nombre });
  const previa = useMutation({
    mutationFn: () => api.vistaPreviaPolitica(org, reglaDe(b)),
    onSuccess: (datos) => setVista({ clave, datos }),
  });
  const guardar = useMutation({
    mutationFn: () =>
      politica ? api.actualizarPolitica(org, politica.id, { name: b.nombre.trim(), rule: reglaDe(b) }) : api.crearPolitica(org, b.nombre.trim(), reglaDe(b)),
    onSuccess: () => {
      invalidar();
      onListo();
    },
  });
  // Solo guardo después de ver la vista previa de exactamente estos valores.
  const vigente = vista?.clave === clave;
  const cambiar = (cambios: Partial<Borrador>) => setB((actual) => ({ ...actual, ...cambios }));
  const etiquetaValor = b.tipo === "health_factor_below" ? "Umbral de alerta (health factor)" : b.tipo === "debt_change" ? "Cambio de deuda (%)" : "Antigüedad máxima (min)";

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    if (vigente) guardar.mutate();
    else previa.mutate();
  };

  return (
    <form onSubmit={enviar} className="space-y-3 border-t border-border pt-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm">
          Tipo
          <select
            value={b.tipo}
            disabled={Boolean(politica)}
            onChange={(e) => setB(borradorDe({ rule: { type: e.target.value } } as unknown as Politica))}
            className="mt-1 w-full rounded border border-border bg-background px-3 py-2 disabled:opacity-60"
          >
            {Object.entries(TIPOS_REGLA).map(([k, t]) => (
              <option key={k} value={k}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Nombre
          <input value={b.nombre} onChange={(e) => cambiar({ nombre: e.target.value })} required maxLength={200} className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
        </label>
        <label className="text-sm">
          {etiquetaValor}
          <input value={b.valor} onChange={(e) => cambiar({ valor: e.target.value })} required inputMode="decimal" className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
        </label>
        <label className="text-sm">
          Severidad
          <select value={b.severidad} onChange={(e) => cambiar({ severidad: e.target.value as Severidad })} className="mt-1 w-full rounded border border-border bg-background px-3 py-2">
            {Object.entries(SEVERIDADES).map(([k, t]) => (
              <option key={k} value={k}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">Opciones de despeje y escalamiento</summary>
        <div className="mt-2 grid gap-3 sm:grid-cols-3">
          {b.tipo === "health_factor_below" && (
            <>
              <label className="text-sm">
                Se despeja desde (vacío: umbral + 5 %)
                <input value={b.despeje} onChange={(e) => cambiar({ despeje: e.target.value })} inputMode="decimal" className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
              </label>
              <label className="text-sm">
                Evaluaciones seguidas para despejar
                <input value={b.consecutivas} onChange={(e) => cambiar({ consecutivas: e.target.value })} inputMode="numeric" className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
              </label>
            </>
          )}
          <label className="text-sm">
            Escalar si nadie lo toma (min)
            <input value={b.escalaMin} onChange={(e) => cambiar({ escalaMin: e.target.value })} inputMode="numeric" className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
          </label>
        </div>
      </details>
      {vigente && vista && <VistaPrevia vista={vista.datos} />}
      {(previa.error || guardar.error) && <ErrorVista error={previa.error ?? guardar.error} />}
      <div className="flex flex-wrap gap-2">
        <Boton type="submit" variante="primario" disabled={previa.isPending || guardar.isPending}>
          {vigente ? (politica ? "Guardar como versión nueva" : "Crear política") : previa.isPending ? "Calculando…" : "Ver cuándo abre y cuándo despeja"}
        </Boton>
        <Boton onClick={onListo}>Cancelar</Boton>
      </div>
      {politica && <p className="text-xs text-muted-foreground">Guardar crea la versión {politica.version + 1}. Los incidentes y la evidencia existentes no cambian.</p>}
    </form>
  );
}

function describirRegla(p: Politica): string {
  const r = p.rule;
  if (r.type === "health_factor_below") return `Health factor menor a ${formatearNumero(r.threshold as string, 4)}; se despeja desde ${formatearNumero(r.clear_above as string, 4)} en ${r.clear_after} evaluaciones seguidas.`;
  if (r.type === "debt_change") return `La deuda cambia ${formatearNumero(r.change_pct as string)} % o más.`;
  return `Más de ${Math.round(Number(r.max_age_seconds) / 60)} min sin una lectura actualizada.`;
}

function Versiones({ politica }: { politica: Politica }) {
  const { org } = useOrgActual();
  const [abierto, setAbierto] = useState(false);
  const { data } = useVersiones(org, politica.id, abierto);
  return (
    <details onToggle={(e) => setAbierto((e.target as HTMLDetailsElement).open)} className="mt-1 text-xs text-muted-foreground">
      <summary className="cursor-pointer">Historial de versiones</summary>
      <ul className="mt-1 space-y-0.5">
        {(data ?? []).map((v) => (
          <li key={v.version}>
            v{v.version} · {formatearFecha(v.created_at)} · <span className="font-mono">{JSON.stringify(v.rule)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function FilaPolitica({ politica }: { politica: Politica }) {
  const { org, puede } = useOrgActual();
  const invalidar = useInvalidarOrg(org);
  const [editando, setEditando] = useState(false);
  const [confirmarPausa, setConfirmarPausa] = useState(false);
  const pausa = useMutation({
    mutationFn: (habilitar: boolean) => api.actualizarPolitica(org, politica.id, { enabled: habilitar }),
    onSuccess: () => {
      invalidar();
      setConfirmarPausa(false);
    },
  });
  return (
    <li id={`politica-${politica.id}`} className="scroll-mt-4 py-3 target:bg-primary/5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{politica.name}</p>
          <p className="text-sm text-muted-foreground">{describirRegla(politica)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Insignia tono="neutro">{SEVERIDADES[politica.rule.severity]}</Insignia>
          <Insignia tono="neutro">v{politica.version}</Insignia>
          <Insignia tono={politica.enabled ? "ok" : "aviso"}>{politica.enabled ? "Habilitada" : "Pausada"}</Insignia>
        </div>
      </div>
      <Versiones politica={politica} />
      {puede("operator") && !editando && (
        <div className="mt-2 flex flex-wrap gap-2">
          <Boton onClick={() => setEditando(true)}>Editar</Boton>
          {politica.enabled ? (
            confirmarPausa ? (
              <>
                <Boton variante="peligro" onClick={() => pausa.mutate(false)} disabled={pausa.isPending}>
                  Confirmar pausa
                </Boton>
                <Boton onClick={() => setConfirmarPausa(false)}>Volver</Boton>
              </>
            ) : (
              <Boton onClick={() => setConfirmarPausa(true)}>Pausar</Boton>
            )
          ) : (
            <Boton onClick={() => pausa.mutate(true)} disabled={pausa.isPending}>
              Reactivar
            </Boton>
          )}
        </div>
      )}
      {confirmarPausa && (
        <p className="mt-2 text-sm">Mientras esté pausada no abre incidentes nuevos. Los incidentes abiertos siguen abiertos hasta que alguien los resuelva.</p>
      )}
      {pausa.error && <div className="mt-2"><ErrorVista error={pausa.error} /></div>}
      {editando && <div className="mt-3"><Editor politica={politica} onListo={() => setEditando(false)} /></div>}
    </li>
  );
}

export function Politicas() {
  const { org, puede } = useOrgActual();
  const { data, error, isLoading, refetch } = usePoliticas(org);
  const [creando, setCreando] = useState(false);
  return (
    <Tarjeta id="politicas" titulo="Políticas de alerta" accion={puede("operator") && !creando && <Boton variante="primario" onClick={() => setCreando(true)}>Nueva política</Boton>}>
      {isLoading ? (
        <Cargando />
      ) : error ? (
        <ErrorVista error={error} reintentar={() => refetch()} />
      ) : !data?.length ? (
        <Vacio titulo="Sin políticas">Una política define cuándo abrir un incidente; se aplica a todas las cuentas de la organización.</Vacio>
      ) : (
        <ul className="divide-y divide-border">
          {data.map((p) => (
            <FilaPolitica key={p.id} politica={p} />
          ))}
        </ul>
      )}
      {creando && <Editor onListo={() => setCreando(false)} />}
      {!puede("operator") && <p className="mt-3 text-xs text-muted-foreground">Tu rol es de lectura: una persona operadora puede crear y editar políticas.</p>}
    </Tarjeta>
  );
}
