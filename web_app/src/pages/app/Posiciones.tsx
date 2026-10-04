import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useCuentas, useMutacionOrg, usePosicion } from "@/lib/consultas";
import {
  acortarDireccion,
  DIRECCION_VALIDA,
  describirError,
  estadoCuenta,
  formatearMontoBase,
  formatearNumero,
  haceCuanto,
  TEXTO_ESTADO_CUENTA,
} from "@/lib/formato";
import { useOrgActual } from "@/lib/sesion";
import type { Cuenta } from "@/lib/tipos";
import { Cargando, ErrorVista, Insignia, Tarjeta, Vacio } from "@/components/Estados";

// Por ahora observo una sola red: Ethereum mainnet (chain_id 1).
const REDES = [{ chainId: 1, nombre: "Ethereum (mainnet)" }];

function FilaCuenta({ org, cuenta }: { org: string; cuenta: Cuenta }) {
  const { data: posicion, error, isLoading } = usePosicion(org, cuenta.id);
  const estado = estadoCuenta(posicion, cuenta.interval_seconds);
  const texto = TEXTO_ESTADO_CUENTA[estado];
  return (
    <li>
      <Link
        to={`/app/${org}/posiciones/${cuenta.id}`}
        className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4 hover:border-primary/60 sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="min-w-0">
          <p className="font-medium">{cuenta.label || acortarDireccion(cuenta.address)}</p>
          <p className="truncate font-mono text-xs text-muted-foreground">{cuenta.address}</p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          {isLoading ? (
            <span className="text-muted-foreground">Cargando…</span>
          ) : error ? (
            <Insignia tono="error">{describirError(error).titulo}</Insignia>
          ) : (
            <>
              <Insignia tono={texto.tono}>{texto.etiqueta}</Insignia>
              {estado === "activa" && posicion && (
                <span>
                  HF <strong>{formatearNumero(posicion.health_factor, 4)}</strong> · Deuda {formatearMontoBase(posicion.debt_base)}
                </span>
              )}
              {posicion && <span className="text-xs text-muted-foreground">Leída {haceCuanto(posicion.read_at)}</span>}
            </>
          )}
        </div>
      </Link>
    </li>
  );
}

function AgregarCuenta({ org }: { org: string }) {
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
    <Tarjeta titulo="Observar una dirección">
      <form onSubmit={enviar} className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end" noValidate>
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
        <button type="submit" disabled={crear.isPending} className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
          {crear.isPending ? "Agregando…" : "Agregar"}
        </button>
      </form>
      {aviso && (
        <p id="aviso-direccion" role="alert" className="mt-2 text-sm text-risk-high">
          {aviso}
        </p>
      )}
      {crear.error && <div className="mt-3"><ErrorVista error={crear.error} /></div>}
      <p className="mt-3 text-xs text-muted-foreground">
        Solo leo la posición: ChainSignal no firma ni mueve fondos y no necesita acceso a la wallet.
      </p>
    </Tarjeta>
  );
}

export default function Posiciones() {
  const { org, puede } = useOrgActual();
  const { data: cuentas, error, isLoading, refetch } = useCuentas(org);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Posiciones</h1>
      {puede("operator") && <AgregarCuenta org={org} />}
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
          {cuentas.map((c) => (
            <FilaCuenta key={c.id} org={org} cuenta={c} />
          ))}
        </ul>
      )}
    </div>
  );
}
