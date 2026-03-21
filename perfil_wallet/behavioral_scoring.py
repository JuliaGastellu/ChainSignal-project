"""Behavioral scoring engine for Ethereum wallet profiles."""

from dataclasses import dataclass
from generacion_features.extractor import FeaturesWallet

class MetricaScoring:
    """Mandatory structure for each dashboard metric."""
    def __init__(self, value: int = 0, interpretation: str = ""):
        self.value = value
        self.interpretation = interpretation

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

    def get_risk_breakdown(self, f: FeaturesWallet) -> list[dict]:
        """Provides a detailed list of risk factors found."""
        breakdown = []
        if f.transacciones_con_error > 10:
            breakdown.append({
                "factor": "High Error Rate",
                "severity": "high" if f.transacciones_con_error > 20 else "medium",
                "detail": f"Detected {f.transacciones_con_error} failed transactions, which may indicate interaction with malicious or broken contracts."
            })
        
        if f.ratio_envios_vs_recepciones > 10:
            breakdown.append({
                "factor": "Aggressive Outflow",
                "severity": "medium",
                "detail": "High frequency of outgoing transfers compared to receipts. Common in automated trading or fund drainage."
            })
            
        if f.dias_activo < 30:
            breakdown.append({
                "factor": "Young Wallet",
                "severity": "medium",
                "detail": f"Wallet is only {f.dias_activo} days old. Young wallets have less established behavioral history."
            })
            
        if f.porcentaje_interacciones_contratos < 5:
            breakdown.append({
                "factor": "Low Contract Interaction",
                "severity": "low",
                "detail": "Mostly simple transfers. Limited interaction with verified DeFi protocols."
            })

        if not breakdown:
            breakdown.append({
                "factor": "Clean History",
                "severity": "none",
                "detail": "No significant risk factors detected in the analyzed period."
            })
            
        return breakdown

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
            
        return MetricaScoring(value=valor, interpretation=inter)

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
            
        return MetricaScoring(value=valor, interpretation=inter)

    def _score_defi(self, f: FeaturesWallet) -> MetricaScoring:
        """Score for interaction with DeFi protocols and smart contracts."""
        valor = min(100, int(f.porcentaje_interacciones_contratos))
        
        if valor >= 80: inter = "Fully immersed in DeFi protocols/Smart Contracts."
        elif valor >= 50: inter = "Strong interaction with protocols."
        elif valor >= 20: inter = "Moderate use of decentralized applications."
        else: inter = "Low contract interaction, mainly used for transfers."
            
        return MetricaScoring(value=valor, interpretation=inter)

    def _score_diversidad(self, f: FeaturesWallet) -> MetricaScoring:
        """Score for diversity of tokens used on the network."""
        puntos = int(f.diversidad_tokens * 80)
        if f.tokens_unicos_utilizados > 20: puntos += 20
        elif f.tokens_unicos_utilizados > 5: puntos += 10
        
        valor = min(100, puntos)
        
        if valor >= 70: inter = "High diversity. Manages a broad portfolio."
        elif valor >= 40: inter = "Moderate token diversity."
        elif valor >= 10: inter = "Regular network interaction with tokens."
        else: inter = "Low token variety; mostly uses ETH or a few tokens."
        
        return MetricaScoring(value=valor, interpretation=inter)

    def _score_exploracion(self, f: FeaturesWallet) -> MetricaScoring:
        """Score for protocol exploration and discovery."""
        # Safety check for the attribute
        div = getattr(f, "diversidad_protocolos", 0.0)
        valor = min(100, int(div * 100))
        
        if valor >= 80: inter = "Early adopter. Actively interacts with multiple protocols."
        elif valor >= 50: inter = "Protocol explorer; interacts with diverse DApps."
        elif valor >= 20: inter = "Moderate protocol interaction."
        else: inter = "Low protocol interaction; focused on basic transfers."
        
        return MetricaScoring(value=valor, interpretation=inter)

    def _calcular_indice_web3(self, scores: BehavioralScores) -> MetricaScoring:
        """Web3 Activity Index (normalized 0-100) based on multiple behavior metrics."""
        # Weigh activity, defi, diversity and exploration for the global index
        weighted_score = (
            (scores.activity_score.value * 0.4) +
            (scores.defi_engagement.value * 0.3) +
            (scores.token_diversity.value * 0.15) +
            (scores.protocol_exploration.value * 0.15)
        )
        
        valor = min(100, int(weighted_score))
        
        if valor >= 80: inter = "Expert Web3 user. High participation across all sectors."
        elif valor >= 50: inter = "Advanced user with stable activity."
        elif valor >= 25: inter = "Emerging user. Growing participation."
        else: inter = "Sporadic user. Low impact in the ecosystem."
        
        return MetricaScoring(value=valor, interpretation=inter)
