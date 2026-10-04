"""Pruebas de regresión de services/agent_budget_service.py.

El presupuesto efectivo de una wallet nunca debe inflarse con el saldo
on-chain de la wallet compartida del agente. Antes get_effective_balance_eth
devolvía max(saldo_guardado, saldo_onchain_compartido) y cualquier wallet
parecía fondeada apenas alguien fondeaba la compartida: una fuga entre
clientes.

El servicio guarda su estado en la base (infra/db.py); cada prueba inyecta su
propio engine SQLite descartable.
"""

from infra.db import init_db, make_engine
from infra.db_models import AgentBudgetRecord
from services.agent_budget_service import AgentBudgetService

WALLET_A = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WALLET_B = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _service(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'agent_budget_test.db'}")
    init_db(engine)
    return AgentBudgetService(engine_=engine)


def test_unfunded_wallet_has_zero_effective_balance(tmp_path):
    svc = _service(tmp_path)
    assert svc.get_effective_balance_eth(WALLET_B) == 0.0


def test_funding_wallet_a_never_credits_wallet_b(tmp_path):
    svc = _service(tmp_path)

    # Simulate wallet A having a real ledgered balance (as verify_and_fund would
    # write after a validated on-chain funding transaction).
    with svc._Session() as session:
        session.add(
            AgentBudgetRecord(
                wallet=WALLET_A,
                balance_eth=5.0,
                spent_eth=0.0,
                created_at=1,
                updated_at=1,
                last_funding_tx="0xdeadbeef",
                last_funding_amount_eth=5.0,
            )
        )
        session.commit()

    assert svc.get_effective_balance_eth(WALLET_A) == 5.0
    # Wallet B never funded anything - it must see exactly zero, regardless of
    # how much ETH the shared agent wallet holds on-chain.
    assert svc.get_effective_balance_eth(WALLET_B) == 0.0


def test_effective_balance_ignores_shared_onchain_balance_even_when_w3_mocked(tmp_path, monkeypatch):
    svc = _service(tmp_path)

    class _FakeW3:
        def is_connected(self):
            return True

        class eth:
            @staticmethod
            def get_balance(addr):
                return 10**18  # 1 ETH sitting in the shared agent wallet

        @staticmethod
        def from_wei(value, unit):
            return value / 10**18

    svc.w3 = _FakeW3()

    # Even though the shared agent wallet has 1 ETH on-chain, an unfunded wallet
    # must still show zero effective balance.
    assert svc.get_effective_balance_eth(WALLET_B) == 0.0
    # Operational visibility into the shared balance is available separately.
    assert svc.get_agent_wallet_onchain_balance_eth() == 1.0


def test_consume_only_affects_the_target_wallet(tmp_path):
    svc = _service(tmp_path)
    with svc._Session() as session:
        session.add(AgentBudgetRecord(wallet=WALLET_A, balance_eth=5.0, spent_eth=0.0))
        session.add(AgentBudgetRecord(wallet=WALLET_B, balance_eth=2.0, spent_eth=0.0))
        session.commit()

    svc.consume(WALLET_A, 1.0)

    assert svc.get_effective_balance_eth(WALLET_A) == 4.0
    assert svc.get_effective_balance_eth(WALLET_B) == 2.0


def test_budget_survives_a_new_service_instance_against_the_same_db(tmp_path):
    """Control de durabilidad: un segundo AgentBudgetService apuntado al mismo
    archivo de base (simulo un reinicio) debe ver el mismo estado contable, sin
    depender de memoria de un proceso ni de un JSON intacto."""
    db_path = tmp_path / "restart_test.db"
    engine1 = make_engine(f"sqlite:///{db_path}")
    init_db(engine1)
    svc1 = AgentBudgetService(engine_=engine1)
    with svc1._Session() as session:
        session.add(AgentBudgetRecord(wallet=WALLET_A, balance_eth=3.0, spent_eth=0.0))
        session.commit()

    # Fresh engine/service pointed at the same sqlite file, as a new process
    # would create after a restart.
    engine2 = make_engine(f"sqlite:///{db_path}")
    svc2 = AgentBudgetService(engine_=engine2)
    assert svc2.get_effective_balance_eth(WALLET_A) == 3.0
