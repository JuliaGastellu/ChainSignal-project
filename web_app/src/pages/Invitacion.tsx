// Aceptar una invitación. El token llega en el fragmento (#token=…): no viaja
// al servidor en la solicitud de la página ni en el encabezado Referer.
// - Con sesión iniciada: acepto con esa cuenta (el email tiene que coincidir).
// - Sin sesión y sin cuenta: creo la cuenta con la contraseña que elija la persona.
// - Sin sesión y con cuenta existente: pido iniciar sesión y volver al enlace.

import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { Boton, ErrorVista } from "@/components/Estados";

function tokenDelFragmento(hash: string): string | null {
  const valor = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return valor && valor.length > 10 ? valor : null;
}

export default function Invitacion() {
  const { hash } = useLocation();
  const navigate = useNavigate();
  const cliente = useQueryClient();
  const token = tokenDelFragmento(hash);
  const sesion = useQuery({ queryKey: ["sesion"], queryFn: api.sesion, retry: false });
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [necesitaLogin, setNecesitaLogin] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const conSesion = Boolean(sesion.data);

  const aceptar = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!token) return;
    setEnviando(true);
    setError(null);
    try {
      const resultado = await api.aceptarInvitacion(token, conSesion ? undefined : password);
      await cliente.invalidateQueries({ queryKey: ["sesion"] });
      navigate(`/app/${resultado.organization_id}/resumen`, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setNecesitaLogin(true);
      else setError(err);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm space-y-4 rounded-xl border border-border bg-card p-6">
        <h1 className="text-lg font-semibold">Aceptar invitación</h1>
        {!token ? (
          <p className="text-sm">El enlace no tiene una invitación válida. Pedile a la persona que te invitó un enlace nuevo.</p>
        ) : necesitaLogin ? (
          <p className="text-sm">
            Ya existe una cuenta con ese email. <Link to={`/login?siguiente=${encodeURIComponent(`/invitacion${hash}`)}`} className="font-medium text-primary underline-offset-4 hover:underline">Iniciá sesión</Link> y
            volvé a este enlace para aceptar.
          </p>
        ) : sesion.isLoading ? (
          <p role="status" className="text-sm text-muted-foreground">Verificando sesión…</p>
        ) : conSesion ? (
          <>
            <p className="text-sm">
              Vas a aceptar la invitación con la cuenta <strong className="break-all">{sesion.data?.user.email}</strong>. Tiene que ser el email invitado.
            </p>
            <Boton variante="primario" onClick={() => aceptar()} disabled={enviando} className="w-full">
              {enviando ? "Aceptando…" : "Aceptar"}
            </Boton>
          </>
        ) : (
          <form onSubmit={aceptar} className="space-y-3">
            <p className="text-sm">Elegí una contraseña para tu cuenta nueva. El email es el de la invitación.</p>
            <label className="block text-sm">
              Contraseña
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-describedby="ayuda-contrasena"
                className="mt-1 w-full rounded border border-border bg-background px-3 py-2"
              />
              <span id="ayuda-contrasena" className="mt-1 block text-xs text-muted-foreground">Al menos 12 caracteres.</span>
            </label>
            <Boton type="submit" variante="primario" disabled={enviando} className="w-full">
              {enviando ? "Creando…" : "Crear cuenta y aceptar"}
            </Boton>
          </form>
        )}
        {error !== null && <ErrorVista error={error} />}
      </div>
    </main>
  );
}
