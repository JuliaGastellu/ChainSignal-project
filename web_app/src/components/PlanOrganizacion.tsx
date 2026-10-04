// Plan de la organización: estado, límites, uso, precio de referencia y
// cancelación. El precio es una hipótesis de piloto y el cobro es asistido: lo
// digo explícitamente. La interfaz solo muestra los límites; los aplica la API.

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { claves, useSuscripcion } from "@/lib/consultas";
import { describirPlan, formatearFecha } from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import { Cargando, Dato, ErrorVista, Insignia, Tarjeta } from "@/components/Estados";

export function PlanOrganizacion() {
  const { org, puede } = useOrgActual();
  const { data, error, isLoading, refetch } = useSuscripcion(org);
  const cliente = useQueryClient();
  const [confirmando, setConfirmando] = useState(false);
  const cambiar = useMutation({
    mutationFn: (accion: "cancelar" | "reanudar") => (accion === "cancelar" ? api.cancelarSuscripcion(org) : api.reanudarSuscripcion(org)),
    onSuccess: (nueva) => {
      cliente.setQueryData(claves.suscripcion(org), nueva);
      setConfirmando(false);
    },
  });

  if (isLoading) return <Tarjeta titulo="Plan"><Cargando /></Tarjeta>;
  if (error || !data) return <Tarjeta titulo="Plan"><ErrorVista error={error} reintentar={() => refetch()} /></Tarjeta>;
  if (data.is_demo) {
    return (
      <Tarjeta titulo="Plan">
        <p className="text-sm text-muted-foreground">La demo no tiene plan ni cobro: usa datos sintéticos y vence sola.</p>
      </Tarjeta>
    );
  }

  const estado = describirPlan(data);
  const vigente = ["trialing", "active", "past_due"].includes(data.status);
  return (
    <Tarjeta titulo="Plan">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{data.plan.name}</span>
        <Insignia tono={estado.tono}>{estado.etiqueta}</Insignia>
      </div>
      <p className="mt-1 text-sm">{estado.detalle}</p>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Dato etiqueta="Cuentas observadas">
          {data.usage.accounts} de {data.limits.max_accounts}
        </Dato>
        <Dato etiqueta="Frecuencia máxima">Cada {Math.round(data.limits.min_interval_seconds / 60)} min</Dato>
        <Dato etiqueta="Alcance">Aave V3 en Ethereum mainnet, solo lectura</Dato>
        <Dato etiqueta="Precio de referencia">
          USD {data.plan.reference_price_usd_per_month} por mes
          {data.plan.price_is_hypothesis && <span className="block text-xs font-normal text-muted-foreground">Precio de piloto en validación, no tarifa definitiva</span>}
        </Dato>
      </dl>
      <p className="mt-4 text-sm text-muted-foreground">
        Cobro asistido: emitimos una factura y activamos el período cuando el pago está confirmado. No pedimos tarjeta ni cobramos de forma automática.
        {data.plan.guided_onboarding && " Incluye acompañamiento en la configuración."}
      </p>
      {data.confirmed_payments.length > 0 && (
        <div className="mt-4">
          <p className="text-sm font-medium">Pagos confirmados</p>
          <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
            {data.confirmed_payments.map((p) => (
              <li key={`${p.period_start}-${p.period_end}`}>
                USD {p.amount_usd}: {formatearFecha(p.period_start)} a {formatearFecha(p.period_end)} ({p.source === "manual" ? "confirmación manual" : "procesador de pagos"})
              </li>
            ))}
          </ul>
        </div>
      )}
      {puede("owner") && vigente && (
        <div className="mt-4 border-t border-border pt-4">
          {data.cancel_at_period_end ? (
            <button type="button" onClick={() => cambiar.mutate("reanudar")} disabled={cambiar.isPending}
              className="rounded border border-border px-3 py-1.5 text-sm hover:border-primary disabled:opacity-50">
              Mantener el plan (deshacer la cancelación)
            </button>
          ) : confirmando ? (
            <div className="space-y-2">
              <p className="text-sm">
                Vas a cancelar la renovación. El servicio sigue hasta el fin de la prueba o del período pago; después se pausa el monitoreo y el historial
                queda disponible.
              </p>
              <div className="flex gap-2">
                <button type="button" onClick={() => cambiar.mutate("cancelar")} disabled={cambiar.isPending}
                  className="rounded border border-risk-high/60 px-3 py-1.5 text-sm text-risk-high disabled:opacity-50">
                  Confirmar cancelación
                </button>
                <button type="button" onClick={() => setConfirmando(false)} className="rounded border border-border px-3 py-1.5 text-sm">
                  Volver
                </button>
              </div>
            </div>
          ) : (
            <button type="button" onClick={() => setConfirmando(true)} className="rounded border border-border px-3 py-1.5 text-sm hover:border-primary">
              Cancelar el plan
            </button>
          )}
          {cambiar.error && <div className="mt-2"><ErrorVista error={cambiar.error} /></div>}
        </div>
      )}
    </Tarjeta>
  );
}

// Aviso visible en toda la app cuando el plan necesita atención.
export function AvisoPlan({ org }: { org: string }) {
  const { data } = useSuscripcion(org);
  if (!data || data.is_demo) return null;
  const quedan = data.trial_ends_at ? (data.trial_ends_at - data.server_time) / 86400 : null;
  const avisar = !data.service_active || data.status === "past_due" || data.cancel_at_period_end || (data.status === "trialing" && quedan !== null && quedan <= 3);
  if (!avisar) return null;
  const estado = describirPlan(data);
  return (
    <div role="status" className={`mb-4 rounded-lg border p-3 text-sm ${data.service_active ? "border-risk-medium/50 bg-risk-medium/10" : "border-risk-high/50 bg-risk-high/10"}`}>
      <strong>{estado.etiqueta}.</strong> {estado.detalle} Podés ver el plan en Configuración.
    </div>
  );
}
