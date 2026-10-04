import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useCuentas, useIncidentes, useMutacionOrg, usePosicion } from "@/lib/consultas";
import {
  acortarDireccion,
  actividadCuenta,
  alertasCuenta,
  DIRECCION_VALIDA,
  describirError,
  formatearMontoBase,
  formatearNumero,
  frescuraDato,
  haceCuanto,
  TEXTO_FRESCURA,
} from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import type { Cuenta, Incidente } from "@/lib/tipos";
import { Boton, Cargando, ErrorVista, Insignia, Senales, Tarjeta, Titulo, Vacio } from "@/components/Estados";

// Por ahora observo una sola red: Ethereum mainnet (chain_id 1).
const REDES = [{ chainId: 1, nombre: "Ethereum (mainnet)" }];

function FilaCuenta({ org, cuenta, incidentes }: { org: string; cuenta: Cuenta; incidentes: Incidente[] }) {
  const { data: posicion, error, isLoading } = usePosicion(org, cuenta.id);
  const alertas = alertasCuenta(incidentes);
  return (
    <li>
      <Link
        to={`/app/${org}/posiciones/${cuenta.id}`}
        className="block rounded-lg border border-border bg-card p-4 hover:border-primary/60"
        aria-label={`${cuenta.label || acortarDireccion(cuenta.address)}: ${alertas.etiqueta}`}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <p className="font-medium">{cuenta.label || acortarDireccion(cuenta.address)}</p>
          {posicion?.health_factor && !posicion.no_debt && (
            <p className="text-sm">
              Health factor <strong className="tabular-nums">{formatearNumero(posicion.health_factor, 4)}</strong>
              <span className="text-muted-foreground"> · deuda {formatearMontoBase(posicion.debt_base)}</span>
            </p>
          )}
        </div>
        <p className="truncate font-mono text-xs text-muted-foreground">{cuenta.address}</p>
        <div className="mt-2">
          {isLoading ? (
            <span className="text-sm text-muted-foreground">Cargando…</span>
          ) : error ? (
            <Insignia tono="error">{describirError(error).titulo}</Insignia>
          ) : (
            <Senales compacto alertas={alertas} dato={TEXTO_FRESCURA[frescuraDato(posicion, cuenta.interval_seconds)]} actividad={actividadCuenta(posicion)} />
          )}
        </div>
        {posicion && <p className="mt-1 text-xs text-muted-foreground">Leída {haceCuanto(posicion.read_at)}</p>}
      </Link>
    </li>
  );
}

function AgregarCuenta({ org, abierto }: { org: string; abierto: boolean }) {
  const navigate = useNavigate();
  const [direccion, setDireccion] = useState("");
  const [etiqueta, setEtiqueta] = useState("");
  const [red, setRed] = useState(1);
  const [aviso, setAviso] = useState<string | null>(null);
  const crear = useMutacionOrg(org, () => api.crearCuenta(org, direccion.trim(), red, etiqueta.trim() || null));

  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (!DIRECCION_VALIDA.test(direccion.trim())) {
      setAviso("La dirección debe empezar con 0x y tener 40 caracteres hexadecimales.");
      return;
    }
    setAviso(null);
    crear.mutate(undefined, { onSuccess: (cuenta) => navigate(`/app/${org}/posiciones/${cuenta.id}`) });
  };

  return (
    <details open={abierto} className="rounded-lg border border-border bg-card p-4">
      <summary className="cursor-pointer text-base font-semibold">Observar una dirección</summary>
      <form onSubmit={enviar} className="mt-3 grid gap-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end" noValidate>
        <label className="text-sm">
          Dirección
          <input
            value={direccion}
            onChange={(e) => setDireccion(e.target.value)}
            placeholder="0x…"
            required
            spellCheck={false}
            aria-invalid={aviso ? true : undefined}
            aria-describedby={aviso ? "aviso-direccion" : undefined}
            className="mt-1 w-full rounded border border-border bg-background px-3 py-2 font-mono text-sm"
          />
        </label>
        <label className="text-sm">
          Red
          <select value={red} onChange={(e) => setRed(Number(e.target.value))} className="mt-1 w-full rounded border border-border bg-background px-3 py-2">
            {REDES.map((r) => (
              <option key={r.chainId} value={r.chainId}>
                {r.nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Nombre (opcional)
          <input value={etiqueta} onChange={(e) => setEtiqueta(e.target.value)} maxLength={200} className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
        </label>
        <Boton type="submit" variante="primario" disabled={crear.isPending}>
          {crear.isPending ? "Agregando…" : "Agregar"}
        </Boton>
      </form>
      {aviso && (
        <p id="aviso-direccion" role="alert" className="mt-2 text-sm text-risk-text-high">
          {aviso}
        </p>
      )}
      {crear.error && <div className="mt-3"><ErrorVista error={crear.error} /></div>}
      <p className="mt-3 text-xs text-muted-foreground">Solo leo la posición: no firmo, no muevo fondos y no necesito acceso a la wallet.</p>
    </details>
  );
}

export default function Posiciones() {
  const { org, puede } = useOrgActual();
  const { data: cuentas, error, isLoading, refetch } = useCuentas(org);
  const incidentes = useIncidentes(org, "active");
  const porCuenta = (id: string) => (incidentes.data ?? []).filter((i) => i.account_id === id);
  // Primero las cuentas con alertas abiertas: son las que necesitan atención.
  const ordenadas = [...(cuentas ?? [])].sort((a, b) => Number(porCuenta(b.id).length > 0) - Number(porCuenta(a.id).length > 0));

  return (
    <div className="space-y-6">
      <Titulo subtitulo="Aave V3 en Ethereum mainnet. Las alertas salen de tus políticas; el estado del dato, de la última lectura.">Posiciones</Titulo>
      {isLoading ? (
        <Cargando />
      ) : error ? (
        <ErrorVista error={error} reintentar={() => refetch()} />
      ) : !cuentas?.length ? (
        <Vacio titulo="Todavía no observás ninguna dirección">
          {puede("operator") ? "Agregá una dirección de Ethereum para leer su posición en Aave V3." : "Pedile a una persona operadora que agregue una."}
        </Vacio>
      ) : (
        <ul className="space-y-2" aria-label="Cuentas observadas">
          {ordenadas.map((c) => (
            <FilaCuenta key={c.id} org={org} cuenta={c} incidentes={porCuenta(c.id)} />
          ))}
        </ul>
      )}
      {puede("operator") && <AgregarCuenta org={org} abierto={!cuentas?.length} />}
    </div>
  );
}
