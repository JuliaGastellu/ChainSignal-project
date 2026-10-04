// Canales de notificación. Distingo tres cosas que no son lo mismo:
// - canal simulado (sandbox): registra la notificación sin enviarla fuera del sistema;
// - entrega aceptada: un destino externo (webhook) respondió 2xx;
// - recepción humana: no la puedo afirmar sin una confirmación aparte.
// Si la instancia no permite webhooks, lo explico y doy el siguiente paso real;
// nunca reemplazo un webhook por el sandbox en silencio.

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useCanales, useInvalidarOrg } from "@/lib/consultas";
import { haceCuanto, RESULTADO_ENTREGA } from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import { traducirErrorEntrega } from "@/lib/traducciones";
import type { Canal, PruebaCanal } from "@/lib/tipos";
import { Boton, Cargando, DetalleTecnico, ErrorVista, Insignia, Tarjeta, Vacio } from "@/components/Estados";

function textoPrueba(p: Pick<PruebaCanal, "kind" | "outcome" | "error">): string {
  if (p.outcome === "simulated") return "Registré una simulación: el mensaje no salió del sistema y no llegó a nadie.";
  if (p.outcome === "accepted_by_destination") return "El destino externo aceptó la prueba (HTTP 2xx). No puedo confirmar que una persona la haya visto.";
  if (p.outcome === "failed") return `La prueba falló. ${traducirErrorEntrega(p.error)}`;
  return "La prueba quedó pendiente.";
}

function FilaCanal({ canal }: { canal: Canal }) {
  const { org, puede } = useOrgActual();
  const invalidar = useInvalidarOrg(org);
  const prueba = useMutation({ mutationFn: () => api.probarCanal(org, canal.id), onSuccess: () => invalidar() });
  const ultima = prueba.data ?? (canal.last_test ? { kind: canal.kind, ...canal.last_test } : null);
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{canal.name}</p>
          <p className="text-sm text-muted-foreground">
            {canal.kind === "sandbox" ? "Simulado: registra la notificación sin enviarla fuera del sistema." : `Webhook externo a ${canal.config.host ?? "—"}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {ultima ? (
            <Insignia tono={RESULTADO_ENTREGA[ultima.outcome].tono}>{RESULTADO_ENTREGA[ultima.outcome].etiqueta}</Insignia>
          ) : (
            <Insignia tono="aviso">Sin probar</Insignia>
          )}
          {puede("operator") && (
            <Boton onClick={() => prueba.mutate()} disabled={prueba.isPending}>
              {prueba.isPending ? "Probando…" : "Enviar prueba"}
              <span className="sr-only"> a {canal.name}</span>
            </Boton>
          )}
        </div>
      </div>
      {ultima && (
        <p role="status" className="mt-1 text-sm">
          {textoPrueba(ultima)} {canal.last_test && !prueba.data && <span className="text-muted-foreground">({haceCuanto(canal.last_test.at)})</span>}
        </p>
      )}
      {ultima?.error && <DetalleTecnico>{ultima.error}</DetalleTecnico>}
      {prueba.error && <div className="mt-2"><ErrorVista error={prueba.error} /></div>}
    </li>
  );
}

function NuevoWebhook({ habilitados }: { habilitados: boolean }) {
  const { org } = useOrgActual();
  const invalidar = useInvalidarOrg(org);
  const [nombre, setNombre] = useState("Alertas del equipo");
  const [url, setUrl] = useState("");
  const crear = useMutation({ mutationFn: () => api.crearCanal(org, "webhook", nombre.trim(), { url: url.trim() }), onSuccess: () => invalidar() });

  if (!habilitados) {
    return (
      <div className="rounded border border-risk-medium/40 bg-risk-medium/10 p-3 text-sm">
        <p className="font-medium">Los envíos externos están deshabilitados en esta instancia</p>
        <p className="mt-1">
          Por ahora no puedo enviar alertas fuera de ChainSignal: los incidentes solo se ven en la app. El siguiente paso es pedirle a la persona que opera
          esta instancia que habilite los webhooks (NOTIFICATIONS_WEBHOOKS_ENABLED). No reemplazo el envío por una simulación.
        </p>
      </div>
    );
  }
  if (crear.data?.signing_secret) {
    return (
      <div className="rounded border border-primary/40 bg-primary/5 p-3 text-sm" role="status">
        <p className="font-medium">Webhook creado. Guardá este secreto ahora: no lo vuelvo a mostrar.</p>
        <p className="mt-1">Con él, el destino puede comprobar la firma del encabezado X-ChainSignal-Signature.</p>
        <code className="mt-2 block break-all rounded bg-background p-2 font-mono text-xs">{crear.data.signing_secret}</code>
        <Boton className="mt-2" onClick={() => crear.reset()}>Listo, lo guardé</Boton>
      </div>
    );
  }
  const enviar = (e: FormEvent) => {
    e.preventDefault();
    crear.mutate();
  };
  return (
    <form onSubmit={enviar} className="grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
      <label className="text-sm">
        Nombre
        <input value={nombre} onChange={(e) => setNombre(e.target.value)} required maxLength={200} className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
      </label>
      <label className="text-sm">
        URL del webhook (https)
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          type="url"
          inputMode="url"
          placeholder="https://hooks.tu-equipo.com/…"
          spellCheck={false}
          className="mt-1 w-full rounded border border-border bg-background px-3 py-2 font-mono text-sm"
        />
      </label>
      <Boton type="submit" variante="primario" disabled={crear.isPending}>
        {crear.isPending ? "Validando…" : "Crear webhook"}
      </Boton>
      <p className="text-xs text-muted-foreground sm:col-span-3">
        Solo acepto https al puerto 443 y destinos con dirección pública. La URL completa no se vuelve a mostrar ni se escribe en los registros.
      </p>
      {crear.error && <div className="sm:col-span-3"><ErrorVista error={crear.error} /></div>}
    </form>
  );
}

function NuevoSandbox() {
  const { org } = useOrgActual();
  const invalidar = useInvalidarOrg(org);
  const crear = useMutation({ mutationFn: () => api.crearCanal(org, "sandbox", "Canal simulado"), onSuccess: () => invalidar() });
  return (
    <div className="text-sm">
      <Boton onClick={() => crear.mutate()} disabled={crear.isPending}>Crear un canal simulado</Boton>
      <span className="ml-2 text-xs text-muted-foreground">Sirve para ver el circuito; no cuenta como canal verificado.</span>
      {crear.error && <div className="mt-2"><ErrorVista error={crear.error} /></div>}
    </div>
  );
}

export function Canales() {
  const { org, puede, esDemo } = useOrgActual();
  const { data, error, isLoading, refetch } = useCanales(org);
  return (
    <Tarjeta id="canales" titulo="Canales de notificación">
      {isLoading ? (
        <Cargando />
      ) : error || !data ? (
        <ErrorVista error={error} reintentar={() => refetch()} />
      ) : (
        <>
          {data.channels.length === 0 ? (
            <Vacio titulo="Sin canales">Sin un canal externo, los incidentes se registran pero no avisan fuera de la app.</Vacio>
          ) : (
            <ul className="divide-y divide-border">
              {data.channels.map((c) => (
                <FilaCanal key={c.id} canal={c} />
              ))}
            </ul>
          )}
          {esDemo ? (
            <p className="mt-4 text-sm text-muted-foreground">En la demo los canales son simulados y no se pueden crear otros.</p>
          ) : puede("owner") ? (
            <div className="mt-4 space-y-4 border-t border-border pt-4">
              <NuevoWebhook habilitados={data.webhooks_enabled} />
              <NuevoSandbox />
            </div>
          ) : (
            <p className="mt-4 text-xs text-muted-foreground">Solo la persona dueña de la organización crea canales.</p>
          )}
        </>
      )}
    </Tarjeta>
  );
}
