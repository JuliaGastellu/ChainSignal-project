import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="text-center">
        <h1 className="text-3xl font-semibold">Página no encontrada</h1>
        <p className="mt-3 text-foreground/80">La dirección no existe o cambió.</p>
        <Link to="/" className="mt-4 inline-block text-primary underline-offset-4 hover:underline">
          Volver al inicio
        </Link>
      </div>
    </main>
  );
}
