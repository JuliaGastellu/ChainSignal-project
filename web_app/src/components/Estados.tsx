// Piezas comunes de las vistas: estados (cargando, vacío, error), insignias,
// señales de cuenta, botones y detalle técnico desplegable.
//
// Jerarquía visual que uso en toda la app:
// - título de página: text-2xl semibold (Titulo);
// - título de sección: text-base semibold dentro de Tarjeta;
// - métricas: Metrica, números grandes y tabulares, siempre con su unidad;
// - acciones: Boton primario (una por bloque), secundario o de peligro;
// - evidencia y procedencia: DetalleTecnico, plegado por defecto.

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { describirError, type Senal, type Tono } from "@/lib/formato";
import { cn } from "@/lib/utils";

export function Titulo({ children, subtitulo }: { children: ReactNode; subtitulo?: ReactNode }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">{children}</h1>
      {subtitulo && <p className="mt-1 text-sm text-muted-foreground">{subtitulo}</p>}
    </div>
  );
}

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <p role="status" aria-live="polite" className="py-8 text-center text-sm text-muted-foreground">
      {texto}
    </p>
  );
}

export function Vacio({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-border p-6 text-center">
      <p className="font-medium">{titulo}</p>
      {children && <div className="mt-2 text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function DetalleTecnico({ titulo = "Detalle técnico", children }: { titulo?: string; children: ReactNode }) {
  return (
    <details className="group mt-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer select-none rounded underline-offset-4 hover:underline">{titulo}</summary>
      <div className="mt-1 break-words font-mono">{children}</div>
    </details>
  );
}

export function ErrorVista({ error, reintentar }: { error: unknown; reintentar?: () => void }) {
  const { titulo, detalle, accion, tecnico } = describirError(error);
  return (
    <div role="alert" className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm">
      <p className="font-semibold">{titulo}</p>
      <p className="mt-1 text-foreground/85">{detalle}</p>
      <div className="mt-3 flex flex-wrap gap-3">
        {accion && (
          <Link to={accion.href} className="font-medium text-primary underline-offset-4 hover:underline">
            {accion.texto}
          </Link>
        )}
        {reintentar && (
          <button type="button" onClick={reintentar} className="font-medium text-primary underline-offset-4 hover:underline">
            Reintentar
          </button>
        )}
      </div>
      {tecnico && <DetalleTecnico>{tecnico}</DetalleTecnico>}
    </div>
  );
}

const TONOS: Record<Tono, string> = {
  ok: "border-risk-low/40 bg-risk-low/10 text-risk-text-low",
  neutro: "border-border bg-muted text-foreground/85",
  aviso: "border-risk-medium/40 bg-risk-medium/10 text-risk-text-medium",
  error: "border-risk-high/40 bg-risk-high/10 text-risk-text-high",
};

// No dependo solo del color: cada tono lleva un símbolo (pseudo-elemento CSS,
// fuera del texto accesible) además del texto.
const SIMBOLO: Record<Tono, string> = { ok: "✓", neutro: "•", aviso: "!", error: "▲" };

export function Insignia({ tono, children, className }: { tono: Tono; children: ReactNode; className?: string }) {
  return (
    <span
      data-simbolo={SIMBOLO[tono]}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium before:content-[attr(data-simbolo)]",
        TONOS[tono],
        className,
      )}
    >
      {children}
    </span>
  );
}

// Las tres señales de una cuenta, cada una con su nombre para no confundirlas.
export function Senales({ actividad, alertas, dato, compacto = false }: { actividad: Senal; alertas: Senal; dato: Senal; compacto?: boolean }) {
  const filas: [string, Senal][] = [["Alertas", alertas], ["Dato", dato], ["Actividad", actividad]];
  return (
    <dl className={cn("flex flex-wrap gap-x-4 gap-y-1", compacto ? "text-xs" : "text-sm")}>
      {filas.map(([nombre, senal]) => (
        <div key={nombre} className="flex items-center gap-1.5">
          <dt className="text-muted-foreground">{nombre}:</dt>
          <dd>
            <Insignia tono={senal.tono}>{senal.etiqueta}</Insignia>
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function Tarjeta({ titulo, children, className, accion, id }: { titulo?: string; children: ReactNode; className?: string; accion?: ReactNode; id?: string }) {
  return (
    <section id={id} className={cn("rounded-lg border border-border bg-card p-4", className)} aria-label={titulo}>
      {(titulo || accion) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {titulo && <h2 className="text-base font-semibold">{titulo}</h2>}
          {accion}
        </div>
      )}
      {children}
    </section>
  );
}

export function Dato({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{etiqueta}</dt>
      <dd className="mt-0.5 font-medium break-words">{children}</dd>
    </div>
  );
}

export function Metrica({ etiqueta, valor, unidad, children }: { etiqueta: string; valor: ReactNode; unidad?: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <p className="text-xs text-muted-foreground">{etiqueta}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">
        {valor}
        {unidad && <span className="ml-1 text-sm font-normal text-muted-foreground">{unidad}</span>}
      </p>
      {children && <div className="mt-1 text-xs text-muted-foreground">{children}</div>}
    </div>
  );
}

type Variante = "primario" | "secundario" | "peligro";

const VARIANTES: Record<Variante, string> = {
  primario: "bg-primary text-primary-foreground hover:bg-primary/90",
  secundario: "border border-border bg-transparent hover:border-primary",
  peligro: "border border-risk-high/60 text-risk-text-high hover:bg-risk-high/10",
};

export function Boton({ variante = "secundario", className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante }) {
  return (
    <button
      type="button"
      {...props}
      className={cn("inline-flex min-h-9 items-center justify-center rounded px-3 py-1.5 text-sm font-medium disabled:opacity-50", VARIANTES[variante], className)}
    />
  );
}
