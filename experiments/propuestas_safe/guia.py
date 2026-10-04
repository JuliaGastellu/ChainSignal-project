"""Guía manual y cuerpo de propuesta para el Safe Transaction Service (spike E10).

Nada de esto firma ni envía. La guía le dice a una persona del cliente qué va
a aprobar y cómo comprobar en su wallet que es exactamente eso (mismo
safeTxHash). El cuerpo de propuesta sigue el esquema del servicio
(POST /api/v2/safes/{address}/multisig-transactions/) y queda sin `sender` ni
`signature`: los completa un owner o un proposer (delegado) autorizado por los
owners, en su propia wallet. ChainSignal no guarda esa clave.
"""

from typing import Any, Dict, Optional

from eth_utils import from_wei

from experiments.propuestas_safe.propuesta import Intencion

RIESGOS = [
    "El precio y el health factor pueden cambiar entre la simulación y la ejecución; la simulación vence en pocos minutos.",
    "Si otra transacción usa el mismo nonce del Safe, esta propuesta queda inválida.",
    "Los approvals son por el monto exacto; si la ejecución falla, el approval puede quedar sin usar hasta que lo revoques.",
    "Ejecutar requiere el umbral de firmas del Safe; ChainSignal no firma ni ejecuta.",
]


def resumen_para_aprobacion(intencion: Intencion) -> Dict[str, Any]:
    sim = intencion.simulacion
    return {
        "safe_tx_hash": intencion.safe_tx_hash,
        "chain_id": intencion.chain_id,
        "safe": intencion.safe,
        "nonce": intencion.nonce,
        "mode": intencion.modo,
        "atomic": intencion.modo in ("ATOMICO_MULTISEND", "LLAMADA_UNICA"),
        "steps": [ll["descripcion"] for ll in intencion.llamadas],
        "fee_estimate_eth": str(from_wei(sim.fee_estimate_wei, "ether")),
        "gas_estimate": sim.gas_estimate,
        "approvals": sim.approvals,
        "expected_changes": sim.expected_changes,
        "simulated_at_block": sim.block_number,
        "expires_at": intencion.expira_en,
        "policy": {"id": intencion.policy_id, "version": intencion.policy_version},
        "risks": RIESGOS,
    }


def guia_manual(intencion: Intencion) -> str:
    r = resumen_para_aprobacion(intencion)
    pasos = "\n".join(f"{i}. {p}" for i, p in enumerate(r["steps"], 1))
    cambios = "\n".join(f"- {c}" for c in r["expected_changes"]) or "- (sin cambios declarados)"
    approvals = "\n".join(f"- {a}" for a in r["approvals"]) or "- ninguno"
    riesgos = "\n".join(f"- {x}" for x in r["risks"])
    tx = intencion.safe_tx
    return f"""# Propuesta para revisar y firmar en tu Safe

No es una orden ni una recomendación automática: es una propuesta que ChainSignal armó a partir de la política
{r['policy']['id']} (versión {r['policy']['version']}). Decidí vos si la firmás.

**Red:** chain_id {r['chain_id']} · **Safe:** {r['safe']} · **Nonce:** {r['nonce']}
**Modo:** {r['mode']} ({'todo o nada en una sola transacción' if r['atomic'] else 'pasos separados: puede quedar a medias'})

## Qué hace
{pasos}

## Cambios esperados (simulados en el bloque {r['simulated_at_block']})
{cambios}

## Approvals
{approvals}

## Costo estimado
{r['fee_estimate_eth']} ETH de gas (≈ {r['gas_estimate']} unidades), a precio de la simulación.

## Riesgos
{riesgos}

## Cómo crearla en Safe{{Wallet}}
1. Abrí el Safe {r['safe']} en Ethereum mainnet y elegí "Nueva transacción" → "Transaction Builder" en modo personalizado.
2. Cargá: to = `{tx.to}`, value = `{tx.value}`, operation = `{tx.operation}` ({'DELEGATECALL a MultiSendCallOnly' if tx.operation == 1 else 'CALL'}), data:
   `{tx.data}`
3. Usá el nonce {tx.nonce}. Antes de firmar, comprobá que tu wallet muestre exactamente este safeTxHash:
   **`{r['safe_tx_hash']}`**
   Si no coincide, no firmes.
4. La propuesta vence en {int((intencion.expira_en - intencion.creada_en) // 60)} minutos desde que se armó. Después, pedí una nueva.
"""


def cuerpo_propuesta_servicio(intencion: Intencion, sender: Optional[str] = None, signature: Optional[str] = None) -> Dict[str, Any]:
    """Cuerpo según el esquema del Safe Transaction Service 6.11.0. Sin firma no se puede enviar."""
    tx = intencion.safe_tx
    return {
        "safe": intencion.safe, "to": tx.to, "value": str(tx.value), "data": tx.data, "operation": tx.operation,
        "gasToken": tx.gas_token, "safeTxGas": str(tx.safe_tx_gas), "baseGas": str(tx.base_gas), "gasPrice": str(tx.gas_price),
        "refundReceiver": tx.refund_receiver, "nonce": str(tx.nonce), "contractTransactionHash": intencion.safe_tx_hash,
        "sender": sender, "signature": signature, "origin": "ChainSignal (propuesta con firma humana)",
    }
