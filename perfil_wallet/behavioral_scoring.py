"""Behavioral scoring engine for Ethereum wallet profiles."""

from dataclasses import dataclass
from generacion_features.extractor import FeaturesWallet

class MetricaScoring:
    """Mandatory structure for each dashboard metric."""
    def __init__(self, valor: int = 0, interpretacion: str = ""):
        self.valor = valor
        self.interpretacion = interpretacion

@dataclass
class BehavioralScores:
    """Set of scores regarding wallet behavior."""
    activity_score: MetricaScoring
    risk_score: MetricaScoring
    defi_engagement: MetricaScoring
    token_diversity: MetricaScoring
    protocol_exploration: MetricaScoring
    web3_activity_index: MetricaScoring # New Web3 activity index

class BehavioralScorer:
    """Calculates numerical scores based on on-chain features."""

    def calcular_scores(self, f: FeaturesWallet) -> BehavioralScores:
        scores = BehavioralScores(
            activity_score=self._score_actividad(f),
            risk_score=self._score_riesgo(f),
            defi_engagement=self._score_defi(f),
            token_diversity=self._score_diversidad(f),
            protocol_exploration=self._score_exploracion(f),
            web3_activity_index=MetricaScoring(0, "") # Will be calculated below
        )
        
        # Web3 activity index is a weighted combination of other scores
        scores.web3_activity_index = self._calcular_indice_web3(scores)
        
        return scores

    def _score_actividad(self, f: FeaturesWallet) -> MetricaScoring:
        """Activity score based on volume and transaction frequency."""
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
        
        if valor >= 80: inter = "Very high activity. Intensive profile."
        elif valor >= 50: inter = "Moderate to high activity."
        elif valor >= 20: inter = "Regular network activity."
        else: inter = "Low or sporadic activity."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _score_riesgo(self, f: FeaturesWallet) -> MetricaScoring:
        """Risk estimation based on errors and anomalous patterns."""
        puntos = 0
        if f.transacciones_con_error > 20: puntos += 40
        elif f.transacciones_con_error > 5: puntos += 20
        
        if f.ratio_envios_vs_recepciones > 20: puntos += 30
        if f.dias_activo < 30: puntos += 30 # Young wallets are riskier
        
        valor = min(100, puntos)
        
        if valor >= 70: inter = "High risk. Unusual patterns or many errors."
        elif valor >= 40: inter = "Moderate risk."
        elif valor >= 20: inter = "Low risk."
        else: inter = "Very low risk. Conservative profile."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _score_defi(self, f: FeaturesWallet) -> MetricaScoring:
        """Score for interaction with DeFi protocols and smart contracts."""
        valor = min(100, int(f.porcentaje_interacciones_contratos))
        
        if valor >= 80: inter = "Fully immersed in DeFi protocols/Smart Contracts."
        elif valor >= 50: inter = "Strong interaction with protocols."
        elif valor >= 20: inter = "Moderate use of decentralized applications."
        else: inter = "Low contract interaction, mainly used for transfers."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _score_diversidad(self, f: FeaturesWallet) -> MetricaScoring:
        """Score for diversity of tokens used on the network."""
        puntos = int(f.diversidad_tokens * 80)
        if f.tokens_unicos_utilizados > 20: puntos += 20
        elif f.tokens_unicos_utilizados > 5: puntos += 10
        
        valor = min(100, puntos)
        
        if valor >= 70: inter = "High diversity. Manages a broad portfolio."
        elif valor >= 40: inter = "Medium token diversity."
        elif valor >= 15: inter = "Low token diversity."
        else: inter = "Wallet concentrated in 1 or 2 main assets."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _score_exploracion(self, f: FeaturesWallet) -> MetricaScoring:
        """Exploration score based on unique wallets and contracts."""
        puntos = 0
        if f.numero_wallets_interactuadas > 150: puntos += 100
        else: puntos = int(f.numero_wallets_interactuadas * 0.6)
        
        valor = min(100, puntos)
        
        if valor >= 80: inter = "Extremely high exploration level."
        elif valor >= 50: inter = "Active network explorer."
        elif valor >= 20: inter = "Moderate exploration interacting with several counterparties."
        else: inter = "Closed interaction circle (isolated activity or few destinations)."
            
        return MetricaScoring(valor=valor, interpretacion=inter)

    def _calcular_indice_web3(self, s: BehavioralScores) -> MetricaScoring:
        """Composite index summarizing Web3 user level (0-100)."""
        # Weighting: 30% Activity, 30% DeFi, 20% Diversity, 20% Exploration
        indice = (
            s.activity_score.valor * 0.3 +
            s.defi_engagement.valor * 0.3 +
            s.token_diversity.valor * 0.2 +
            s.protocol_exploration.valor * 0.2
        )
        valor = min(100, int(indice))
        
        if valor >= 80: inter = "Advanced Web3 Native or Institutional user."
        elif valor >= 50: inter = "Experienced and involved Web3 user."
        elif valor >= 20: inter = "Intermediate/moderate level Web3 user."
        else: inter = "Beginner or occasional user."
            
        return MetricaScoring(valor=valor, interpretacion=inter)
