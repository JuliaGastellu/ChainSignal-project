import datetime

class GeneradorContratos:
    """Genera código Solidity basado en insights del agente."""

    def __init__(self):
        self.pragma = "pragma solidity ^0.8.20;"
        self.license = "// SPDX-License-Identifier: MIT"

    def generar(self, insight: dict) -> str:
        """
        Genera el código fuente de un contrato inteligente.
        
        Args:
            insight: Diccionario con tipo, wallet_analizada, score_riesgo, etc.
            
        Returns:
            str: Código fuente Solidity.
        """
        tipo = insight.get("tipo")
        wallet = insight.get("wallet_analizada", "0x0000000000000000000000000000000000000000")
        riesgo = insight.get("score_riesgo", 0)
        actividad = insight.get("score_actividad", 0)
        fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        header = f"""{self.license}
{self.pragma}

/**
 * Contrato generado automáticamente por ChainSignal
 * Wallet analizada: {wallet}
 * Score de riesgo: {riesgo}
 * Fecha de generación: {fecha}
 */
"""

        if tipo == "risk_guard":
            return header + self._plantilla_risk_guard(wallet, riesgo)
        elif tipo == "signal_lock":
            return header + self._plantilla_signal_lock()
        elif tipo == "treasury_manager":
            return header + self._plantilla_treasury_manager(actividad)
        else:
            raise ValueError(f"Tipo de contrato no soportado: {tipo}")

    def _plantilla_risk_guard(self, wallet: str, riesgo: int) -> str:
        return f"""
contract RiskGuard {{
    address public owner;
    address public walletAnalizada;
    uint256 public umbralRiesgo;
    bool public pausado;

    event RiesgoDetectado(uint256 score, bool pausaActivada);

    constructor(uint256 _umbralRiesgo) {{
        owner = msg.sender;
        walletAnalizada = {wallet};
        umbralRiesgo = _umbralRiesgo;
        pausado = false;
    }}

    modifier onlyOwner() {{
        require(msg.sender == owner, "Solo el owner puede ejecutar esto");
        _;
    }}

    function actualizarPausa(uint256 scoreActual) public onlyOwner {{
        if (scoreActual > umbralRiesgo) {{
            pausado = true;
        }} else {{
            pausado = false;
        }}
        emit RiesgoDetectado(scoreActual, pausado);
    }}

    function setUmbral(uint256 nuevoUmbral) public onlyOwner {{
        umbralRiesgo = nuevoUmbral;
    }}
}}
"""

    def _plantilla_signal_lock(self) -> str:
        return """
contract SignalLock {
    address public owner;
    uint256 public desbloqueoTimestamp;

    event FondosLiberados(uint256 cantidad);

    constructor(uint256 duracionSegundos) payable {
        owner = msg.sender;
        desbloqueoTimestamp = block.timestamp + duracionSegundos;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Solo el owner puede ejecutar esto");
        _;
    }

    function liberarFondos() public onlyOwner {
        require(block.timestamp >= desbloqueoTimestamp, "El periodo de bloqueo no ha vencido");
        uint256 balance = address(this).balance;
        payable(owner).transfer(balance);
        emit FondosLiberados(balance);
    }

    receive() external payable {}
}
"""

    def _plantilla_treasury_manager(self, actividad: int) -> str:
        return f"""
contract TreasuryManager {{
    address public owner;
    uint256 public scoreActividadInicial;
    
    struct Observacion {{
        string detalle;
        uint256 timestamp;
    }}

    Observacion[] public observaciones;

    event NuevaObservacion(string detalle, uint256 timestamp);

    constructor() {{
        owner = msg.sender;
        scoreActividadInicial = {actividad};
    }}

    modifier onlyOwner() {{
        require(msg.sender == owner, "Solo el owner puede ejecutar esto");
        _;
    }}

    function registrarObservacion(string memory _detalle) public onlyOwner {{
        observaciones.push(Observacion({{
            detalle: _detalle,
            timestamp: block.timestamp
        }}));
        emit NuevaObservacion(_detalle, block.timestamp);
    }}

    function totalObservaciones() public view returns (uint256) {{
        return observaciones.length;
    }}
}}
"""
