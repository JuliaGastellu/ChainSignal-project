"""Servicio de monetización x402 para ChainSignal.

Implementa el protocolo x402 como capa de acceso a los reportes de análisis.
El flujo es:
  1. Cliente solicita GET /report/{wallet}
  2. Si no hay header X-Payment, el servicio emite un HTTP 402 con los datos
     de pago requeridos (monto, receptor, token).
  3. El cliente realiza el pago en USD₮ via WDK y vuelve a llamar con
     el header X-Payment que contiene el comprobante.
  4. El servicio valida el comprobante y entrega el reporte.

Si X402_ENABLED=false en el entorno, el servicio retorna un error descriptivo
sin crash (degradación limpia).
"""

import os
from dataclasses import dataclass

from loguru import logger


# Precio del reporte en USD₮ (en unidades base, 6 decimales para USDT)
_PRECIO_REPORTE_USDT_BASE = int(os.getenv("X402_REPORT_PRICE_USDT", "1")) * 1_000_000

# Dirección receptora de los pagos (wallet del agente)
_RECEPTOR_PAGO = os.getenv("X402_PAYMENT_RECIPIENT", "")

# Dirección del contrato USD₮ en Sepolia (testnet)
_USDT_SEPOLIA = "0x7169D38820dfd117C3FA1f22a697dBA58d90BA06"


@dataclass
class ChallengeX402:
    """Representa el desafío de pago HTTP 402 emitido por el servidor."""

    monto: int          # En unidades base del token (ej. 1_000_000 para 1 USDT)
    token: str          # Dirección del contrato del token de pago
    receptor: str       # Dirección Ethereum que recibirá el pago
    descripcion: str    # Descripción del recurso que se está comprando

    def to_dict(self) -> dict:
        """Serializes the challenge as a JSON-serializable dict."""
        return {
            "error": "Payment required to access this resource.",
            "payment_required": True,
            "base_amount": self.monto,
            "formatted_amount": f"{self.monto / 1_000_000:.2f} USDT",
            "token": self.token,
            "recipient": self.receptor,
            "description": self.descripcion,
            "instructions": (
                "Make the payment in USDT to the 'recipient' address using the WDK "
                "and call this endpoint again with the X-Payment header: "
                "<tx_hash_of_the_payment>"
            ),
        }


class ValidadorX402:
    """Valida comprobantes de pago para el protocolo x402.

    En el contexto de ChainSignal (testnet), la validación comprueba:
    - Que el header X-Payment sea un hash de transacción válido (0x + 64 hex chars).
    - Que el hash no haya sido usado antes (anti-replay).

    En un sistema de producción, esto verificaría el hash on-chain via RPC.
    """

    def __init__(self):
        # Registro de hashes ya usados para prevenir replay attacks
        self._hashes_usados: set[str] = set()

    def esta_habilitado(self) -> bool:
        """Returns True if x402 is enabled in the environment."""
        valor = os.getenv("X402_ENABLED", "true").lower()
        return valor in ("true", "1", "yes")

    def extraer_hash_pago(self, headers: dict) -> str | None:
        """Extracts the payment hash from the X-Payment header.

        Args:
            headers: Dict of HTTP request headers.

        Returns:
            The transaction hash if it exists, None if not present.
        """
        return headers.get("x-payment") or headers.get("X-Payment")

    def validar(self, hash_pago: str) -> tuple[bool, str]:
        """Validates that the payment hash is structurally correct and not used.

        Args:
            hash_pago: Ethereum transaction hash (0x + 64 hex characters).

        Returns:
            Tuple (valid: bool, reason: str).
        """
        if not hash_pago:
            return False, "X-Payment header not present."

        # Structural validation: 0x + 64 hex characters
        if not hash_pago.startswith("0x") or len(hash_pago) != 66:
            return False, f"Invalid hash format: '{hash_pago[:20]}...'"

        # Check hex characters
        try:
            int(hash_pago[2:], 16)
        except ValueError:
            return False, "The hash contains non-hexadecimal characters."

        # Anti-replay: check it hasn't been used before
        if hash_pago.lower() in self._hashes_usados:
            return False, "This payment proof has already been used."

        # Register as used
        self._hashes_usados.add(hash_pago.lower())
        logger.info("x402 payment validated. Hash: {}", hash_pago)
        return True, "Valid payment."


class GatewayX402:
    """Orquesta el flujo de acceso protegido via x402.

    Expone dos operaciones principales:
        - emitir_challenge(): Genera el HTTP 402 con los datos de pago.
        - verificar_acceso(): Valida si la request tiene pago válido.
    """

    def __init__(self):
        self._validador = ValidadorX402()

    def emitir_challenge(self, descripcion: str) -> ChallengeX402:
        """Genera el desafío de pago para un recurso.

        Args:
            descripcion: Descripción human-readable del recurso (ej. wallet).

        Returns:
            ChallengeX402 listo para serializar como respuesta 402.
        """
        return ChallengeX402(
            monto=_PRECIO_REPORTE_USDT_BASE,
            token=_USDT_SEPOLIA,
            receptor=_RECEPTOR_PAGO,
            descripcion=descripcion,
        )

    def verificar_acceso(self, headers: dict) -> tuple[bool, str]:
        """Verifies if the request has a valid payment proof.

        Args:
            headers: Dict of HTTP headers.

        Returns:
            Tuple (access_allowed: bool, reason: str).
        """
        if not self._validador.esta_habilitado():
            # x402 disabled: require access anyway but with notice
            return False, (
                "x402 is disabled in this environment (X402_ENABLED=false). "
                "Configure X402_ENABLED=true to enable protected access."
            )

        hash_pago = self._validador.extraer_hash_pago(headers)
        if not hash_pago:
            return False, "X-Payment header not present."

        return self._validador.validar(hash_pago)
