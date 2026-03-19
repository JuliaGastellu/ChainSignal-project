"""Extractor de features a partir de los datos on-chain de una wallet."""

import time
from collections import Counter
from dataclasses import dataclass

from ingestion_onchain.modelos import DatosWallet


@dataclass
class FeaturesWallet:
    """Conjunto de features estructuradas derivadas de la actividad on-chain."""

    direccion: str

    # Métricas de actividad
    total_transacciones: int = 0
    frecuencia_transacciones_por_dia: float = 0.0
    volumen_total_transferido_eth: float = 0.0
    numero_wallets_interactuadas: int = 0
    balance_eth_actual: float = 0.0

    # Análisis de tokens
    tokens_unicos_utilizados: int = 0
    token_mas_utilizado: str = "ninguno"
    diversidad_tokens: float = 0.0
    transferencias_token_total: int = 0

    # Patrones de comportamiento
    ratio_envios_vs_recepciones: float = 0.0
    porcentaje_transacciones_recientes: float = 0.0
    interacciones_contratos: int = 0
    porcentaje_interacciones_contratos: float = 0.0
    transacciones_con_error: int = 0

    # Contexto temporal
    primera_transaccion_timestamp: int = 0
    ultima_transaccion_timestamp: int = 0
    dias_activo: int = 0


class ExtractorFeatures:
    """Genera features estructuradas a partir de los datos crudos de una wallet."""

    SEGUNDOS_POR_DIA = 86_400
    VENTANA_RECIENTE_DIAS = 30

    def extraer(self, datos: DatosWallet) -> FeaturesWallet:
        """Procesa los datos crudos y retorna el conjunto de features."""
        features = FeaturesWallet(
            direccion=datos.direccion,
            balance_eth_actual=datos.balance_eth,
        )

        txs = [tx for tx in datos.transacciones if not tx.es_error]
        transferencias = datos.transferencias_token

        if txs:
            self._calcular_metricas_actividad(features, txs, datos.direccion)
        if transferencias:
            self._calcular_metricas_tokens(features, transferencias, datos.direccion)

        features.transacciones_con_error = sum(1 for tx in datos.transacciones if tx.es_error)
        self._calcular_patrones_comportamiento(features, datos.transacciones, datos.direccion)

        return features

    def _calcular_metricas_actividad(self, features: FeaturesWallet, txs: list, direccion: str) -> None:
        """Calcula métricas generales de actividad."""
        features.total_transacciones = len(txs)

        timestamps = [tx.timestamp for tx in txs]
        features.primera_transaccion_timestamp = min(timestamps)
        features.ultima_transaccion_timestamp = max(timestamps)

        diferencia_segundos = features.ultima_transaccion_timestamp - features.primera_transaccion_timestamp
        features.dias_activo = max(1, diferencia_segundos // self.SEGUNDOS_POR_DIA)
        features.frecuencia_transacciones_por_dia = round(
            features.total_transacciones / features.dias_activo, 4
        )

        direccion_lower = direccion.lower()
        features.volumen_total_transferido_eth = round(
            sum(tx.valor_eth for tx in txs if tx.origen == direccion_lower), 4
        )

        contrapartes = set()
        for tx in txs:
            if tx.origen == direccion_lower:
                contrapartes.add(tx.destino)
            else:
                contrapartes.add(tx.origen)
        features.numero_wallets_interactuadas = len(contrapartes)

    def _calcular_metricas_tokens(
        self, features: FeaturesWallet, transferencias: list, direccion: str
    ) -> None:
        """Calcula métricas relacionadas con el uso de tokens ERC-20."""
        features.transferencias_token_total = len(transferencias)

        conteo_tokens = Counter(t.simbolo_token for t in transferencias)
        features.tokens_unicos_utilizados = len(conteo_tokens)

        if conteo_tokens:
            features.token_mas_utilizado = conteo_tokens.most_common(1)[0][0]

        total = sum(conteo_tokens.values())
        if total > 0 and features.tokens_unicos_utilizados > 0:
            proporciones = [c / total for c in conteo_tokens.values()]
            entropia = -sum(p * (p ** 0.5) for p in proporciones if p > 0)
            features.diversidad_tokens = round(min(1.0, abs(entropia)), 4)

    def _calcular_patrones_comportamiento(
        self, features: FeaturesWallet, txs: list, direccion: str
    ) -> None:
        """Calcula patrones de envíos, recepciones e interacciones con contratos."""
        direccion_lower = direccion.lower()
        envios = sum(1 for tx in txs if tx.origen == direccion_lower and not tx.es_error)
        recepciones = sum(1 for tx in txs if tx.destino == direccion_lower and not tx.es_error)

        features.ratio_envios_vs_recepciones = round(
            envios / recepciones if recepciones > 0 else float(envios), 4
        )

        ahora = int(time.time())
        umbral_reciente = ahora - (self.VENTANA_RECIENTE_DIAS * self.SEGUNDOS_POR_DIA)
        recientes = sum(1 for tx in txs if tx.timestamp >= umbral_reciente)
        total = len(txs)
        features.porcentaje_transacciones_recientes = round(
            recientes / total * 100 if total > 0 else 0.0, 2
        )

        contratos = sum(1 for tx in txs if tx.es_contrato)
        features.interacciones_contratos = contratos
        features.porcentaje_interacciones_contratos = round(
            contratos / total * 100 if total > 0 else 0.0, 2
        )
