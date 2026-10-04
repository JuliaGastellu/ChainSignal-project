"""Pruebas de durabilidad del estado en base de datos.

Planes de ejecución, historial y presupuestos vivían antes en JSON bajo
storage/ y no tenían garantía de sobrevivir una caída, un archivo escrito a
medias o un reinicio.

Verifico supervivencia a reinicios: lo que escribe una instancia debe verlo
otra instancia construida de forma independiente contra la misma base.

No pruebo aquí locking distribuido, nonce ni reconciliación tras una caída, y
estas pruebas sobre SQLite no certifican concurrencia.
"""

import asyncio

from execution_guard.models import ExecutionContext, ExecutionLifecycle, ExecutionPlan, PlannedAction
from execution_guard.persistence import PersistenceManager
from infra.db import init_db, make_engine
from agent_executor.executor import AgentExecutor, load_execution_history


def _sqlite_url(tmp_path, name: str) -> str:
    return f"sqlite:///{tmp_path / name}"


# --- ExecutionPlan persistence (execution_guard/persistence.py) -----------


def _make_plan(wallet="0xabc0000000000000000000000000000000000a", risk_score=80, block_number=100):
    return ExecutionPlan(
        wallet=wallet,
        actions=[PlannedAction(action_id=0, type="TRANSFER", params={"to": "0xdef", "value_wei": 1})],
        risk_score=risk_score,
        block_number=block_number,
        context=ExecutionContext(pre_state={"nonce": 1, "balance": 1.0, "block_number": block_number}),
    )


def test_execution_plan_survives_process_restart(tmp_path):
    db_url = _sqlite_url(tmp_path, "plans.db")
    engine1 = make_engine(db_url)
    init_db(engine1)
    pm1 = PersistenceManager(engine_=engine1)

    plan = _make_plan()
    pm1.save_plan(plan)
    pm1.log_event(plan.fingerprint, "created")

    # Simulate a restart: a brand new engine/session pointed at the same
    # database file, with no shared Python object with pm1.
    engine2 = make_engine(db_url)
    pm2 = PersistenceManager(engine_=engine2)

    loaded = pm2.load_plan(plan.fingerprint)
    assert loaded is not None
    assert loaded.wallet == plan.wallet
    assert loaded.fingerprint == plan.fingerprint
    assert loaded.lifecycle == ExecutionLifecycle.CREATED


def test_execution_plan_lifecycle_transition_is_durable(tmp_path):
    db_url = _sqlite_url(tmp_path, "plans_lifecycle.db")
    engine = make_engine(db_url)
    init_db(engine)
    pm = PersistenceManager(engine_=engine)

    plan = _make_plan()
    pm.save_plan(plan)

    plan.lifecycle = ExecutionLifecycle.COMPLETED
    pm.save_plan(plan)

    # Independent instance, same underlying database.
    pm2 = PersistenceManager(engine_=make_engine(db_url))
    reloaded = pm2.load_plan(plan.fingerprint)
    assert reloaded.lifecycle == ExecutionLifecycle.COMPLETED


def test_get_all_plans_reflects_every_saved_plan(tmp_path):
    db_url = _sqlite_url(tmp_path, "plans_all.db")
    engine = make_engine(db_url)
    init_db(engine)
    pm = PersistenceManager(engine_=engine)

    plan_a = _make_plan(wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", block_number=1)
    plan_b = _make_plan(wallet="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", block_number=2)
    pm.save_plan(plan_a)
    pm.save_plan(plan_b)

    all_plans = PersistenceManager(engine_=make_engine(db_url)).get_all_plans()
    wallets = {p.wallet for p in all_plans}
    assert wallets == {plan_a.wallet, plan_b.wallet}


def test_duplicate_fingerprint_save_upserts_not_duplicates(tmp_path):
    """Saving the same plan twice (e.g. a retried step) must update the
    existing row, not create a second one - fingerprint is the primary key."""
    db_url = _sqlite_url(tmp_path, "plans_upsert.db")
    engine = make_engine(db_url)
    init_db(engine)
    pm = PersistenceManager(engine_=engine)

    plan = _make_plan()
    pm.save_plan(plan)
    plan.lifecycle = ExecutionLifecycle.EXECUTING
    pm.save_plan(plan)  # same fingerprint, updated lifecycle

    all_plans = pm.get_all_plans()
    matching = [p for p in all_plans if p.fingerprint == plan.fingerprint]
    assert len(matching) == 1
    assert matching[0].lifecycle == ExecutionLifecycle.EXECUTING


# --- Execution history (agent_executor/executor.py) ------------------------


def test_execution_history_survives_process_restart(tmp_path, modo_experimental):
    db_url = _sqlite_url(tmp_path, "history.db")
    engine1 = make_engine(db_url)
    init_db(engine1)
    executor1 = AgentExecutor(engine_=engine1)

    executor1._append(
        {
            "id": "rec-1",
            "timestamp": executor1._now_iso(),
            "cycle": 5,
            "wallet": "0xaaa",
            "decision": "MONITOR",
            "threat_score": 0.2,
            "action_type": "transfer",
            "tx_hash": None,
            "contract_address": None,
            "status": "confirmed",
            "error": None,
        }
    )

    # Simulate restart via a fresh module-level helper + fresh engine.
    history = load_execution_history(engine_=make_engine(db_url))
    assert len(history) == 1
    assert history[0]["wallet"] == "0xaaa"
    assert history[0]["cycle"] == 5


def test_duplicate_cycle_wallet_is_rejected_after_restart(tmp_path, modo_experimental):
    """The duplicate-cycle guard in AgentExecutor.execute() must see history
    written by a prior process instance, not just the current one."""
    db_url = _sqlite_url(tmp_path, "history_dup.db")
    engine1 = make_engine(db_url)
    init_db(engine1)
    executor1 = AgentExecutor(engine_=engine1)
    executor1._append(
        {
            "id": "rec-dup",
            "timestamp": executor1._now_iso(),
            "cycle": 7,
            "wallet": "0xbbb",
            "decision": "MONITOR",
            "threat_score": 0.1,
            "action_type": "transfer",
            "tx_hash": None,
            "contract_address": None,
            "status": "confirmed",
            "error": None,
        }
    )

    # A brand new AgentExecutor instance (as a restarted process would build)
    # pointed at the same database.
    executor2 = AgentExecutor(engine_=make_engine(db_url))

    async def run():
        return await executor2.execute({"wallet": "0xBBB", "cycle": 7, "action": {"type": "transfer"}})

    result = asyncio.run(run())
    assert result == {"status": "skipped", "reason": "duplicate_cycle_wallet"}
