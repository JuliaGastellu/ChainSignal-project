// Personas de la organización: roles, bajas e invitaciones. Solo la persona
// dueña cambia roles, quita miembros e invita; la API además impide dejar la
// organización sin una persona dueña. No envío correos: el enlace de
// invitación se muestra una vez para compartirlo por un canal propio.

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useInvalidarOrg, useInvitaciones, useMiembros } from "@/lib/consultas";
import { formatearFecha } from "@/lib/formato";
import { useOrgActual, useSesion } from "@/lib/sesion";
import type { Miembro, Rol } from "@/lib/tipos";
import { Boton, Cargando, ErrorVista, Insignia, Tarjeta } from "@/components/Estados";

const ROLES: Record<Rol, string> = { owner: "Dueña o dueño", operator: "Operación", viewer: "Lectura" };
const DESCRIPCION_ROLES: Record<Rol, string> = {
  owner: "todo, incluidos canales, personas y plan",
  operator: "cuentas, políticas e incidentes",
  viewer: "solo ver",
};

function FilaMiembro({ miembro, esPropio }: { miembro: Miembro; esPropio: boolean }) {
  const { org, puede } = useOrgActual();
  const invalidar = useInvalidarOrg(org);
  const [confirmar, setConfirmar] = useState(false);
  const rol = useMutation({ mutationFn: (nuevo: Rol) => api.cambiarRol(org, miembro.membership_id, nuevo), onSuccess: () => invalidar() });
  const quitar = useMutation({ mutationFn: () => api.quitarMiembro(org, miembro.membership_id), onSuccess: () => invalidar() });
  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="min-w-0 break-all">
          {miembro.email}
          {esPropio && <span className="text-muted-foreground"> (vos)</span>}
        </span>
        {puede("owner") ? (
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm">
              <span className="sr-only">Rol de {miembro.email}</span>
              <select
                value={miembro.role}
                onChange={(e) => rol.mutate(e.target.value as Rol)}
                disabled={rol.isPending}
                className="rounded border border-border bg-background px-2 py-1 text-sm"
              >
                {Object.entries(ROLES).map(([k, t]) => (
                  <option key={k} value={k}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            {confirmar ? (
              <>
                <Boton variante="peligro" onClick={() => quitar.mutate()} disabled={quitar.isPending}>Confirmar</Boton>
                <Boton onClick={() => setConfirmar(false)}>Volver</Boton>
              </>
            ) : (
              <Boton onClick={() => setConfirmar(true)}>Quitar</Boton>
            )}
          </div>
        ) : (
          <Insignia tono="neutro">{ROLES[miembro.role]}</Insignia>
        )}
      </div>
      {(rol.error || quitar.error) && <div className="mt-2"><ErrorVista error={rol.error ?? quitar.error} /></div>}
    </li>
  );
}

function Invitaciones() {
  const { org } = useOrgActual();
  const invalidar = useInvalidarOrg(org);
  const { data } = useInvitaciones(org, true);
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState<Rol>("viewer");
  const invitar = useMutation({ mutationFn: () => api.invitar(org, email.trim(), rol), onSuccess: () => { invalidar(); setEmail(""); } });
  const revocar = useMutation({ mutationFn: (id: string) => api.revocarInvitacion(org, id), onSuccess: () => invalidar() });
  const ahora = Date.now() / 1000;
  const pendientes = (data ?? []).filter((i) => !i.accepted_at && !i.revoked_at && i.expires_at > ahora);
  const enlace = invitar.data?.token ? `${window.location.origin}/invitacion#token=${encodeURIComponent(invitar.data.token)}` : null;

  const enviar = (e: FormEvent) => {
    e.preventDefault();
    invitar.mutate();
  };
  return (
    <div className="mt-4 space-y-3 border-t border-border pt-4">
      <form onSubmit={enviar} className="grid gap-3 sm:grid-cols-[2fr_1fr_auto] sm:items-end">
        <label className="text-sm">
          Email de la persona
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
        </label>
        <div className="text-sm">
          <label htmlFor="rol-invitacion">Rol</label>
          <select id="rol-invitacion" value={rol} onChange={(e) => setRol(e.target.value as Rol)} className="mt-1 w-full rounded border border-border bg-background px-3 py-2">
            {Object.entries(ROLES).map(([k, t]) => (
              <option key={k} value={k}>
                {t}: {DESCRIPCION_ROLES[k as Rol]}
              </option>
            ))}
          </select>
        </div>
        <Boton type="submit" variante="primario" disabled={invitar.isPending}>
          Invitar
        </Boton>
      </form>
      {invitar.error && <ErrorVista error={invitar.error} />}
      {enlace && (
        <div role="status" className="rounded border border-primary/40 bg-primary/5 p-3 text-sm">
          <p className="font-medium">Invitación creada para {invitar.data?.email}. Este enlace se muestra una sola vez:</p>
          <code className="mt-2 block break-all rounded bg-background p-2 font-mono text-xs">{enlace}</code>
          <p className="mt-2 text-xs text-muted-foreground">
            Compartilo por un canal tuyo; no envío correos. Vence el {formatearFecha(invitar.data?.expires_at)} y sirve una sola vez, para ese email.
          </p>
        </div>
      )}
      {pendientes.length > 0 && (
        <div>
          <p className="text-sm font-medium">Invitaciones pendientes</p>
          <ul className="mt-1 divide-y divide-border text-sm">
            {pendientes.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="break-all">
                  {i.email} · {ROLES[i.role]} · vence {formatearFecha(i.expires_at)}
                </span>
                <Boton onClick={() => revocar.mutate(i.id)} disabled={revocar.isPending}>Revocar</Boton>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function Personas() {
  const { org, puede, esDemo } = useOrgActual();
  const sesion = useSesion();
  const { data, error, isLoading, refetch } = useMiembros(org);
  return (
    <Tarjeta id="personas" titulo="Personas">
      {isLoading ? (
        <Cargando />
      ) : error ? (
        <ErrorVista error={error} reintentar={() => refetch()} />
      ) : (
        <ul className="divide-y divide-border text-sm">
          {data?.map((m) => (
            <FilaMiembro key={m.membership_id} miembro={m} esPropio={m.user_id === sesion?.user.id} />
          ))}
        </ul>
      )}
      {puede("owner") && !esDemo && <Invitaciones />}
      <p className="mt-3 text-xs text-muted-foreground">
        Roles: dueña o dueño ({DESCRIPCION_ROLES.owner}), operación ({DESCRIPCION_ROLES.operator}) y lectura ({DESCRIPCION_ROLES.viewer}). La
        organización siempre conserva al menos una persona dueña.
      </p>
    </Tarjeta>
  );
}
