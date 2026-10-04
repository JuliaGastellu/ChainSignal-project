"""Intención de propuesta, huella y aprobación humana (spike E10).

La aprobación de una persona se ata a una huella SHA-256 de todo lo relevante:

- payload ordenado y su safeTxHash;
- organización, cadena, Safe y cuenta;
- nonce, acción y parámetros;
- versión de la política;
- simulación exacta (bloque, hash y digest del estado);
- expiración.

Cambiar cualquiera de esos campos cambia la huella y la aprobación deja de servir. Antes de enviar valido otra vez contra el
estado actual: misma red, mismo nonce del Safe, simulación reciente sobre el
mismo estado y sin vencer.
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from eth_utils import to_checksum_address

from experiments.propuestas_safe.safe_tx import ACCIONES, SafeTx, armar_safe_tx, safe_tx_hash

MAX_BLOQUES_SIMULACION = 25  # ≈ 5 minutos en mainnet
VIDA_PROPUESTA_SEGUNDOS = 3600


@dataclass(frozen=True)
class Simulacion:
    """Resultado de simular la SafeTx exacta sobre un bloque. Lo produce un simulador externo o un fork."""

    block_number: int
    block_hash: str
    ok: bool
    state_digest: str  # hash del estado previo relevante (balances, deuda, allowances)
    gas_estimate: int
    fee_estimate_wei: int
    expected_changes: List[Dict[str, Any]]
    approvals: List[Dict[str, Any]]


@dataclass(frozen=True)
class Intencion:
    id: str
    organization_id: str
    chain_id: int
    safe: str
    account: str
    policy_id: str
    policy_version: int
    accion: str
    parametros: Dict[str, Any]
    nonce: int
    safe_tx: SafeTx
    safe_tx_hash: str
    llamadas: List[Dict[str, Any]]
    efecto_esperado: Dict[str, Any]
    simulacion: Simulacion
    modo: str  # ATOMICO_MULTISEND | LLAMADA_UNICA
    creada_en: float
    expira_en: float

    def huella(self) -> str:
        datos = asdict(self)
        datos.pop("id")
        return hashlib.sha256(json.dumps(datos, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class Aprobacion:
    intencion_id: str
    huella: str
    aprobada_por: str
    aprobada_en: float


@dataclass
class Contexto:
    """Lo que observo en el momento de enviar."""

    chain_id: int
    nonce_safe: int
    bloque_actual: int
    state_digest_actual: str
    ahora: float
    errores: List[str] = field(default_factory=list)


class PropuestaInvalida(ValueError):
    pass


def crear_intencion(organization_id: str, chain_id: int, safe: str, account: str, policy_id: str, policy_version: int,
                    accion: str, parametros: Dict[str, Any], nonce: int, simulacion: Simulacion, ahora: float) -> Intencion:
    if accion not in ACCIONES:
        raise PropuestaInvalida(f"action {accion!r} is not allowed")
    safe, account = to_checksum_address(safe), to_checksum_address(account)
    if safe != account:
        # La propuesta solo gestiona la posición de la propia cuenta del cliente.
        raise PropuestaInvalida("the Safe must be the monitored account itself")
    llamadas, efecto = ACCIONES[accion](safe, **parametros)
    tx = armar_safe_tx(llamadas, nonce)
    return Intencion(
        id=uuid.uuid4().hex, organization_id=organization_id, chain_id=chain_id, safe=safe, account=account, policy_id=policy_id,
        policy_version=policy_version, accion=accion, parametros=dict(parametros), nonce=nonce, safe_tx=tx,
        safe_tx_hash=safe_tx_hash(chain_id, safe, tx), llamadas=[asdict(ll) for ll in llamadas], efecto_esperado=efecto,
        simulacion=simulacion, modo="ATOMICO_MULTISEND" if len(llamadas) > 1 else "LLAMADA_UNICA",
        creada_en=ahora, expira_en=ahora + VIDA_PROPUESTA_SEGUNDOS,
    )


def aprobar(intencion: Intencion, persona: str, ahora: float) -> Aprobacion:
    if not intencion.simulacion.ok:
        raise PropuestaInvalida("the simulation failed; nothing to approve")
    if ahora >= intencion.expira_en:
        raise PropuestaInvalida("the proposal expired")
    return Aprobacion(intencion.id, intencion.huella(), persona, ahora)


def validar_para_envio(intencion: Intencion, aprobacion: Optional[Aprobacion], ctx: Contexto) -> List[str]:
    errores = []
    if aprobacion is None or aprobacion.intencion_id != intencion.id:
        errores.append("approval_missing")
    elif aprobacion.huella != intencion.huella():
        errores.append("approval_does_not_match_payload")
    if safe_tx_hash(intencion.chain_id, intencion.safe, intencion.safe_tx) != intencion.safe_tx_hash:
        errores.append("safe_tx_hash_mismatch")
    if ctx.chain_id != intencion.chain_id:
        errores.append("wrong_chain")
    if ctx.nonce_safe != intencion.nonce:
        errores.append("wrong_nonce")
    if ctx.ahora >= intencion.expira_en:
        errores.append("expired")
    if not intencion.simulacion.ok:
        errores.append("simulation_failed")
    if (ctx.bloque_actual - intencion.simulacion.block_number > MAX_BLOQUES_SIMULACION
            or ctx.state_digest_actual != intencion.simulacion.state_digest):
        errores.append("stale_simulation")
    return errores


def reemplazar(intencion: Intencion, **cambios: Any) -> Intencion:
    """Para pruebas y revisiones: una copia con campos cambiados (la huella cambia)."""
    datos = {**intencion.__dict__, **cambios}
    return Intencion(**datos)
