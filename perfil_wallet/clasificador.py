"""Motor de clasificación de wallets basado en reglas deterministas."""

from dataclasses import dataclass
from typing import List

from generacion_features.extractor import FeaturesWallet


@dataclass
class PerfilWallet:
    """Perfil clasificado de una wallet con tipo y señales de soporte."""

    tipo: str
    confianza: str
    score_confianza: float
    senales: List[str]
    descripcion: str


class ClasificadorWallet:
    """Clasifica wallets en perfiles predefinidos usando reglas sobre las features."""

    # Umbrales de clasificación
    UMBRAL_ALTA_ACTIVIDAD = 50
    UMBRAL_BAJA_ACTIVIDAD = 5
    UMBRAL_DEFI_TOKENS = 5
    UMBRAL_DEFI_CONTRATOS = 40.0
    UMBRAL_TRADER_FRECUENCIA = 2.0
    UMBRAL_TRADER_ENVIOS = 1.5
    UMBRAL_WHALE_BALANCE = 50.0

    def clasificar(self, features: FeaturesWallet) -> PerfilWallet:
        """Aplica las reglas de clasificación y retorna el perfil de la wallet."""
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

        # Cálculo de confianza
        score_confianza = min(puntaje_maximo / 5.0, 1.0)
        confianza = "alta" if score_confianza >= 0.8 else "media" if score_confianza >= 0.5 else "baja"

        descripcion = self._generar_descripcion(tipo, features)

        return PerfilWallet(
            tipo=tipo,
            confianza=confianza,
            score_confianza=score_confianza,
            senales=senales,
            descripcion=descripcion,
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
        """Identifica señales conductuales específicas a partir de las features."""
        senales = []
        if f.total_transacciones > 100:
            senales.append("Alta actividad histórica en la red")
        if f.frecuencia_transacciones_por_dia > 2:
            senales.append("Transacciones frecuentes diarias")
        if f.porcentaje_interacciones_contratos > 50:
            senales.append("Uso intensivo de protocolos y smart contracts")
        if f.tokens_unicos_utilizados > 10:
            senales.append(f"Diversidad de activos: {f.tokens_unicos_utilizados} tokens detectados")
        if f.volumen_total_transferido_eth > 10:
            senales.append("Movimientos de volumen significativo de ETH")
        if f.porcentaje_transacciones_recientes > 50:
            senales.append("Actividad reciente muy alta (últimos 30 días)")
        if f.transacciones_con_error > 5:
            senales.append("Presencia de transacciones fallidas")
        if f.dias_activo > 365:
            senales.append("Wallet veterana (más de 1 año activa)")
        
        return senales

    def _generar_descripcion(self, tipo: str, f: FeaturesWallet) -> str:
        """Genera una descripción breve del perfil clasificado."""
        descripciones = {
            "defi_power_user": "Usuario avanzado de protocolos DeFi con alta interaccion con smart contracts.",
            "protocol_explorer": "Explorador de protocolos con gran diversidad de tokens e interacciones.",
            "active_trader": "Trader activo con alta frecuencia de transacciones y volumen de movimiento.",
            "liquidity_provider_candidate": "Candidato a proveedor de liquidez con balance estable y uso de DeFi.",
            "experimental_wallet": "Wallet experimental con alta tasa de errores y exploracion de contratos.",
            "long_term_holder": "Holder a largo plazo con baja actividad reciente y balance significativo.",
            "high_activity_wallet": f"Wallet de alta actividad con {f.total_transacciones} transacciones.",
            "low_activity_wallet": "Wallet con actividad minima o casi nula.",
        }
        return descripciones.get(tipo, "Perfil conductual no determinado.")
