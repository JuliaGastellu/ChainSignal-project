"""Primitivas de seguridad de la identidad: contraseñas y tokens.

Uso scrypt de la biblioteca estándar para no sumar dependencias. Nunca guardo
contraseñas ni tokens en claro: de los tokens de sesión, CSRF e invitación solo
persisto su SHA-256, que alcanza porque son aleatorios de 256 bits.
"""

import base64
import hashlib
import hmac
import secrets

# Parámetros de scrypt: n=2**14, r=8, p=1 (unos 16 MiB por verificación).
_N, _R, _P = 2**14, 8, 1
_LARGO = 64
LARGO_MINIMO_CONTRASENA = 12


class ContrasenaInvalida(ValueError):
    pass


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def _desde_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def validar_contrasena(contrasena: str) -> None:
    if not isinstance(contrasena, str) or len(contrasena) < LARGO_MINIMO_CONTRASENA:
        raise ContrasenaInvalida(f"La contraseña debe tener al menos {LARGO_MINIMO_CONTRASENA} caracteres.")
    if len(contrasena) > 1024:
        raise ContrasenaInvalida("La contraseña es demasiado larga.")


def hashear_contrasena(contrasena: str) -> str:
    validar_contrasena(contrasena)
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(contrasena.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=_LARGO)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(derivada)}"


def verificar_contrasena(contrasena: str, almacenado: str) -> bool:
    try:
        esquema, n, r, p, sal, derivada = almacenado.split("$")
        if esquema != "scrypt":
            return False
        calculada = hashlib.scrypt(
            contrasena.encode("utf-8"), salt=_desde_b64(sal), n=int(n), r=int(r), p=int(p), dklen=len(_desde_b64(derivada))
        )
        return hmac.compare_digest(calculada, _desde_b64(derivada))
    except Exception:
        return False


# Hash de una contraseña aleatoria: lo verifico cuando el email no existe, así
# el tiempo de respuesta no revela qué emails están registrados.
_HASH_SENUELO = hashear_contrasena(secrets.token_urlsafe(24))


def verificar_contra_senuelo(contrasena: str) -> None:
    verificar_contrasena(contrasena, _HASH_SENUELO)


def nuevo_token() -> str:
    return secrets.token_urlsafe(32)


def hashear_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_iguales(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def nuevo_id() -> str:
    return secrets.token_hex(16)
