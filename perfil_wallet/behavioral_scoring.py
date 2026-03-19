"""Motor de scoring conductual para perfiles de wallets Ethereum."""

from dataclasses import dataclass
from generacion_features.extractor import FeaturesWallet

class MetricaScoring:
    """Estructura obligatoria para cada métrica del dashboard."""
    def __init__(self, valor: int = 0, interpretacion: str = ""):
        self.valor = valor
        self.interpretacion = interpretacion

@dataclass
class BehavioralScores:
    """Conjunto de scores sobre el comportamiento de la wallet."""
    activity_score: MetricaScoring
    risk_score: MetricaScoring
    defi_engagement: MetricaScoring
    token_diversity: MetricaScoring
    protocol_exploration: MetricaScoring
    web3_activity_index: MetricaScoring # Nuevo índice de actividad Web3

class BehavioralScorer:
    """Calcula scores numéricos basados en las features on-chain."""

    def calcular_scores(self, f: FeaturesWallet) -> BehavioralScores:
        scores = BehavioralScores(
            activity_score=self._score_actividad(f),
            risk_score=self._score_riesgo(f),
            defi_engagement=self._score_defi(f),
            token_diversity=self._score_diversidad(f),
            protocol_exploration=self._score_exploracion(f),
            web3_activity_index=MetricaScoring(0, "") # Se calculará a continuación
        )
        
        # El índice de actividad Web3 es una combinación ponderada de otros scores
        scores.web3_activity_index = self._calcular_indice_web3(scores)
        
        return scores

    def _score_actividad(self, f: FeaturesWallet) -> MetricaScoring:
        """Puntaje de actividad basado en volumen y frecuencia de transacciones."""
        puntos = 0
        if f.frecuencia_transacciones_por_dia > 10: puntos += 40
        elif f.frecuencia_transacciones_por_dia > 2: puntos += 25
        elif f.frecuencia_transacciones_por_dia > 0.5: puntos += 10
        
        if f.total_transacciones > 1000: puntos += 40
        elif f.total_transacciones > 200: puntos += 25
        elif f.total_transacciones > 50: puntos += 10
        
        if f.porcentaje_transacciones_recientes > 70: puntos += 20
        elif f.porcentaje_transacciones_recientes > 30: puntos += 10
        
        valor = min(100, puntos)
        
        if valor >= 80: inter = "Actividad muy alta. Perfil intensivo."
        elif valor >= 50: inter = "Actividad moderada a alta."
        elif valor >= 20: inter = "Actividad regular en la red."
        else: inter = "Actividad baja o esporádica."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _score_riesgo(self, f: FeaturesWallet) -> MetricaScoring:
        """Estimación de riesgo basada en errores y patrones anómalos."""
        puntos = 0
        if f.transacciones_con_error > 20: puntos += 40
        elif f.transacciones_con_error > 5: puntos += 20
        
        if f.ratio_envios_vs_recepciones > 20: puntos += 30
        if f.dias_activo < 30: puntos += 30 # Wallets jóvenes son más arriesgadas
        
        valor = min(100, puntos)
        
        if valor >= 70: inter = "Alto riesgo. Patrones inusuales o muchos errores."
        elif valor >= 40: inter = "Riesgo moderado."
        elif valor >= 20: inter = "Riesgo bajo."
        else: inter = "Muy bajo riesgo. Perfil conservador."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _score_defi(self, f: FeaturesWallet) -> MetricaScoring:
        """Puntaje de interacción con protocolos DeFi y smart contracts."""
        valor = min(100, int(f.porcentaje_interacciones_contratos))
        
        if valor >= 80: inter = "Totalmente inmerso en protocolos DeFi/Smart Contracts."
        elif valor >= 50: inter = "Fuerte interacción con protocolos."
        elif valor >= 20: inter = "Uso moderado de aplicaciones descentralizadas."
        else: inter = "Baja interacción con contratos, uso principal como transferencia."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _score_diversidad(self, f: FeaturesWallet) -> MetricaScoring:
        """Puntaje de diversidad de tokens utilizados en la red."""
        puntos = int(f.diversidad_tokens * 80)
        if f.tokens_unicos_utilizados > 20: puntos += 20
        elif f.tokens_unicos_utilizados > 5: puntos += 10
        
        valor = min(100, puntos)
        
        if valor >= 70: inter = "Alta diversidad. Gestiona un portafolio amplio."
        elif valor >= 40: inter = "Diversidad media de tokens."
        elif valor >= 15: inter = "Baja diversidad de tokens."
        else: inter = "Cartera concentrada en 1 o 2 activos principales."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _score_exploracion(self, f: FeaturesWallet) -> MetricaScoring:
        """Puntaje de exploración basado en la cantidad de wallets y contratos únicos."""
        puntos = 0
        if f.numero_wallets_interactuadas > 150: puntos += 100
        else: puntos = int(f.numero_wallets_interactuadas * 0.6)
        
        valor = min(100, puntos)
        
        if valor >= 80: inter = "Nivel de exploración extremadamente alto."
        elif valor >= 50: inter = "Explorador activo de la red."
        elif valor >= 20: inter = "Exploración moderada interactuando con varias contrapartes."
        else: inter = "Círculo cerrado de interacción (actividad aislada o pocos destinos)."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _calcular_indice_web3(self, s: BehavioralScores) -> MetricaScoring:
        """Índice compuesto que resume el nivel de usuario Web3 (0-100)."""
        # Ponderación: 30% Actividad, 30% DeFi, 20% Diversidad, 20% Exploración
        indice = (
            s.activity_score.valor * 0.3 +
            s.defi_engagement.valor * 0.3 +
            s.token_diversity.valor * 0.2 +
            s.protocol_exploration.valor * 0.2
        )
        valor = min(100, int(indice))
        
        if valor >= 80: inter = "Usuario Nativo Web3 avanzado o institucional."
        elif valor >= 50: inter = "Usuario Web3 experimentado e involucrado."
        elif valor >= 20: inter = "Usuario Web3 de nivel intermedio/moderado."
        else: inter = "Usuario principiante u ocasional."
            
        return MetricaScoring(valor=valor, interpretacion=inter)
