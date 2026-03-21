import time
from typing import Tuple, Optional
from loguru import logger
from .models import ExecutionPlan, ExecutionLifecycle, ActionStatus
from .persistence import PersistenceManager
from infra.config import settings

class ExecutionGuard:
    """Validates execution plans against safety and financial rules."""

    def __init__(self):
        self.persistence = PersistenceManager()

    def validate_plan(self, plan: ExecutionPlan, current_state: dict) -> Tuple[bool, str]:
        """
        Validates a plan against all safety rules.
        current_state should contain: nonce, balance, current_risk_score
        """
        try:
            # 1. Idempotency Check
            existing_plan = self.persistence.load_plan(plan.fingerprint)
            if existing_plan:
                if existing_plan.lifecycle == ExecutionLifecycle.COMPLETED:
                    return False, f"Plan with fingerprint {plan.fingerprint[:10]} already executed."
                if existing_plan.lifecycle == ExecutionLifecycle.EXECUTING:
                    now = time.time()
                    if existing_plan.expires_at and now > existing_plan.expires_at:
                        existing_plan.lifecycle = ExecutionLifecycle.ABORTED
                        self.persistence.save_plan(existing_plan)
                    else:
                        return False, f"Plan with fingerprint {plan.fingerprint[:10]} already executing."

            # 2. Cooldown Check
            # (Simplified: check if any plan for this wallet was completed in the last COOLDOWN_BLOCKS)
            # In a real system, we'd check blockchain events or a more robust history.
            all_plans = self.persistence.get_all_plans()
            cooldown_period = getattr(settings, "COOLDOWN_SECONDS", 300) # 5 mins cooldown
            for p in all_plans:
                if p.wallet.lower() == plan.wallet.lower() and \
                   p.lifecycle == ExecutionLifecycle.COMPLETED and \
                   (time.time() - p.created_at) < cooldown_period:
                    return False, f"Wallet {plan.wallet[:10]} is in cooldown."

            # 3. Nonce Integrity
            if current_state.get("nonce") != plan.context.pre_state.get("nonce"):
                return False, f"Nonce mismatch: expected {plan.context.pre_state.get('nonce')}, got {current_state.get('nonce')}. Plan regeneration required."

            # 4. Capital Protection
            total_value_wei = sum(a.params.get("value_wei", 0) for a in plan.actions)
            # Rough estimate: 0.01 ETH gas per action max
            estimated_gas_eth = len(plan.actions) * 0.01
            total_exposure_eth = (total_value_wei / 1e18) + estimated_gas_eth
            
            max_exposure = plan.context.max_exposure_per_execution or getattr(settings, "MAX_EXPOSURE_ETH", 0.5)
            if total_exposure_eth > max_exposure:
                return False, f"Exposure {total_exposure_eth:.4f} ETH exceeds limit {max_exposure} ETH."

            # 5. Risk Re-check
            if current_state.get("current_risk_score", 100) < plan.risk_score:
                # If risk dropped significantly (e.g., > 10 points), abort
                if plan.risk_score - current_state.get("current_risk_score", 100) > 10:
                    return False, f"Risk score dropped from {plan.risk_score} to {current_state.get('current_risk_score')}. Aborting."

            # 6. Strict Simulation Policy (in Production)
            if settings.APP_ENV == "production":
                # This would ideally call a WDK dry-run or Tenderly simulation
                # For now, we ensure the simulation_policy is respected.
                if plan.context.simulation_policy == "STRICT" and not current_state.get("simulation_success", False):
                    return False, "Strict simulation policy active, but no successful simulation was provided."

            return True, "Validation successful."

        except Exception as e:
            logger.error(f"Guard validation error: {e}")
            return False, f"Guard internal error: {str(e)}"

    def create_plan(self, wallet: str, actions_data: list, risk_score: int, block_number: int, nonce: int, balance: float) -> ExecutionPlan:
        """Helper to create a new plan with current state snapshot."""
        from .models import PlannedAction, ExecutionContext, ExecutionMode
        
        actions = [
            PlannedAction(action_id=i, type=a["type"], params=a["params"])
            for i, a in enumerate(actions_data)
        ]
        
        context = ExecutionContext(
            pre_state={
                "nonce": nonce,
                "balance": balance,
                "block_number": block_number
            },
            max_exposure_per_execution=getattr(settings, "MAX_EXPOSURE_ETH", 0.5),
            execution_mode=ExecutionMode.ATOMIC
        )
        
        return ExecutionPlan(
            wallet=wallet,
            actions=actions,
            risk_score=risk_score,
            block_number=block_number,
            context=context
        )
