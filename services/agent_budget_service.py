import time
from typing import Any, Dict, List, Optional

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from web3 import Web3

from infra.config import settings
from infra.red import SEPOLIA
from infra.db import engine as default_engine
from infra.db import get_session_factory, init_db
from infra.db_models import AgentBudgetRecord, BudgetConsumptionRecord, ProcessedFundingTxRecord


class AgentBudgetService:
    """Persisto presupuestos y transacciones de fondeo procesadas en la base
    (infra/db.py) en lugar de storage/agent_budget.json, para que saldos y
    deduplicación sobrevivan un reinicio.

    get_effective_balance_eth sigue leyendo solo la fila de la wallet pedida y
    nunca usa el saldo on-chain total de la wallet compartida del agente.
    """

    def __init__(self, engine_: Optional[Engine] = None):
        self._engine = engine_ or default_engine
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)
        self.w3 = Web3(Web3.HTTPProvider(settings.SEPOLIA_RPC_URL)) if settings.SEPOLIA_RPC_URL else None

    @staticmethod
    def _record_to_dict(record: AgentBudgetRecord) -> Dict[str, Any]:
        return {
            "wallet": record.wallet,
            "agent_wallet": record.agent_wallet,
            "balance_eth": record.balance_eth,
            "spent_eth": record.spent_eth,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "last_funding_tx": record.last_funding_tx,
            "last_funding_amount_eth": record.last_funding_amount_eth,
        }

    def get_budget(self, wallet: str) -> Dict[str, Any]:
        key = wallet.lower()
        with self._Session() as session:
            record = session.get(AgentBudgetRecord, key)
            if record is None:
                return {
                    "wallet": key,
                    "agent_wallet": settings.X402_PAYMENT_RECIPIENT,
                    "balance_eth": 0.0,
                    "spent_eth": 0.0,
                    "created_at": None,
                    "updated_at": None,
                    "last_funding_tx": None,
                    "last_funding_amount_eth": 0.0,
                }
            return self._record_to_dict(record)

    def get_effective_balance_eth(self, wallet: str) -> float:
        """Returns this wallet's own ledgered budget only.

        Nunca debo caer en el saldo on-chain total de la wallet compartida del
        agente. La versión anterior devolvía max(saldo_guardado, saldo_onchain)
        y, como el saldo on-chain es el mismo para todas, cualquier wallet
        parecía fondeada apenas otro cliente fondeaba la compartida: una fuga
        entre clientes. Para visibilidad operativa uso
        get_agent_wallet_onchain_balance_eth(), nunca para habilitar gasto.
        """
        return float(self.get_budget(wallet).get("balance_eth", 0.0))

    def get_agent_wallet_onchain_balance_eth(self) -> Optional[float]:
        """Solo para visibilidad operativa: saldo on-chain total de la wallet
        compartida del agente. Nunca lo uso como saldo efectivo de una wallet
        (ver get_effective_balance_eth)."""
        if not self.w3 or not self.w3.is_connected():
            return None
        try:
            onchain_wei = self.w3.eth.get_balance(settings.X402_PAYMENT_RECIPIENT)
            return float(self.w3.from_wei(onchain_wei, "ether"))
        except Exception:
            return None

    def consume(self, wallet: str, amount_eth: float, fingerprint: Optional[str] = None) -> None:
        """Deducts amount_eth from wallet's ledgered budget.

        Si recibo `fingerprint` (el plan al que pertenece el consumo), la
        llamada es idempotente por fingerprint: un segundo consume() del mismo
        plan no descuenta dos veces. Lo dejo opcional solo por compatibilidad;
        los llamados de producción siempre deben pasarlo.
        """
        if amount_eth <= 0:
            return
        key = wallet.lower()
        with self._Session() as session:
            if fingerprint:
                already_consumed = session.get(BudgetConsumptionRecord, fingerprint)
                if already_consumed is not None:
                    return

            record = session.get(AgentBudgetRecord, key)
            if record is None:
                record = AgentBudgetRecord(
                    wallet=key,
                    agent_wallet=settings.X402_PAYMENT_RECIPIENT,
                    balance_eth=0.0,
                    spent_eth=0.0,
                    last_funding_amount_eth=0.0,
                )
                session.add(record)
            record.balance_eth = max(0.0, float(record.balance_eth or 0.0) - float(amount_eth))
            record.spent_eth = float(record.spent_eth or 0.0) + float(amount_eth)
            record.updated_at = time.time()

            if fingerprint:
                session.add(
                    BudgetConsumptionRecord(
                        fingerprint=fingerprint,
                        wallet=key,
                        amount_eth=float(amount_eth),
                        timestamp=time.time(),
                    )
                )
                try:
                    session.commit()
                except IntegrityError:
                    # Otro consume() concurrente del mismo fingerprint confirmó
                    # primero: este descuento no debe aplicarse, así que revierto
                    # todo en lugar de dejar el saldo a medio cambiar.
                    session.rollback()
                return

            session.commit()

    def verify_and_fund(self, wallet: str, tx_hash: str) -> Dict[str, Any]:
        if not tx_hash or not tx_hash.startswith("0x"):
            return {"ok": False, "message": "Invalid tx hash format."}
        if not self.w3 or not self.w3.is_connected():
            return {"ok": False, "message": "RPC unavailable for on-chain verification."}

        try:
            with self._Session() as session:
                processed = session.get(ProcessedFundingTxRecord, tx_hash)
                if processed is not None:
                    item = self.get_budget(wallet)
                    return {
                        "ok": True,
                        "message": "Funding tx already registered.",
                        "budget": item,
                        "funded_eth": float(processed.funded_eth),
                    }

            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            tx = self.w3.eth.get_transaction(tx_hash)
            if not receipt or receipt.get("status") != 1:
                return {"ok": False, "message": "Transaction failed or not found."}
            to_addr = (tx.get("to") or "").lower()
            expected = settings.X402_PAYMENT_RECIPIENT.lower()
            if to_addr != expected:
                return {"ok": False, "message": "Transaction recipient does not match agent wallet."}
            value_wei = int(tx.get("value") or 0)
            if value_wei <= 0:
                return {"ok": False, "message": "Transaction has zero ETH value."}

            funded_eth = float(self.w3.from_wei(value_wei, "ether"))
            key = wallet.lower()
            now = time.time()
            with self._Session() as session:
                record = session.get(AgentBudgetRecord, key)
                if record is None:
                    record = AgentBudgetRecord(
                        wallet=key,
                        agent_wallet=settings.X402_PAYMENT_RECIPIENT,
                        balance_eth=0.0,
                        spent_eth=0.0,
                        created_at=now,
                        last_funding_amount_eth=0.0,
                    )
                    session.add(record)
                record.balance_eth = float(record.balance_eth or 0.0) + funded_eth
                if not record.created_at:
                    record.created_at = now
                record.updated_at = now
                record.last_funding_tx = tx_hash
                record.last_funding_amount_eth = funded_eth
                session.add(
                    ProcessedFundingTxRecord(tx_hash=tx_hash, wallet=key, funded_eth=funded_eth, timestamp=now)
                )
                session.commit()
                item = self._record_to_dict(record)
            return {"ok": True, "message": "Agent budget funded.", "budget": item, "funded_eth": funded_eth}
        except Exception as e:
            return {"ok": False, "message": f"Funding verification error: {e}"}

    def get_recent_funding_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._Session() as session:
            records = (
                session.query(AgentBudgetRecord)
                .filter(AgentBudgetRecord.last_funding_tx.isnot(None))
                .all()
            )
            events: List[Dict[str, Any]] = []
            for item in records:
                if not item.last_funding_tx or not item.updated_at:
                    continue
                amount = float(item.last_funding_amount_eth or 0.0)
                events.append(
                    {
                        "wallet": item.wallet,
                        "timestamp": item.updated_at,
                        "type": "FUNDING",
                        "status": "SUCCESS",
                        "tx_hash": item.last_funding_tx,
                        "value_moved_eth": amount,
                        "reason": f"Funding received: +{amount} ETH",
                        "strategy": "FUNDING",
                        "simulated": False,
                        "explorer": SEPOLIA.url_tx(item.last_funding_tx),
                    }
                )
        events_sorted = sorted(events, key=lambda e: float(e.get("timestamp") or 0.0), reverse=True)
        return events_sorted[:limit]

    def get_global_state(self) -> Dict[str, Any]:
        with self._Session() as session:
            records = session.query(AgentBudgetRecord).all()
            total_balance = 0.0
            total_spent = 0.0
            funded_wallets = 0
            for item in records:
                bal = float(item.balance_eth or 0.0)
                spent = float(item.spent_eth or 0.0)
                total_balance += bal
                total_spent += spent
                if bal > 0:
                    funded_wallets += 1
        return {
            "agent_wallet": settings.X402_PAYMENT_RECIPIENT,
            "funded_wallets": funded_wallets,
            "total_balance_eth": round(total_balance, 8),
            "total_spent_eth": round(total_spent, 8),
        }
