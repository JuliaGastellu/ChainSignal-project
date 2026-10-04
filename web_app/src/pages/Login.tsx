import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { describirError } from "@/lib/formato";

export default function Login() {
  const navigate = useNavigate();
  const cliente = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (evento: FormEvent) => {
    evento.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      const sesion = await api.login(email, password);
      cliente.setQueryData(["sesion"], sesion);
      navigate("/app", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? "Email o contraseña incorrectos." : describirError(e).detalle);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <form onSubmit={enviar} className="w-full max-w-sm space-y-4 rounded-xl border border-border bg-card p-6" aria-labelledby="titulo-login">
        <h1 id="titulo-login" className="text-lg font-semibold">
          Iniciar sesión en ChainSignal
        </h1>
        <label className="block text-sm">
          Email
          <input
            type="email"
            autoComplete="username"
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
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded border border-border bg-background px-3 py-2"
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-risk-high">
            {error}
          </p>
        )}
        <button type="submit" disabled={enviando} className="w-full rounded bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
          {enviando ? "Ingresando…" : "Ingresar"}
        </button>
        <p className="text-sm text-muted-foreground">
          ¿No tenés cuenta?{" "}
          <Link to="/registro" className="text-primary underline-offset-4 hover:underline">
            Creá una organización
          </Link>{" "}
          o{" "}
          <Link to="/" className="text-primary underline-offset-4 hover:underline">
            probá la demo
          </Link>
          .
        </p>
      </form>
    </main>
  );
}
