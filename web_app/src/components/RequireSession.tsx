import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router-dom";
import { api, ApiError } from "@/lib/api";
import { SesionContext } from "@/lib/sesion";
import { ErrorVista } from "@/components/Estados";

// Verifico la sesión en la API antes de mostrar cualquier página privada.
// La autorización real ocurre en el backend; esto solo evita pantallas vacías.
export function RequireSession({ children }: { children: ReactNode }) {
  const ubicacion = useLocation();
  const { data: sesion, error, refetch } = useQuery({ queryKey: ["sesion"], queryFn: api.sesion, staleTime: 60_000 });

  if (error instanceof ApiError && error.status === 401) {
    return <Navigate to="/login" replace state={{ desde: ubicacion.pathname }} />;
  }
  if (error) {
    return (
      <div className="mx-auto flex min-h-screen max-w-md items-center p-6">
        <div className="w-full">
          <p className="mb-3 text-sm">No pudimos verificar tu sesión. Intentá de nuevo en unos segundos.</p>
          <ErrorVista error={error} reintentar={() => refetch()} />
        </div>
      </div>
    );
  }
  if (!sesion) {
    return (
      <p role="status" className="flex min-h-screen items-center justify-center p-6 text-sm text-muted-foreground">
        Verificando sesión…
      </p>
    );
  }
  return <SesionContext.Provider value={sesion}>{children}</SesionContext.Provider>;
}
