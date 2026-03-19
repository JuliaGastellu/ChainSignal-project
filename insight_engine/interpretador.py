"""Motor de insight para generar resúmenes ejecutivos interpretables."""

from dataclasses import dataclass
from generacion_features.extractor import FeaturesWallet
from perfil_wallet.clasificador import PerfilWallet

@dataclass
class ResumenEjecutivo:
    """Estructura de salida del resumen ejecutivo para el dashboard."""
    tipo_usuario: str
    actividad: str
    riesgo: str
    exploracion: str
    confianza: str

class InterpretadorInsight:
    """
    Traduce las métricas técnicas, scores y perfiles crudos en una
    etiqueta narrativa amigable para mostrar en el 'Resumen Ejecutivo'.
    """

    def generar_resumen(self, features: FeaturesWallet, perfil: PerfilWallet, scores) -> ResumenEjecutivo:
        """
        Interpreta los números en atributos narrativos estandarizados.
        """
        # 1. Tipo de usuario (Narrativo corto)
        tipo = self._formatear_tipo(perfil.tipo)

        # 2. Nivel de Actividad (Texto descriptivo: "Baja", "Media", "Alta")
        actividad = self._interpretar_nivel(scores.activity_score.valor)

        # 3. Nivel de Riesgo
        riesgo = self._interpretar_nivel(scores.risk_score.valor)

        # 4. Nivel de Exploración
        exploracion = self._interpretar_nivel(scores.protocol_exploration.valor)

        # 5. Confianza
        confianza = f"{perfil.score_confianza * 100:.0f}%"

        return ResumenEjecutivo(
            tipo_usuario=tipo,
            actividad=actividad,
            riesgo=riesgo,
            exploracion=exploracion,
            confianza=confianza
        )

    def _interpretar_nivel(self, valor: int) -> str:
        """Convierte (0-100) en etiqueta textual (Baja, Media, Alta)."""
        if valor < 33:
            return "Baja"
        elif valor < 66:
            return "Media"
        else:
            return "Alta"

    def _formatear_tipo(self, tipo_raw: str) -> str:
        """Convierte 'protocol_explorer' en 'Explorador de Protocolos'."""
        formato = {
            "trader": "Trader Frecuente",
            "protocol_explorer": "Explorador de Protocolos",
            "defi_user": "Usuario DeFi",
            "high_activity_wallet": "Ballena / Alta Actividad",
            "low_activity_wallet": "Wallet de Baja Actividad",
            "passive_holder": "Holder Pasivo",
            "new_wallet": "Wallet Nueva",
            "bot": "Bot Sistemático"
        }
        return formato.get(tipo_raw, "Desconocido")
