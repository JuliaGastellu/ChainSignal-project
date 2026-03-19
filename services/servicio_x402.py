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
        """Serializa el challenge como dict JSON-serializable."""
        return {
            "error": "Pago requerido para acceder a este recurso.",
            "payment_required": True,
            "monto_base": self.monto,
            "monto_formateado": f"{self.monto / 1_000_000:.2f} USDT",
            "token": self.token,
            "receptor": self.receptor,
            "descripcion": self.descripcion,
            "instrucciones": (
                "Realizá el pago en USD₮ a la dirección 'receptor' usando el WDK "
                "y volvé a llamar este endpoint con el header "
                "X-Payment: <tx_hash_del_pago>"
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
        """Retorna True si x402 está habilitado en el entorno."""
        valor = os.getenv("X402_ENABLED", "true").lower()
        return valor in ("true", "1", "yes")

    def extraer_hash_pago(self, headers: dict) -> str | None:
        """Extrae el hash de pago del header X-Payment.

        Args:
            headers: Dict de headers HTTP de la request.

        Returns:
            El hash de transacción si existe, None si no está presente.
        """
        return headers.get("x-payment") or headers.get("X-Payment")

    def validar(self, hash_pago: str) -> tuple[bool, str]:
        """Valida que el hash de pago sea estructuralmente correcto y no usado.

        Args:
            hash_pago: Hash de transacción Ethereum (0x + 64 caracteres hex).

        Returns:
            Tupla (válido: bool, motivo: str).
        """
        if not hash_pago:
            return False, "Header X-Payment no presente."

        # Validación estructural: 0x + 64 chars hexadecimales
        if not hash_pago.startswith("0x") or len(hash_pago) != 66:
            return False, f"Formato de hash inválido: '{hash_pago[:20]}...'"

        # Verificar caracteres hexadecimales
        try:
            int(hash_pago[2:], 16)
        except ValueError:
            return False, "El hash contiene caracteres no hexadecimales."

        # Anti-replay: verificar que no haya sido usado
        if hash_pago.lower() in self._hashes_usados:
            return False, "Este comprobante de pago ya fue utilizado."

        # Registrar como usado
        self._hashes_usados.add(hash_pago.lower())
        logger.info("Pago x402 validado. Hash: {}", hash_pago)
        return True, "Pago válido."


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
        """Verifica si la request tiene un comprobante de pago válido.

        Args:
            headers: Dict de headers HTTP.

        Returns:
            Tupla (acceso_permitido: bool, motivo: str).
        """
        if not self._validador.esta_habilitado():
            # x402 deshabilitado: requerir acceso igual pero con aviso
            return False, (
                "x402 está deshabilitado en este entorno (X402_ENABLED=false). "
                "Configure X402_ENABLED=true para habilitar el acceso protegido."
            )

        hash_pago = self._validador.extraer_hash_pago(headers)
        if not hash_pago:
            return False, "Header X-Payment no presente."

        return self._validador.validar(hash_pago)
