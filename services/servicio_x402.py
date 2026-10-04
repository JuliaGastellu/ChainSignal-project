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
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger
from web3 import Web3
from infra.config import settings

# Platform-specific file locking
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# Paths for persistence
_USED_HASHES_FILE = Path("cache/used_payments.json")

# ERC20 Transfer event signature (keccak256("Transfer(address,address,uint256)"))
_TRANSFER_EVENT_SIGNATURE = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

@dataclass
class ChallengeX402:
    """Representa el desafío de pago HTTP 402 emitido por el servidor."""

    amount: int          # En unidades base del token (ej. 1_000_000 para 1 USDC)
    token: str           # Dirección del contrato del token de pago
    recipient: str       # Dirección Ethereum que recibirá el pago
    description: str     # Descripción del recurso que se está comprando
    chain: str = settings.X402_CHAIN_NAME
    chain_id: int = settings.SEPOLIA_CHAIN_ID
    symbol: str = "USDC"
    decimals: int = 6

    def to_dict(self) -> dict:
        """Serializes the challenge as a JSON-serializable dict."""
        return {
            "error": "Payment required to access this resource.",
            "payment_required": True,
            "challenge": {
                "chain": self.chain,
                "chain_id": self.chain_id,
                "token": self.symbol,
                "token_address": self.token,
                "recipient": self.recipient,
                "amount": str(self.amount),
                "decimals": self.decimals,
                "formatted_amount": f"{self.amount / (10**self.decimals):.2f} {self.symbol}",
                "description": self.description,
                "instructions": (
                    f"Send {self.amount / (10**self.decimals):.2f} {self.symbol} on {self.chain} "
                    f"to {self.recipient} and provide the transaction hash in X-Payment header."
                ),
            }
        }


class ValidadorX402:
    """Valida comprobantes de pago para el protocolo x402.

    Soporta validación dual:
    - Modo Simulación (local): Solo verifica formato del hash.
    - Modo Producción (real): Verifica on-chain via RPC que el pago sea válido.
    """

    def __init__(self):
        self._hashes_usados: set[str] = self._cargar_hashes_usados()
        self.w3 = None
        if settings.SEPOLIA_RPC_URL:
            try:
                self.w3 = Web3(Web3.HTTPProvider(settings.SEPOLIA_RPC_URL))
                if not self.w3.is_connected():
                    logger.warning("No se pudo conectar al provider Web3 para x402.")
                    self.w3 = None
            except Exception as e:
                logger.error(f"Error inicializando Web3: {e}")

    def _cargar_hashes_usados(self) -> set[str]:
        """Carga los hashes usados desde el archivo de persistencia."""
        if _USED_HASHES_FILE.exists():
            try:
                with open(_USED_HASHES_FILE, "r") as f:
                    return set(json.load(f))
            except Exception as e:
                logger.error(f"Error cargando hashes usados: {e}")
        return set()

    def _guardar_hash_usado(self, hash_pago: str):
        """Guarda un hash en el archivo de persistencia (thread-safe con file locking)."""
        hash_lower = hash_pago.lower()
        try:
            _USED_HASHES_FILE.parent.mkdir(exist_ok=True)
            
            # Abrir archivo en modo a+ (append+read) para crear si no existe
            with open(_USED_HASHES_FILE, "a+") as f:
                # Aplicar file lock (platform-specific)
                try:
                    if sys.platform == "win32":
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    
                    try:
                        # Recargar desde disco (otro proceso pudo modificar)
                        f.seek(0)
                        existing = set()
                        try:
                            content = f.read()
                            if content.strip():
                                data = json.loads(content)
                                existing = set(data)
                        except (json.JSONDecodeError, ValueError):
                            pass
                        
                        # Agregar hash nuevo
                        existing.add(hash_lower)
                        self._hashes_usados = existing  # Actualizar en memoria
                        
                        # Escribir archivo completo
                        f.seek(0)
                        f.truncate()
                        json.dump(sorted(list(existing)), f)
                        
                    finally:
                        # Liberar lock
                        if sys.platform == "win32":
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception as e_lock:
                    logger.error(f"Error with file lock: {e_lock}")
                            
        except Exception as e:
            logger.error(f"Error guardando hash usado (con lock): {e}")

    def esta_habilitado(self) -> bool:
        """Devuelvo True si x402 está habilitado en el entorno."""
        valor = os.getenv("X402_ENABLED", "true").lower()
        return valor in ("true", "1", "yes")

    def extraer_hash_pago(self, headers: dict) -> Optional[str]:
        """Extraigo el hash de pago del header X-Payment."""
        return headers.get("x-payment") or headers.get("X-Payment")

    def validar(self, hash_pago: str) -> Tuple[bool, str]:
        """Valida el comprobante de pago."""
        if not hash_pago:
            return False, "X-Payment header not present."

        # Structural validation: 0x + 64 hex characters
        if not hash_pago.startswith("0x") or len(hash_pago) != 66:
            return False, f"Invalid hash format."

        # Anti-replay: check it hasn't been used before
        if hash_pago.lower() in self._hashes_usados:
            return False, "This payment proof has already been used."

        # Si no estamos en producción, aceptamos cualquier hash con formato válido
        if not settings.is_production:
            logger.info("x402 payment accepted (SIMULATION MODE). Hash: {}", hash_pago)
            self._guardar_hash_usado(hash_pago)
            return True, "Valid payment (simulation)."

        # Validación REAL on-chain
        return self.verificar_transaccion_onchain(hash_pago)

    def verificar_transaccion_onchain(self, tx_hash: str) -> Tuple[bool, str]:
        """Verifica una transacción ERC-20 real en la blockchain."""
        if not self.w3:
            return False, "On-chain validation failed: Provider not available."

        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if not receipt or receipt['status'] != 1:
                return False, "Transaction failed or not found on-chain."

            # Buscar evento Transfer en los logs
            usdc_address = settings.USDC_ADDRESS_SEPOLIA.lower()
            recipient_expected = settings.X402_PAYMENT_RECIPIENT.lower()
            amount_required = settings.X402_REPORT_PRICE_USDC * 1_000_000

            for log in receipt['logs']:
                # Verificar que el log sea del contrato USDC
                if log['address'].lower() != usdc_address:
                    continue
                
                # Verificar que sea un evento Transfer
                topics = log['topics']
                if not topics or topics[0].hex() != _TRANSFER_EVENT_SIGNATURE:
                    continue
                
                # topics[2] es el destinatario (indexed address)
                # El formato es 32 bytes (padded), necesitamos extraer los últimos 20 bytes
                recipient_found = "0x" + topics[2].hex()[-40:].lower()
                
                if recipient_found != recipient_expected:
                    continue
                
                # El valor está en el campo 'data' si no es indexed
                value = int(log['data'].hex(), 16)
                
                if value >= amount_required:
                    logger.success(f"Pago x402 validado on-chain: {value} USDC. Hash: {tx_hash}")
                    self._guardar_hash_usado(tx_hash)
                    return True, "Payment verified on-chain."

            return False, f"No valid USDC transfer to {recipient_expected} found in transaction."

        except Exception as e:
            logger.error(f"Error verificando transacción {tx_hash}: {e}")
            return False, f"Verification error: {str(e)}"


class GatewayX402:
    """Orquesta el flujo de acceso protegido via x402."""

    def __init__(self):
        self._validador = ValidadorX402()

    def emitir_challenge(self, descripcion: str) -> ChallengeX402:
        """Genera el desafío de pago para un recurso."""
        return ChallengeX402(
            amount=settings.X402_REPORT_PRICE_USDC * 1_000_000,
            token=settings.USDC_ADDRESS_SEPOLIA,
            recipient=settings.X402_PAYMENT_RECIPIENT,
            description=descripcion,
        )

    def verificar_acceso(self, headers: dict) -> Tuple[bool, str]:
        """Verifica si la request tiene un pago válido."""
        if not self._validador.esta_habilitado():
            return True, "x402 is disabled."

        hash_pago = self._validador.extraer_hash_pago(headers)
        if not hash_pago:
            return False, "X-Payment header not present."

        return self._validador.validar(hash_pago)
