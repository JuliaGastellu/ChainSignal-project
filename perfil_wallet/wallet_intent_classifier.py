"""Clasificador de intención del usuario basado en patrones de transacciones."""

from enum import Enum
from generacion_features.extractor import FeaturesWallet

class WalletIntent(str, Enum):
    TRADING = "Trading"
    COLLECTION = "Colección de Activos"
    DEVELOPMENT = "Desarrollo/Contratos"
    STAKING_DEFI = "Staking & DeFi"
    PERSONAL_USE = "Uso Personal"
    UNKNOWN = "Desconocido"

class IntentClassifier:
    """Analiza las features para determinar el 'propósito' probable de la wallet."""

    def clasificar_intento(self, f: FeaturesWallet) -> WalletIntent:
        if f.porcentaje_interacciones_contratos > 70:
            return WalletIntent.DEVELOPMENT if f.volumen_total_transferido_eth < 1 else WalletIntent.STAKING_DEFI
        
        if f.tokens_unicos_utilizados > 15:
            return WalletIntent.TRADING
        
        if f.frecuencia_transacciones_por_dia < 0.1 and f.balance_eth_actual > 1:
            return WalletIntent.COLLECTION
            
        if f.total_transacciones > 0:
            return WalletIntent.PERSONAL_USE
            
        return WalletIntent.UNKNOWN
