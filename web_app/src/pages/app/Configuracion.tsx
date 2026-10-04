import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { PlanOrganizacion } from "@/components/PlanOrganizacion";
import { Canales } from "@/components/config/Canales";
import { Personas } from "@/components/config/Personas";
import { Politicas } from "@/components/config/Politicas";
import { Titulo } from "@/components/Estados";

export default function Configuracion() {
  const { hash } = useLocation();
  // Los enlaces del Resumen y de las explicaciones llevan a una sección (#canales, #politica-…).
  useEffect(() => {
    if (!hash) return;
    const destino = document.getElementById(decodeURIComponent(hash.slice(1)));
    destino?.scrollIntoView({ block: "start" });
  }, [hash]);

  return (
    <div className="space-y-6">
      <Titulo>Configuración</Titulo>
      <Politicas />
      <Canales />
      <Personas />
      <PlanOrganizacion />
    </div>
  );
}
