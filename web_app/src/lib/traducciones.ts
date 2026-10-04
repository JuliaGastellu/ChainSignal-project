// Traduzco al castellano los textos técnicos que llegan de la API (límites de
// lectura, detalles de calidad, errores de entrega y mensajes de error). El
// texto original no se pierde: lo muestro como "detalle técnico" en un
// desplegable, para conservar la trazabilidad.

interface Patron {
  re: RegExp;
  es: (m: RegExpMatchArray) => string;
}

const LIMITES: Patron[] = [
  {
    re: /^Addresses (?:resolved on-chain from PoolAddressesProvider; reference|from): (.+?)\.?$/,
    es: (m) => `Direcciones de los contratos de Aave tomadas de ${m[1]}.`,
  },
  {
    re: /^(\w+) at block (\d+) is (0x[0-9a-fA-F]+), differs from the address book \((0x[0-9a-fA-F]+)\)\.$/,
    es: (m) => `El contrato ${m[1]} en el bloque ${m[2]} no coincide con la referencia publicada: revisá antes de confiar en esta lectura.`,
  },
  {
    re: /^No debt: health factor is not applicable/,
    es: () => "Sin deuda: el health factor no aplica (no hay nada que liquidar).",
  },
  {
    re: /^E-mode category (\d+) is active/,
    es: (m) =>
      `La categoría E-mode ${m[1]} está activa: el LTV y el umbral de liquidación de la cuenta incluyen E-mode; los valores por activo son los de cada reserva.`,
  },
];

const DETALLES: Patron[] = [
  { re: /^block hash changed during the read/, es: () => "El bloque cambió durante la lectura (reorganización): los valores pueden mezclar dos versiones de la cadena." },
  { re: /^(\d+) reserve\(s\) could not be read/, es: (m) => `${m[1]} reserva(s) no se pudieron leer.` },
  { re: /^per-asset totals do not reconcile/, es: () => "La suma por activo no coincide con los totales del protocolo." },
  { re: /^reader is not configured for Ethereum mainnet/, es: () => "El lector no está configurado para Ethereum mainnet." },
  { re: /^block (\d+) not recorded/, es: (m) => `No hay datos del bloque ${m[1]}.` },
];

const ERRORES_ENTREGA: Record<string, string> = {
  webhooks_disabled: "Los envíos externos están deshabilitados en esta instancia.",
  https_required: "La URL tiene que usar https.",
  credentials_in_url: "La URL no puede incluir usuario ni contraseña.",
  port_not_allowed: "Solo acepto el puerto 443.",
  invalid_url: "La URL no es válida.",
  dns_error: "No pude resolver el nombre del destino.",
  destination_not_public: "El destino resuelve a una dirección privada o reservada; por seguridad no envío ahí.",
  tls_error: "El certificado TLS del destino no es válido o no es confiable.",
  timeout: "El destino no respondió a tiempo.",
  connection_error: "No pude conectarme con el destino.",
  "channel disabled": "El canal está deshabilitado.",
};

// Mensajes de la API que la interfaz puede mostrar. Lo que no está aquí no se
// muestra crudo: uso el texto general del código HTTP.
const MENSAJES_API: Record<string, string> = {
  "This address is already monitored on that chain.": "Esa dirección ya está en observación.",
  "An organization must keep at least one owner.": "La organización tiene que conservar al menos una persona dueña.",
  "That person is already a member.": "Esa persona ya es miembro de la organización.",
  "This policy has incidents; disable it instead of deleting it.": "La política tiene incidentes: pausala en lugar de borrarla.",
  "Incident is already resolved.": "El incidente ya estaba resuelto.",
  "The subscription already ended.": "La suscripción ya terminó.",
  "A resolution note is required (max 500 characters).": "La nota de resolución es obligatoria (hasta 500 caracteres).",
  "Invitation not found or no longer valid.": "La invitación no existe, ya se usó, se revocó o venció.",
  "This invitation was issued to a different email.": "La invitación es para otro email.",
  "Log in with the invited email to accept this invitation.": "Iniciá sesión con el email invitado para aceptar la invitación.",
  "Invalid email address.": "El email no es válido.",
  "External webhooks are disabled in this environment.": "Los envíos externos están deshabilitados en esta instancia.",
};

function aplicar(patrones: Patron[], texto: string): string | null {
  for (const p of patrones) {
    const m = texto.match(p.re);
    if (m) return p.es(m);
  }
  return null;
}

export interface TextoTraducido {
  texto: string;
  original: string;
  traducido: boolean;
}

export function traducirLimite(original: string): TextoTraducido {
  const es = aplicar(LIMITES, original);
  return { texto: es ?? "Hay una limitación técnica en esta lectura (ver detalle).", original, traducido: es !== null };
}

export function traducirDetalle(original: string): TextoTraducido {
  const es = aplicar(DETALLES, original);
  return { texto: es ?? "Ver el detalle técnico.", original, traducido: es !== null };
}

export function traducirErrorEntrega(codigo: string | null | undefined): string {
  if (!codigo) return "";
  if (ERRORES_ENTREGA[codigo]) return ERRORES_ENTREGA[codigo];
  const http = codigo.match(/^http_(\d{3})$/);
  if (http) return `El destino respondió HTTP ${http[1]}${Number(http[1]) >= 500 ? " (error del destino)" : ""}.`;
  const redireccion = codigo.match(/^redirect_not_followed_(\d{3})$/);
  if (redireccion) return `El destino respondió con una redirección (HTTP ${redireccion[1]}); por seguridad no la sigo.`;
  return "La entrega falló (ver detalle técnico).";
}

export function traducirMensajeApi(mensaje: string): string | null {
  return MENSAJES_API[mensaje] ?? null;
}
