// Estados comunes de las vistas: cargando, vacío, error y las insignias de tono.

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { describirError, type Tono } from "@/lib/formato";
import { cn } from "@/lib/utils";

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

export function ErrorVista({ error, reintentar }: { error: unknown; reintentar?: () => void }) {
  const { titulo, detalle, accion } = describirError(error);
  return (
    <div role="alert" className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm">
      <p className="font-semibold">{titulo}</p>
      <p className="mt-1 text-foreground/80">{detalle}</p>
      <div className="mt-3 flex gap-3">
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
    </div>
  );
}

const TONOS: Record<Tono, string> = {
  ok: "border-risk-low/40 bg-risk-low/10 text-risk-low",
  neutro: "border-border bg-muted text-foreground/80",
  aviso: "border-risk-medium/40 bg-risk-medium/10 text-risk-medium",
  error: "border-risk-high/40 bg-risk-high/10 text-risk-high",
};

export function Insignia({ tono, children, className }: { tono: Tono; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium", TONOS[tono], className)}>
      {children}
    </span>
  );
}

export function Tarjeta({ titulo, children, className, accion }: { titulo?: string; children: ReactNode; className?: string; accion?: ReactNode }) {
  return (
    <section className={cn("rounded-lg border border-border bg-card p-4", className)}>
      {(titulo || accion) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {titulo && <h2 className="text-sm font-semibold">{titulo}</h2>}
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
