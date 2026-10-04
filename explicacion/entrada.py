"""Entrada estructurada para explicar un incidente (E07).

Armo un JSON chico con los hechos que ya tengo: el incidente, la versión de la
regla que lo abrió, el snapshot de la posición y la evidencia. Cada hecho lleva
su referencia (`snapshot:<id>`, `rule_version:<n>`, `evidence:<id>`) y una
explicación solo puede citar esas referencias.

Los textos que escribe una persona (nombre de la cuenta, nombre de la política,
notas) van aparte, en `untrusted_metadata`. Son datos, no instrucciones: la
plantilla no los usa y el validador rechaza una salida que los repita.

También compruebo si las cifras son consistentes entre sí. Si no lo son, lo
marco y ninguna explicación puede sacar conclusiones de ellas.
"""

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Dict, List, Optional

ESQUEMA_ENTRADA = "chainsignal.explicacion.entrada/1"
MAX_EVIDENCIAS = 20
MAX_TEXTO_METADATO = 200
MAX_BYTES_ENTRADA = 8000
TOLERANCIA_HF = Decimal("0.01")  # 1 % entre el health factor informado y el recalculado


class EntradaInvalida(ValueError):
    """La entrada excede los límites o le faltan datos mínimos."""


def _decimal(valor: Any) -> Optional[Decimal]:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def texto_no_confiable(valor: Any) -> Optional[str]:
    """Normalizo un texto ajeno: sin caracteres de control y con largo acotado."""
    if valor is None:
        return None
    texto = unicodedata.normalize("NFKC", str(valor))
    texto = "".join(c for c in texto if unicodedata.category(c)[0] != "C" or c == " ")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:MAX_TEXTO_METADATO] or None


def _consistencia(snapshot: Optional[Dict[str, Any]], observado: Dict[str, Any]) -> Dict[str, Any]:
    problemas: List[str] = []
    if snapshot:
        hf = _decimal(snapshot.get("health_factor"))
        colateral = _decimal(snapshot.get("collateral_base"))
        deuda = _decimal(snapshot.get("debt_base"))
        umbral_pct = _decimal(snapshot.get("liquidation_threshold_pct"))
        if snapshot.get("quality_reason") == "reconciliation_mismatch":
            problemas.append("reconciliation_mismatch")
        if snapshot.get("no_debt") is True and deuda is not None and deuda > 0:
            problemas.append("no_debt_with_debt")
        if hf is not None and colateral is not None and deuda and deuda > 0 and umbral_pct is not None:
            with localcontext() as ctx:
                ctx.prec = 60
                calculado = colateral * umbral_pct / Decimal(100) / deuda
                if calculado > 0 and abs(hf - calculado) / calculado > TOLERANCIA_HF:
                    problemas.append("health_factor_vs_collateral")
        hf_observado = _decimal(observado.get("health_factor"))
        if hf is not None and hf_observado is not None and hf_observado != 0 and abs(hf - hf_observado) / hf_observado > Decimal("0.0001"):
            problemas.append("observed_vs_snapshot")
    return {"figures_consistent": not problemas, "problems": problemas}


def construir_entrada(incidente: Dict[str, Any], regla: Dict[str, Any], snapshot: Optional[Dict[str, Any]],
                      metadatos: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Armo la entrada desde datos planos. No consulto la base ni la red."""
    evidencias = incidente.get("evidence") or []
    if len(evidencias) > MAX_EVIDENCIAS:
        evidencias = evidencias[:1] + evidencias[-(MAX_EVIDENCIAS - 1):]  # apertura y lo más reciente
    version = int(incidente["policy_version"])
    observado = dict(incidente.get("last_observed") or {})
    referencias = [f"rule_version:{version}"] + [f"evidence:{e['id']}" for e in evidencias]
    datos_snapshot = None
    if snapshot:
        referencias.insert(0, f"snapshot:{snapshot['id']}")
        datos_snapshot = {
            "ref": f"snapshot:{snapshot['id']}",
            "block_number": snapshot.get("block_number"),
            "block_hash": snapshot.get("block_hash"),
            "data_quality": snapshot.get("quality"),
            "quality_reason": snapshot.get("quality_reason"),
            "status": snapshot.get("status"),
            "health_factor": snapshot.get("health_factor"),
            "collateral_base": snapshot.get("collateral_base"),
            "debt_base": snapshot.get("debt_base"),
            "liquidation_threshold_pct": snapshot.get("liquidation_threshold_pct"),
            "no_debt": snapshot.get("no_debt"),
        }
    metadatos = metadatos or {}
    entrada = {
        "schema": ESQUEMA_ENTRADA,
        "incident": {
            "status": incidente.get("status"),
            "severity": incidente.get("severity"),
            "rule_type": incidente.get("rule_type"),
            "escalation_level": incidente.get("escalation_level", 0),
            "data_quality": incidente.get("data_quality"),
        },
        "rule": {"ref": f"rule_version:{version}", "version": version, **{k: v for k, v in regla.items() if k != "severity"}},
        "observed": observado,
        "snapshot": datos_snapshot,
        "evidence": [{"ref": f"evidence:{e['id']}", "kind": e.get("kind"), "block_number": e.get("block_number"),
                      "data_quality": e.get("data_quality")} for e in evidencias],
        "checks": _consistencia(snapshot, observado),
        "allowed_refs": referencias,
        "untrusted_metadata": {
            "account_label": texto_no_confiable(metadatos.get("account_label")),
            "policy_name": texto_no_confiable(metadatos.get("policy_name")),
            "notes": [t for t in (texto_no_confiable(n) for n in (metadatos.get("notes") or [])[:5]) if t],
        },
    }
    if len(serializar(entrada).encode("utf-8")) > MAX_BYTES_ENTRADA:
        raise EntradaInvalida("explanation input exceeds the size limit")
    return entrada


def serializar(entrada: Dict[str, Any]) -> str:
    return json.dumps(entrada, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def textos_no_confiables(entrada: Dict[str, Any]) -> List[str]:
    meta = entrada.get("untrusted_metadata") or {}
    textos = [meta.get("account_label"), meta.get("policy_name"), *(meta.get("notes") or [])]
    return [t for t in textos if t]


def valores_permitidos(entrada: Dict[str, Any]) -> List[Decimal]:
    """Cifras que una explicación puede mencionar: las de la entrada y derivadas simples."""
    candidatos: List[Any] = []
    regla = entrada.get("rule") or {}
    candidatos += [regla.get(k) for k in ("version", "threshold", "clear_above", "clear_after", "change_pct")]
    edad_max = _decimal(regla.get("max_age_seconds"))
    if edad_max is not None:
        candidatos += [edad_max, edad_max / 60]
    observado = entrada.get("observed") or {}
    candidatos += [observado.get(k) for k in ("health_factor", "threshold", "clear_above", "change_pct",
                                              "change_pct_threshold", "max_age_seconds")]
    edad = _decimal(observado.get("age_seconds"))
    if edad is not None:
        candidatos += [edad, edad / 60]
    deuda, base = _decimal(observado.get("debt_base")), _decimal(observado.get("baseline"))
    candidatos += [deuda, base]
    snap = entrada.get("snapshot") or {}
    candidatos += [snap.get(k) for k in ("block_number", "health_factor", "collateral_base", "debt_base",
                                         "liquidation_threshold_pct")]
    candidatos += [e.get("block_number") for e in entrada.get("evidence") or []]
    candidatos.append((entrada.get("incident") or {}).get("escalation_level"))
    return [d for d in (_decimal(c) for c in candidatos) if d is not None]


def hex_permitidos(entrada: Dict[str, Any]) -> List[str]:
    snap = entrada.get("snapshot") or {}
    return [h.lower() for h in [snap.get("block_hash")] if h]
