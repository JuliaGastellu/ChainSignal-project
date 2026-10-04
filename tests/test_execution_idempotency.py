"""Pruebas de idempotencia respaldada por la base.

PersistenceManager.try_claim_plan() es la operación que decide si alguien puede
empezar a ejecutar un fingerprint. Antes la idempotencia dependía de una
lectura optimista en ExecutionGuard.validate_plan() y de un lock en archivo
que solo protege llamadas del mismo host. Pruebo ese método y la idempotencia
por fingerprint de AgentBudgetService.consume().

La carrera concurrente la certifico solo contra PostgreSQL
(CHAINSIGNAL_TEST_POSTGRES_URL); SQLite no demuestra aislamiento real.
"""

import os
import threading
import uuid

import pytest

from execution_guard.models import ExecutionContext, ExecutionLifecycle, ExecutionPlan, PlannedAction
from execution_guard.persistence import PersistenceManager
from infra.db import init_db, make_engine
from services.agent_budget_service import AgentBudgetService

WALLET = "0xabc0000000000000000000000000000000000a"


def _sqlite_url(tmp_path, name: str) -> str:
    return f"sqlite:///{tmp_path / name}"


def _make_plan(wallet=WALLET, block_number=100):
    return ExecutionPlan(
        wallet=wallet,
        actions=[PlannedAction(action_id=0, type="TRANSFER", params={"to": "0xdef", "value_wei": 1})],
        risk_score=80,
        block_number=block_number,
        context=ExecutionContext(pre_state={"nonce": 1, "balance": 1.0, "block_number": block_number}),
    )


# --- PersistenceManager.try_claim_plan --------------------------------------


def test_try_claim_plan_succeeds_for_a_brand_new_fingerprint(tmp_path):
    engine = make_engine(_sqlite_url(tmp_path, "claim_new.db"))
    init_db(engine)
    pm = PersistenceManager(engine_=engine)

    plan = _make_plan()
    claimed, reason = pm.try_claim_plan(plan)
    assert claimed is True
    assert reason == ""

    loaded = pm.load_plan(plan.fingerprint)
    assert loaded.lifecycle == ExecutionLifecycle.EXECUTING


def test_try_claim_plan_rejects_a_second_claim_while_active(tmp_path):
    engine = make_engine(_sqlite_url(tmp_path, "claim_active.db"))
    init_db(engine)
    pm = PersistenceManager(engine_=engine)

    plan = _make_plan()
    first_claim, _ = pm.try_claim_plan(plan)
    assert first_claim is True

    # Same fingerprint, still EXECUTING - a second claim attempt (e.g. a
    # retried/duplicated request for the identical plan) must be rejected.
    second_claim, reason = pm.try_claim_plan(plan)
    assert second_claim is False
    assert "already active" in reason


def test_try_claim_plan_rejects_reclaiming_a_completed_plan(tmp_path):
    engine = make_engine(_sqlite_url(tmp_path, "claim_completed.db"))
    init_db(engine)
    pm = PersistenceManager(engine_=engine)

    plan = _make_plan()
    pm.try_claim_plan(plan)
    plan.lifecycle = ExecutionLifecycle.COMPLETED
    pm.save_plan(plan)

    claimed_again, reason = pm.try_claim_plan(plan)
    assert claimed_again is False
    assert "already completed" in reason


def test_try_claim_plan_allows_retry_of_a_failed_plan(tmp_path):
    engine = make_engine(_sqlite_url(tmp_path, "claim_retry.db"))
    init_db(engine)
    pm = PersistenceManager(engine_=engine)

    plan = _make_plan()
    pm.try_claim_plan(plan)
    plan.lifecycle = ExecutionLifecycle.FAILED
    pm.save_plan(plan)

    # A retry of a previously-failed plan is legitimate (matches the retry
    # policy already applied in ExecutionGuard.validate_plan) and must be
    # allowed to reclaim the same fingerprint.
    retried, reason = pm.try_claim_plan(plan)
    assert retried is True
    assert reason == ""
    assert pm.load_plan(plan.fingerprint).lifecycle == ExecutionLifecycle.EXECUTING


@pytest.mark.postgres
def test_concurrent_claim_for_the_same_fingerprint_only_one_wins():
    """Dos llamadas compiten por el mismo fingerprint casi al mismo tiempo:
    exactamente una debe ganar, sin importar si la carrera se resuelve por
    conflicto de INSERT o por leer una fila ya activa."""
    db_url = os.getenv("CHAINSIGNAL_TEST_POSTGRES_URL", "")
    if not db_url:
        pytest.skip("Definí CHAINSIGNAL_TEST_POSTGRES_URL con un PostgreSQL desechable")

    engine = make_engine(db_url)
    init_db(engine)

    # Wallet única por corrida para no chocar con filas de corridas previas.
    plan = _make_plan(wallet="0x" + uuid.uuid4().hex[:40])
    results = []
    barrier = threading.Barrier(2)

    def attempt():
        # Cada hilo usa su propio engine, como dos procesos independientes.
        pm = PersistenceManager(engine_=make_engine(db_url))
        barrier.wait()
        claimed, _ = pm.try_claim_plan(plan)
        results.append(claimed)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [False, True]


# --- AgentBudgetService.consume() idempotency --------------------------------


def _budget_service(tmp_path):
    engine = make_engine(_sqlite_url(tmp_path, "budget_idempotent.db"))
    init_db(engine)
    return AgentBudgetService(engine_=engine)


def test_consume_with_fingerprint_only_deducts_once(tmp_path):
    svc = _budget_service(tmp_path)
    with svc._Session() as session:
        from infra.db_models import AgentBudgetRecord

        session.add(AgentBudgetRecord(wallet=WALLET, balance_eth=5.0, spent_eth=0.0))
        session.commit()

    fingerprint = "fp-same-intent"
    svc.consume(WALLET, 1.0, fingerprint=fingerprint)
    svc.consume(WALLET, 1.0, fingerprint=fingerprint)  # e.g. a retried call path

    # Only the first call should have taken effect.
    assert svc.get_effective_balance_eth(WALLET) == 4.0


def test_consume_with_different_fingerprints_deducts_each_time(tmp_path):
    svc = _budget_service(tmp_path)
    with svc._Session() as session:
        from infra.db_models import AgentBudgetRecord

        session.add(AgentBudgetRecord(wallet=WALLET, balance_eth=5.0, spent_eth=0.0))
        session.commit()

    svc.consume(WALLET, 1.0, fingerprint="fp-one")
    svc.consume(WALLET, 1.0, fingerprint="fp-two")

    assert svc.get_effective_balance_eth(WALLET) == 3.0
