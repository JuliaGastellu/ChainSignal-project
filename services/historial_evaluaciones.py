"""Historial de evaluaciones y resultados de ejecución (antes LearningStore).

Esto no es aprendizaje: guardo qué señales vi y qué pasó con cada intento de
ejecución del experimento, y lo cuento. Nada de este historial decide ni
autoriza estrategias.

Una transacción aceptada por la red (estado "success") solo dice que la red la
incluyó. No dice que la estrategia fuera rentable ni correcta, así que no la
uso como etiqueta de calidad. Por eso el resumen la llama
`accepted_transactions` y no "éxitos".
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List


class HistorialEvaluaciones:
    def __init__(self, ruta: str = "storage/historial_evaluaciones.json"):
        self.path = Path(ruta)
        # No escribo al construir el historial: la API debe arrancar también
        # cuando el código está montado en un directorio de solo lectura.
        # Creo el directorio en _save únicamente si guardo una evaluación.

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"signals": [], "outcomes": []}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("signals", [])
                    data.setdefault("outcomes", [])
                    return data
        except Exception:
            pass
        return {"signals": [], "outcomes": []}

    def _save(self, data: Dict[str, Any]) -> None:
        # Creo el directorio también al guardar: el path es relativo y el
        # directorio de trabajo puede no ser el del momento de construcción.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def registrar_senales(self, wallet: str, signals: List[Dict[str, Any]], strategy: str) -> None:
        data = self._load()
        data["signals"].append({"timestamp": time.time(), "wallet": wallet, "signals": signals, "strategy": strategy})
        data["signals"] = data["signals"][-500:]
        self._save(data)

    def registrar_resultado(self, wallet: str, status: str, strategy: str, moved_eth: float, tx_hash: str | None = None) -> None:
        data = self._load()
        data["outcomes"].append(
            {
                "timestamp": time.time(),
                "wallet": wallet,
                "status": status,
                "strategy": strategy,
                "moved_eth": moved_eth,
                "tx_hash": tx_hash,
            }
        )
        data["outcomes"] = data["outcomes"][-500:]
        self._save(data)

    def resumen(self) -> Dict[str, Any]:
        """Conteos descriptivos. No incluyo nada por estrategia que pueda leerse como tasa de acierto."""
        data = self._load()
        signals = data.get("signals", [])
        outcomes = data.get("outcomes", [])
        signal_frequency: Dict[str, int] = {}
        for item in signals[-200:]:
            for signal in item.get("signals", []) or []:
                key = str(signal.get("type", "UNKNOWN"))
                signal_frequency[key] = signal_frequency.get(key, 0) + 1
        outcome_status: Dict[str, int] = {}
        for item in outcomes:
            key = str(item.get("status", "unknown"))
            outcome_status[key] = outcome_status.get(key, 0) + 1
        return {
            "signals_count": len(signals),
            "outcomes_count": len(outcomes),
            "accepted_transactions": outcome_status.get("success", 0),
            "outcome_status": outcome_status,
            "latest_signal": signals[-1] if signals else None,
            "latest_outcome": outcomes[-1] if outcomes else None,
            "signal_frequency": signal_frequency,
        }
