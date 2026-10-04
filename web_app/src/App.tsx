import React from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { RequireSession } from "@/components/RequireSession";
import { AppLayout } from "@/components/AppLayout";
import { crearQueryClient } from "@/lib/consultas";
import { useSesion } from "@/lib/sesion";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Registro from "./pages/Registro";
import Invitacion from "./pages/Invitacion";
import NotFound from "./pages/NotFound";
import Resumen from "./pages/app/Resumen";
import Posiciones from "./pages/app/Posiciones";
import PosicionDetalle from "./pages/app/PosicionDetalle";
import Incidentes from "./pages/app/Incidentes";
import IncidenteDetalle from "./pages/app/IncidenteDetalle";
import Configuracion from "./pages/app/Configuracion";

const queryClient = crearQueryClient();

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hayError: boolean }> {
  state = { hayError: false };

  static getDerivedStateFromError() {
    return { hayError: true };
  }

  componentDidCatch(error: unknown) {
    console.error("[UI] Error de render:", error);
  }

  render() {
    if (this.state.hayError) {
      return (
        <main className="flex min-h-screen items-center justify-center p-6">
          <div role="alert" className="w-full max-w-lg rounded-xl border border-border bg-card p-6">
            <p className="font-semibold">La interfaz encontró un error</p>
            <p className="mt-2 text-sm text-foreground/80">Recargá la página. Si vuelve a pasar, el detalle queda en la consola del navegador.</p>
            <button type="button" onClick={() => window.location.reload()} className="mt-4 rounded border border-border px-3 py-2 text-sm hover:border-primary">
              Recargar
            </button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}

// /app sin organización: voy a la primera de la persona.
function InicioApp() {
  const sesion = useSesion();
  const primera = sesion?.memberships[0];
  if (!primera) {
    return (
      <main className="mx-auto max-w-lg p-6 text-sm">
        <h1 className="text-lg font-semibold">Todavía no formás parte de una organización</h1>
        <p className="mt-2 text-foreground/80">Pedí una invitación a tu equipo o creá una organización nueva.</p>
      </main>
    );
  }
  return <Navigate to={`/app/${primera.organization_id}/resumen`} replace />;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ErrorBoundary>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/registro" element={<Registro />} />
          <Route path="/invitacion" element={<Invitacion />} />
          <Route path="/app" element={<RequireSession><InicioApp /></RequireSession>} />
          <Route path="/app/:org" element={<RequireSession><AppLayout /></RequireSession>}>
            <Route index element={<Navigate to="resumen" replace />} />
            <Route path="resumen" element={<Resumen />} />
            <Route path="posiciones" element={<Posiciones />} />
            <Route path="posiciones/:cuenta" element={<PosicionDetalle />} />
            <Route path="incidentes" element={<Incidentes />} />
            <Route path="incidentes/:incidente" element={<IncidenteDetalle />} />
            <Route path="configuracion" element={<Configuracion />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  </QueryClientProvider>
);

export default App;
