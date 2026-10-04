"""Lectura del historial de ejecuciones heredado.

Lo separo de agent_executor/executor.py para que la API de solo lectura pueda
mostrar el historial sin importar WalletAgent ni la capa de firma.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.engine import Engine

from infra.db import engine as default_engine
from infra.db import get_session_factory, init_db
from infra.db_models import ExecutionRecord


def load_execution_history(engine_: Optional[Engine] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Reads the durable execution history, most recent first.

    Reemplaza la lectura directa de executions.json. Lo comparten AgentExecutor
    y los endpoints /agent/status y /agent/history de api/main.py, así tengo un
    único lugar que sabe cómo se guarda el historial.
    """
    target = engine_ or default_engine
    init_db(target)
    session_factory = get_session_factory(target)
    with session_factory() as session:
        query = session.query(ExecutionRecord).order_by(ExecutionRecord.timestamp.desc())
        if limit:
            query = query.limit(limit)
        records = query.all()
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp,
                "cycle": r.cycle,
                "wallet": r.wallet,
                "decision": r.decision,
                "threat_score": r.threat_score,
                "action_type": r.action_type,
                "tx_hash": r.tx_hash,
                "contract_address": r.contract_address,
                "status": r.status,
                "error": r.error,
            }
            for r in records
        ]
