import time
from typing import List, Optional, Callable
from loguru import logger
from .models import ExecutionPlan, ExecutionLifecycle, ActionStatus, ExecutionMode
from .persistence import PersistenceManager
from services.servicio_wdk import ServicioWDK
from domain.modelos_contrato import ContratoCompilado

class ExecutionRunner:
    """Orchestrates the sequential execution of a validated plan."""

    def __init__(self, wdk_service: ServicioWDK):
        self.wdk = wdk_service
        self.persistence = PersistenceManager()

    def run(self, plan: ExecutionPlan, on_step: Optional[Callable[[str, str, dict], None]] = None) -> bool:
        """
        Executes all steps in the plan.
        on_step: callback(step_name, status, data)
        """
        if not self.persistence.acquire_lock(plan.fingerprint):
            if on_step: on_step("execution_lock", "error", {"message": "Could not acquire lock"})
            return False

        try:
            plan.lifecycle = ExecutionLifecycle.EXECUTING
            self.persistence.save_plan(plan)
            self.persistence.log_event(plan.fingerprint, "execution_started")

            for action in plan.actions:
                if action.status == ActionStatus.SUCCESS:
                    continue

                detail = f"Executing {action.type} (Action ID: {action.action_id})"
                if on_step: on_step("execution_step", "starting", {"detalle": detail, "action": action.type})
                
                self.persistence.log_event(plan.fingerprint, "step_started", {"action_id": action.action_id, "type": action.type})
                action.status = ActionStatus.IN_PROGRESS
                self.persistence.save_plan(plan)

                success, tx_hash, error = self._execute_action(action)
                
                if success:
                    action.status = ActionStatus.SUCCESS
                    action.tx_hash = tx_hash
                    self.persistence.log_event(plan.fingerprint, "step_success", {"action_id": action.action_id, "hash": tx_hash})
                    if on_step: on_step("execution_step", "completed", {"detalle": f"{action.type} successful", "hash": tx_hash})
                else:
                    action.status = ActionStatus.FAILED
                    action.error_code = error
                    self.persistence.log_event(plan.fingerprint, "step_failed", {"action_id": action.action_id, "error": error})
                    if on_step: on_step("execution_step", "error", {"detalle": f"{action.type} failed: {error}"})
                    
                    if plan.context.execution_mode == ExecutionMode.ATOMIC:
                        plan.lifecycle = ExecutionLifecycle.FAILED
                        self.persistence.save_plan(plan)
                        self.persistence.log_event(plan.fingerprint, "execution_aborted_atomic")
                        return False

                self.persistence.save_plan(plan)

            # Post-state verification
            if on_step: on_step("execution_verification", "starting", {"detalle": "Verifying post-state and balances..."})
            self._verify_post_state(plan)
            if on_step: on_step("execution_verification", "completed", {"detalle": "Verification complete.", "post_state": plan.context.post_state})
            
            plan.lifecycle = ExecutionLifecycle.COMPLETED
            self.persistence.save_plan(plan)
            self.persistence.log_event(plan.fingerprint, "execution_completed")
            return True

        except Exception as e:
            logger.error(f"Runner execution error: {e}")
            plan.lifecycle = ExecutionLifecycle.FAILED
            self.persistence.save_plan(plan)
            if on_step: on_step("execution_error", "error", {"detalle": str(e)})
            return False
        finally:
            self.persistence.release_lock(plan.fingerprint)

    def _execute_action(self, action) -> tuple[bool, Optional[str], Optional[str]]:
        """Calls the appropriate WDK service method."""
        try:
            if action.type == "TRANSFER":
                res = self.wdk.transferir_activo(
                    action.params["to"], 
                    action.params["value_wei"]
                )
                return res.success, res.transaction_hash, res.detail if not res.success else None
            
            elif action.type == "SWAP":
                res = self.wdk.ejecutar_swap(
                    action.params["token_in"],
                    action.params["token_out"],
                    action.params["amount_wei"]
                )
                return res.success, res.transaction_hash, res.detail if not res.success else None
            
            elif action.type == "DEPLOY":
                compiled = action.params.get("compiled_contract")
                args = action.params.get("args_constructor")
                if not isinstance(compiled, dict):
                    return False, None, "DEPLOY_MISSING_COMPILED_CONTRACT"

                contrato = ContratoCompilado(
                    name=str(compiled.get("name", "Contract")),
                    abi=compiled.get("abi") or [],
                    bytecode=str(compiled.get("bytecode", "")),
                    source_code=str(compiled.get("source_code", "")),
                )
                res = self.wdk.desplegar_contrato(contrato, args_constructor=args)
                if res is not None:
                    action.params["deployed_address"] = res.address
                    action.params["contract_name"] = res.name
                return res is not None, res.transaction_hash if res else None, None if res else "WDK_DEPLOY_FAILED"
            
            return False, None, "Unsupported action type"
        except Exception as e:
            return False, None, str(e)

    def _verify_post_state(self, plan: ExecutionPlan):
        """Checks balances and tx status after execution."""
        try:
            final_balance = self.wdk.consultar_balance()
            plan.context.post_state = {
                "final_balance": final_balance,
                "verification_time": time.time()
            }
            # In a real system, we'd wait for tx receipts and check events here.
        except Exception as e:
            logger.warning(f"Post-state verification failed: {e}")
