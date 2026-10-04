import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { describirError } from "@/lib/formato";
import { ErrorVista, Insignia } from "@/components/Estados";

// La promesa es acotada a propósito: leo posiciones y aviso con evidencia. No
// digo que evite pérdidas ni que tenga certificaciones.

const PUNTOS = [
  { titulo: "Lectura con evidencia", texto: "Cada snapshot de Aave V3 queda atado a un bloque y su hash, con la calidad del dato a la vista." },
  { titulo: "Incidentes, no ruido", texto: "Las políticas abren un incidente una sola vez, lo escalan si nadie lo toma y lo cierran con histéresis." },
  { titulo: "Seguimiento del equipo", texto: "Quién tomó cada incidente, cuándo y con qué nota se resolvió, por organización y con roles." },
];

const PREGUNTAS = [
  {
    p: "¿ChainSignal puede mover mis fondos?",
    r: "No. Solo leo datos públicos de la red con la dirección que me indicás. No pido claves, firmas ni conexión de wallet, y no envío transacciones.",
  },
  {
    p: "¿Evita liquidaciones?",
    r: "No lo prometo. Te aviso cuando una condición que definiste se cumple, con el bloque y los valores que la respaldan. Qué hacer lo decide tu equipo.",
  },
  {
    p: "¿Qué pasa si el proveedor de datos falla?",
    r: "La cuenta queda marcada como dato no disponible o atrasado, con su motivo. Nunca la muestro como sana por falta de datos, y puedo abrir un incidente de dato atrasado.",
  },
  {
    p: "¿Qué redes y protocolos cubre?",
    r: "Por ahora, Aave V3 en Ethereum mainnet. Otros protocolos y redes no están soportados.",
  },
  {
    p: "¿Cómo se paga el piloto?",
    r: "Con cobro asistido: emito una factura y activo el período cuando el pago está confirmado. No pido tarjeta. Podés cancelar desde Configuración y el servicio sigue hasta el fin del período.",
  },
  {
    p: "¿Tienen auditoría o certificación?",
    r: "No. El código y las pruebas están documentados, pero no tengo una auditoría externa ni una certificación de seguridad.",
  },
];

function EjemploIncidente() {
  return (
    <figure className="rounded-lg border border-border bg-card p-4" aria-labelledby="ejemplo-incidente">
      <figcaption id="ejemplo-incidente" className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold">Ejemplo de incidente</span>
        <Insignia tono="aviso">Datos sintéticos</Insignia>
      </figcaption>
      <div className="flex flex-wrap gap-2">
        <Insignia tono="error">Alta</Insignia>
        <Insignia tono="neutro">Abierto</Insignia>
        <span className="text-sm font-medium">Health factor bajo</span>
      </div>
      <p className="mt-2 text-sm">Health factor 1,375 por debajo del umbral 1,5.</p>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-xs text-muted-foreground">Bloque de apertura</dt>
          <dd>20.000.000</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Calidad del dato</dt>
          <dd>Datos actualizados</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Se cierra</dt>
          <dd>Sobre 1,6 en 2 evaluaciones seguidas</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Responsable</dt>
          <dd>Sin asignar</dd>
        </div>
      </dl>
    </figure>
  );
}

function Contacto() {
  const [email, setEmail] = useState("");
  const [organizacion, setOrganizacion] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [consentimiento, setConsentimiento] = useState(false);
  const [estado, setEstado] = useState<"inicial" | "enviando" | "enviado">("inicial");
  const [error, setError] = useState<string | null>(null);

  const enviar = async (evento: FormEvent) => {
    evento.preventDefault();
    if (!consentimiento) {
      setError("Necesito tu consentimiento para guardar tus datos de contacto.");
      return;
    }
    setEstado("enviando");
    setError(null);
    try {
      await api.contacto(email, organizacion, mensaje, consentimiento);
      setEstado("enviado");
    } catch (e) {
      setEstado("inicial");
      setError(describirError(e).detalle);
    }
  };

  if (estado === "enviado") {
    return (
      <p role="status" className="rounded-lg border border-risk-low/50 bg-risk-low/10 p-4 text-sm">
        Recibí tu mensaje. Lo leo y te respondo personalmente; no vas a recibir correos automáticos.
      </p>
    );
  }
  return (
    <form onSubmit={enviar} className="grid gap-3 rounded-lg border border-border bg-card p-4 sm:grid-cols-2" aria-labelledby="titulo-contacto">
      <label className="text-sm">
        Email
        <input type="email" required maxLength={320} autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
      </label>
      <label className="text-sm">
        Organización (opcional)
        <input maxLength={200} value={organizacion} onChange={(e) => setOrganizacion(e.target.value)}
          className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
      </label>
      <label className="text-sm sm:col-span-2">
        Mensaje
        <textarea required maxLength={2000} rows={3} value={mensaje} onChange={(e) => setMensaje(e.target.value)}
          placeholder="Qué posiciones querés vigilar y cómo lo hacen hoy"
          className="mt-1 w-full rounded border border-border bg-background px-3 py-2" />
      </label>
      <label className="flex items-start gap-2 text-sm sm:col-span-2">
        <input type="checkbox" checked={consentimiento} onChange={(e) => setConsentimiento(e.target.checked)} className="mt-1" />
        <span>Acepto que guarde mi email y mi mensaje para responderte. No los uso para otra cosa ni los comparto.</span>
      </label>
      {error && (
        <p role="alert" className="text-sm text-risk-high sm:col-span-2">
          {error}
        </p>
      )}
      <div className="sm:col-span-2">
        <button type="submit" disabled={estado === "enviando"} className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
          {estado === "enviando" ? "Enviando…" : "Enviar"}
        </button>
      </div>
    </form>
  );
}

export default function Landing() {
  const navigate = useNavigate();
  const cliente = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [creando, setCreando] = useState(false);

  const probarDemo = async () => {
    setCreando(true);
    setError(null);
    try {
      const demo = await api.demo();
      await cliente.invalidateQueries({ queryKey: ["sesion"] });
      navigate(`/app/${demo.organization_id}/resumen`);
    } catch (e) {
      setError(e);
    } finally {
      setCreando(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
        <span className="font-semibold">ChainSignal</span>
        <nav aria-label="Cuenta" className="flex gap-4 text-sm">
          <Link to="/login" className="text-primary underline-offset-4 hover:underline">
            Iniciar sesión
          </Link>
          <Link to="/registro" className="text-primary underline-offset-4 hover:underline">
            Crear cuenta
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl space-y-16 px-4 pb-16 pt-10">
        <section className="grid gap-8 lg:grid-cols-[3fr_2fr] lg:items-start">
          <div>
            <h1 className="max-w-3xl text-3xl font-semibold leading-tight sm:text-4xl">
              Monitoreo de posiciones en Aave V3 con evidencia, alertas y seguimiento para tu equipo.
            </h1>
            <p className="mt-4 max-w-2xl text-foreground/80">
              ChainSignal observa direcciones de Ethereum, lee su posición a un bloque concreto y abre incidentes cuando el health factor cae, la deuda
              cambia o el dato se atrasa. Solo lectura: nunca firma ni mueve fondos.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button type="button" onClick={probarDemo} disabled={creando}
                className="rounded bg-primary px-5 py-2.5 font-medium text-primary-foreground disabled:opacity-50">
                {creando ? "Preparando la demo…" : "Probar la demo"}
              </button>
              <Link to="/registro" className="rounded border border-border px-5 py-2.5 font-medium hover:border-primary">
                Empezar la prueba de 14 días
              </Link>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">La demo usa datos sintéticos, está aislada de las cuentas reales y vence sola.</p>
            {error !== null && (
              <div className="mt-4 max-w-lg">
                <ErrorVista error={error} />
              </div>
            )}
          </div>
          <EjemploIncidente />
        </section>

        <ul className="grid gap-4 sm:grid-cols-3">
          {PUNTOS.map((p) => (
            <li key={p.titulo} className="rounded-lg border border-border bg-card p-4">
              <h2 className="font-semibold">{p.titulo}</h2>
              <p className="mt-2 text-sm text-foreground/80">{p.texto}</p>
            </li>
          ))}
        </ul>

        <section aria-labelledby="titulo-alcance" className="grid gap-6 sm:grid-cols-2">
          <div>
            <h2 id="titulo-alcance" className="text-xl font-semibold">Alcance y permisos</h2>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-foreground/80">
              <li>Aave V3 en Ethereum mainnet. Nada más por ahora.</li>
              <li>Me das direcciones públicas; no pido claves, firmas ni conexión de wallet.</li>
              <li>Las personas de tu organización tienen rol de dueño, operación o lectura.</li>
              <li>Las notificaciones salen por un canal que configurás y probás antes.</li>
            </ul>
          </div>
          <div>
            <h2 className="text-xl font-semibold">Qué datos guardo</h2>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-foreground/80">
              <li>Las direcciones que observás y los snapshots de sus posiciones.</li>
              <li>Tus políticas, incidentes, evidencia y quién hizo qué.</li>
              <li>Eventos de uso sin correos, direcciones ni montos, para medir si el producto sirve.</li>
              <li>Tu email de acceso. No lo uso para marketing.</li>
            </ul>
          </div>
        </section>

        <section aria-labelledby="titulo-piloto" className="rounded-lg border border-border bg-card p-6">
          <h2 id="titulo-piloto" className="text-xl font-semibold">Piloto de lectura</h2>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-foreground/80">
            <li>Hasta 10 cuentas, una red y un mercado, evaluación cada minuto como máximo.</li>
            <li>Acompañamiento en la configuración y en la revisión de los primeros incidentes.</li>
            <li>Prueba de 14 días con el mismo alcance; después, USD 150 por organización y mes.</li>
          </ul>
          <p className="mt-3 text-sm text-muted-foreground">
            USD 150 es el precio que estoy validando con los primeros pilotos, no una tarifa definitiva. Cobro con factura; no pido tarjeta.
          </p>
        </section>

        <section aria-labelledby="titulo-preguntas">
          <h2 id="titulo-preguntas" className="text-xl font-semibold">Preguntas frecuentes</h2>
          <div className="mt-3 space-y-2">
            {PREGUNTAS.map((q) => (
              <details key={q.p} className="rounded-lg border border-border bg-card p-4">
                <summary className="cursor-pointer font-medium">{q.p}</summary>
                <p className="mt-2 text-sm text-foreground/80">{q.r}</p>
              </details>
            ))}
          </div>
        </section>

        <section id="contacto" aria-labelledby="titulo-contacto">
          <h2 id="titulo-contacto" className="text-xl font-semibold">Contacto</h2>
          <p className="mb-3 mt-1 text-sm text-muted-foreground">Si querés un piloto o tenés preguntas, escribime.</p>
          <Contacto />
        </section>
      </main>
    </div>
  );
}
