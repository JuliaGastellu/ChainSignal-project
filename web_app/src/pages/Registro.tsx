import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { describirError } from "@/lib/formato";

export default function Registro() {
  const navigate = useNavigate();
  const cliente = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizacion, setOrganizacion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (evento: FormEvent) => {
    evento.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      const alta = await api.alta(email, password, organizacion.trim());
      cliente.setQueryData(["sesion"], alta);
      navigate(`/app/${alta.organization_id}/resumen`, { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setError("El alta autoservicio no está habilitada. Pedí una invitación a tu organización.");
      else if (e instanceof ApiError && e.status === 409) setError("Ya existe una cuenta con ese email. Iniciá sesión.");
      else setError(describirError(e).detalle);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <form onSubmit={enviar} className="w-full max-w-sm space-y-4 rounded-xl border border-border bg-card p-6" aria-labelledby="titulo-registro">
        <h1 id="titulo-registro" className="text-lg font-semibold">
          Crear una organización
        </h1>
        <label className="block text-sm">
          Nombre de la organización
          <input
            required
            maxLength={200}
            value={organizacion}
            onChange={(e) => setOrganizacion(e.target.value)}
            className="mt-1 w-full rounded border border-border bg-background px-3 py-2"
          />
        </label>
        <label className="block text-sm">
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded border border-border bg-background px-3 py-2"
          />
        </label>
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
          <span id="ayuda-contrasena" className="mt-1 block text-xs text-muted-foreground">
            Al menos 12 caracteres.
          </span>
        </label>
        {error && (
          <p role="alert" className="text-sm text-risk-text-high">
            {error}
          </p>
        )}
        <button type="submit" disabled={enviando} className="w-full rounded bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
          {enviando ? "Creando…" : "Crear organización"}
        </button>
        <p className="text-sm text-muted-foreground">
          ¿Ya tenés cuenta?{" "}
          <Link to="/login" className="text-primary underline-offset-4 hover:underline">
            Iniciá sesión
          </Link>
          .
        </p>
      </form>
    </main>
  );
}
