"""Wallet classification engine based on deterministic rules."""

from dataclasses import dataclass
from typing import List

from generacion_features.extractor import FeaturesWallet


@dataclass
class PerfilWallet:
    """Classified wallet profile with type and support signals."""

    type: str
    confidence: str
    confidence_score: float
    signals: List[str]
    description: str


class ClasificadorWallet:
    """Classifies wallets into predefined profiles using rules over features."""

    # Classification thresholds
    UMBRAL_ALTA_ACTIVIDAD = 50
    UMBRAL_BAJA_ACTIVIDAD = 5
    UMBRAL_DEFI_TOKENS = 5
    UMBRAL_DEFI_CONTRATOS = 40.0
    UMBRAL_TRADER_FRECUENCIA = 2.0
    UMBRAL_TRADER_ENVIOS = 1.5
    UMBRAL_WHALE_BALANCE = 50.0

    def clasificar(self, features: FeaturesWallet) -> PerfilWallet:
        """Applies classification rules and returns the wallet profile."""
        puntajes = {
            "defi_power_user": self._evaluar_defi_power_user(features),
            "protocol_explorer": self._evaluar_protocol_explorer(features),
            "active_trader": self._evaluar_active_trader(features),
            "liquidity_provider_candidate": self._evaluar_lp_candidate(features),
            "experimental_wallet": self._evaluar_experimental(features),
            "long_term_holder": self._evaluar_long_term_holder(features),
            "high_activity_wallet": self._evaluar_alta_actividad(features),
            "low_activity_wallet": self._evaluar_baja_actividad(features),
        }

        tipo = max(puntajes, key=puntajes.get)
        puntaje_maximo = puntajes[tipo]
        senales = self._recolectar_senales(features)

        # Confidence calculation
        confidence_score = min(puntaje_maximo / 5.0, 1.0)
        confidence = "high" if confidence_score >= 0.8 else "medium" if confidence_score >= 0.5 else "low"

        description = self._generar_descripcion(tipo, features)

        return PerfilWallet(
            type=tipo,
            confidence=confidence,
            confidence_score=confidence_score,
            signals=senales,
            description=description,
        )

    def _evaluar_defi_power_user(self, f: FeaturesWallet) -> int:
        puntaje = 0
        if f.porcentaje_interacciones_contratos >= 60:
            puntaje += 2
        if f.tokens_unicos_utilizados >= 10:
            puntaje += 1
        if f.total_transacciones >= 100:
            puntaje += 1
        if f.volumen_total_transferido_eth >= 10:
            puntaje += 1
        return puntaje

    def _evaluar_protocol_explorer(self, f: FeaturesWallet) -> int:
        puntaje = 0
        if f.tokens_unicos_utilizados >= 15:
            puntaje += 2
        if f.numero_wallets_interactuadas >= 30:
            puntaje += 1
        if f.diversidad_tokens >= 0.7:
            puntaje += 1
        if f.porcentaje_interacciones_contratos >= 30:
            puntaje += 1
        return puntaje

    def _evaluar_active_trader(self, f: FeaturesWallet) -> int:
        puntaje = 0
        if f.frecuencia_transacciones_por_dia >= 3.0:
            puntaje += 2
        if f.transferencias_token_total >= 50:
            puntaje += 1
        if f.ratio_envios_vs_recepciones >= 1.2:
            puntaje += 1
        if f.volumen_total_transferido_eth >= 5.0:
            puntaje += 1
        return puntaje

    def _evaluar_lp_candidate(self, f: FeaturesWallet) -> int:
        puntaje = 0
        if f.balance_eth_actual >= 5.0:
            puntaje += 1
        if f.porcentaje_interacciones_contratos >= 50 and f.tokens_unicos_utilizados >= 5:
            puntaje += 2
        if f.ratio_envios_vs_recepciones <= 0.8:
            puntaje += 1
        return puntaje

    def _evaluar_experimental(self, f: FeaturesWallet) -> int:
        puntaje = 0
        if f.transacciones_con_error >= 5:
            puntaje += 2
        if f.porcentaje_interacciones_contratos >= 70:
            puntaje += 1
        if f.tokens_unicos_utilizados >= 10 and f.balance_eth_actual < 0.5:
            puntaje += 2
        return puntaje

    def _evaluar_long_term_holder(self, f: FeaturesWallet) -> int:
        puntaje = 0
        if f.dias_activo >= 365:
            puntaje += 2
        if f.frecuencia_transacciones_por_dia <= 0.05:
            puntaje += 1
        if f.balance_eth_actual >= 1.0:
            puntaje += 1
        if f.porcentaje_transacciones_recientes <= 10:
            puntaje += 1
        return puntaje

    def _evaluar_alta_actividad(self, f: FeaturesWallet) -> int:
        puntaje = 0
        if f.total_transacciones >= self.UMBRAL_ALTA_ACTIVIDAD:
            puntaje += 2
        if f.frecuencia_transacciones_por_dia >= 1.0:
            puntaje += 1
        return puntaje

    def _evaluar_baja_actividad(self, f: FeaturesWallet) -> int:
        puntaje = 0
        if f.total_transacciones <= self.UMBRAL_BAJA_ACTIVIDAD:
            puntaje += 3
        return puntaje

    def _recolectar_senales(self, f: FeaturesWallet) -> List[str]:
        """Identifies specific behavioral signals from features."""
        senales = []
        if f.total_transacciones > 100:
            senales.append("High historical network activity")
        if f.frecuencia_transacciones_por_dia > 2:
            senales.append("Frequent daily transactions")
        if f.porcentaje_interacciones_contratos > 50:
            senales.append("Intensive protocol and smart contract usage")
        if f.tokens_unicos_utilizados > 10:
            senales.append(f"Asset diversity: {f.tokens_unicos_utilizados} tokens detected")
        if f.volumen_total_transferido_eth > 10:
            senales.append("Significant ETH volume movements")
        if f.porcentaje_transacciones_recientes > 50:
            senales.append("High recent activity (last 30 days)")
        if f.transacciones_con_error > 5:
            senales.append("Presence of failed transactions")
        if f.dias_activo > 365:
            senales.append("Veteran wallet (active for more than 1 year)")
        
        return senales

    def _generar_descripcion(self, tipo: str, f: FeaturesWallet) -> str:
        """Generates a brief description of the classified profile."""
        descripciones = {
            "defi_power_user": "Advanced DeFi protocol user with high smart contract interaction.",
            "protocol_explorer": "Protocol explorer with high token diversity and interactions.",
            "active_trader": "Active trader with high transaction frequency and movement volume.",
            "liquidity_provider_candidate": "Liquidity provider candidate with stable balance and DeFi usage.",
            "experimental_wallet": "Experimental wallet with high error rate and contract exploration.",
            "long_term_holder": "Long term holder with low recent activity and significant balance.",
            "high_activity_wallet": f"High activity wallet with {f.total_transacciones} transactions.",
            "low_activity_wallet": "Wallet with minimal or almost null activity.",
        }
        return descripciones.get(tipo, "Behavioral profile not determined.")
