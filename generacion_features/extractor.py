"""Extractor de features a partir de los datos on-chain de una wallet.

Solo afirmo lo que puedo demostrar con la ventana ingerida:
- primera_actividad_observada_timestamp es la actividad más vieja que observé,
  no la creación de la wallet; si historial_completo es False, la wallet puede
  ser más vieja.
- dias_observados es el lapso entre la primera y la última actividad observada.
- Identifico tokens por red y contrato; el símbolo es solo una etiqueta.
- diversidad_tokens es la entropía de Shannon normalizada (0 a 1) sobre la
  cantidad de transferencias por contrato.
- Sumo montos con Decimal desde enteros y convierto a float solo al final.
"""

import math
import time
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ingestion_onchain.modelos import CONTEXTO_MONTOS, DatosWallet
from ingestion_onchain.resultados import CalidadDatos


@dataclass
class FeaturesWallet:
    """Features derivadas de la actividad observada en la ventana ingerida."""

    direccion: str
    chain_id: int = 1

    # Métricas de actividad
    total_transacciones: int = 0
    frecuencia_transacciones_por_dia: float = 0.0
    volumen_total_transferido_eth: float = 0.0
    numero_wallets_interactuadas: int = 0
    # None si no pude leer el balance: nunca lo reemplazo por cero.
    balance_eth_actual: Optional[float] = None

    # Tokens, identificados por (chain_id, contrato)
    tokens_unicos_utilizados: int = 0
    token_mas_utilizado: str = "ninguno"
    token_mas_utilizado_contrato: Optional[str] = None
    diversidad_tokens: float = 0.0
    transferencias_token_total: int = 0

    # Patrones de comportamiento
    ratio_envios_vs_recepciones: float = 0.0
    porcentaje_transacciones_recientes: float = 0.0
    interacciones_contratos: int = 0
    porcentaje_interacciones_contratos: float = 0.0
    transacciones_con_error: int = 0
    diversidad_protocolos: float = 0.0

    # Contexto temporal observado
    primera_actividad_observada_timestamp: int = 0
    ultima_transaccion_timestamp: int = 0
    dias_observados: int = 0
    historial_completo: bool = False

    calidad_datos: Optional[CalidadDatos] = None


def entropia_normalizada(conteos) -> float:
    """Entropía de Shannon dividida por log(k): 0 si hay un solo token, 1 si el uso es parejo."""
    valores = [c for c in conteos if c > 0]
    k = len(valores)
    if k <= 1:
        return 0.0
    total = sum(valores)
    h = -sum((c / total) * math.log(c / total) for c in valores)
    return round(min(1.0, max(0.0, h / math.log(k))), 4)


class ExtractorFeatures:
    """Genera features a partir de DatosWallet."""

    SEGUNDOS_POR_DIA = 86_400
    VENTANA_RECIENTE_DIAS = 30

    def extraer(self, datos: DatosWallet) -> FeaturesWallet:
        features = FeaturesWallet(
            direccion=datos.direccion,
            chain_id=datos.chain_id,
            balance_eth_actual=None if datos.balance_eth is None else float(datos.balance_eth),
            calidad_datos=datos.calidad,
        )
        if datos.calidad is not None:
            componente = datos.calidad.componentes.get("transactions")
            features.historial_completo = bool(componente and componente.procedencia.historial_completo)

        txs = [tx for tx in datos.transacciones if not tx.es_error]
        if txs:
            self._calcular_metricas_actividad(features, txs, datos.direccion)
        if datos.transferencias_token:
            self._calcular_metricas_tokens(features, datos.transferencias_token)

        features.transacciones_con_error = sum(1 for tx in datos.transacciones if tx.es_error)
        self._calcular_patrones_comportamiento(features, datos.transacciones, datos.direccion, self._ahora_de_referencia(datos))
        return features

    @staticmethod
    def _ahora_de_referencia(datos: DatosWallet) -> int:
        """Mido "reciente" contra el bloque de referencia, no contra el reloj local."""
        if datos.calidad is not None:
            componente = datos.calidad.componentes.get("transactions")
            if componente and componente.procedencia.referencia:
                return componente.procedencia.referencia.timestamp
        return int(time.time())

    def _calcular_metricas_actividad(self, features: FeaturesWallet, txs: list, direccion: str) -> None:
        features.total_transacciones = len(txs)
        timestamps = [tx.timestamp for tx in txs]
        features.primera_actividad_observada_timestamp = min(timestamps)
        features.ultima_transaccion_timestamp = max(timestamps)

        lapso = features.ultima_transaccion_timestamp - features.primera_actividad_observada_timestamp
        features.dias_observados = max(1, lapso // self.SEGUNDOS_POR_DIA)
        features.frecuencia_transacciones_por_dia = round(features.total_transacciones / features.dias_observados, 4)

        direccion = direccion.lower()
        volumen = Decimal(0)
        for tx in txs:
            if tx.origen == direccion:
                volumen = CONTEXTO_MONTOS.add(volumen, tx.valor_eth)
        features.volumen_total_transferido_eth = round(float(volumen), 8)

        contrapartes = {tx.destino if tx.origen == direccion else tx.origen for tx in txs}
        features.numero_wallets_interactuadas = len(contrapartes)

    def _calcular_metricas_tokens(self, features: FeaturesWallet, transferencias: list) -> None:
        features.transferencias_token_total = len(transferencias)
        conteo = Counter(t.token.clave for t in transferencias)
        tokens = {t.token.clave: t.token for t in transferencias}
        features.tokens_unicos_utilizados = len(conteo)
        clave, _ = conteo.most_common(1)[0]
        features.token_mas_utilizado = tokens[clave].etiqueta
        features.token_mas_utilizado_contrato = tokens[clave].contrato
        features.diversidad_tokens = entropia_normalizada(conteo.values())

    def _calcular_patrones_comportamiento(self, features: FeaturesWallet, txs: list, direccion: str, ahora: int) -> None:
        direccion = direccion.lower()
        envios = sum(1 for tx in txs if tx.origen == direccion and not tx.es_error)
        recepciones = sum(1 for tx in txs if tx.destino == direccion and not tx.es_error)
        features.ratio_envios_vs_recepciones = round(envios / recepciones if recepciones > 0 else float(envios), 4)

        umbral_reciente = ahora - (self.VENTANA_RECIENTE_DIAS * self.SEGUNDOS_POR_DIA)
        total = len(txs)
        recientes = sum(1 for tx in txs if tx.timestamp >= umbral_reciente)
        features.porcentaje_transacciones_recientes = round(recientes / total * 100 if total > 0 else 0.0, 2)

        contratos = sum(1 for tx in txs if tx.es_contrato)
        features.interacciones_contratos = contratos
        features.porcentaje_interacciones_contratos = round(contratos / total * 100 if total > 0 else 0.0, 2)

        # Contratos distintos llamados, escalado a 10. Es una heurística de
        # exploración, no una medida de liquidez ni de riesgo.
        destinos_contratos = {tx.destino for tx in txs if tx.es_contrato and tx.destino}
        features.diversidad_protocolos = round(min(len(destinos_contratos), 10) / 10.0, 4) if total > 0 else 0.0
