from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional
import hashlib
import json
import time

class ExecutionLifecycle(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    FAILED = "FAILED"

class ExecutionMode(str, Enum):
    ATOMIC = "ATOMIC"
    BEST_EFFORT = "BEST_EFFORT"

class ActionStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

@dataclass
class PlannedAction:
    action_id: int
    type: str  # SWAP, TRANSFER, DEPLOY
    params: Dict[str, Any]
    status: ActionStatus = ActionStatus.PENDING
    tx_hash: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self):
        return asdict(self)

@dataclass
class ExecutionContext:
    pre_state: Dict[str, Any]  # nonce, balance, block_number
    post_state: Dict[str, Any] = field(default_factory=dict)
    max_exposure_per_execution: float = 0.0
    execution_mode: ExecutionMode = ExecutionMode.ATOMIC
    simulation_policy: str = "STRICT"

@dataclass
class ExecutionRecovery:
    retry_count: int = 0
    interrupted_at_step: Optional[int] = None
    last_tx_check: float = 0.0

@dataclass
class ExecutionPlan:
    wallet: str
    actions: List[PlannedAction]
    risk_score: int
    block_number: int
    context: ExecutionContext
    lifecycle: ExecutionLifecycle = ExecutionLifecycle.CREATED
    recovery: ExecutionRecovery = field(default_factory=ExecutionRecovery)
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    fingerprint: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = self.generate_fingerprint()
        if self.expires_at == 0:
            # TTL: 10 minutes by default
            self.expires_at = self.created_at + 600

    def generate_fingerprint(self) -> str:
        """Generates a deterministic fingerprint for the plan."""
        # Sort actions to ensure same set of actions produces same fingerprint
        sorted_actions = sorted(
            [f"{a.type}:{json.dumps(a.params, sort_keys=True)}" for a in self.actions]
        )
        data = {
            "wallet": self.wallet.lower(),
            "actions": sorted_actions,
            "risk_score": self.risk_score,
            "block_number": self.block_number
        }
        encoded = json.dumps(data, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Converts the plan to a serializable dictionary."""
        d = asdict(self)
        # Handle enums
        d["lifecycle"] = self.lifecycle.value
        d["context"]["execution_mode"] = self.context.execution_mode.value
        for i, action in enumerate(d["actions"]):
            d["actions"][i]["status"] = self.actions[i].status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionPlan':
        """Reconstructs the plan from a dictionary."""
        actions = [
            PlannedAction(
                action_id=a["action_id"],
                type=a["type"],
                params=a["params"],
                status=ActionStatus(a["status"]),
                tx_hash=a.get("tx_hash"),
                error_code=a.get("error_code")
            ) for a in data["actions"]
        ]
        context = ExecutionContext(
            pre_state=data["context"]["pre_state"],
            post_state=data["context"].get("post_state", {}),
            max_exposure_per_execution=data["context"]["max_exposure_per_execution"],
            execution_mode=ExecutionMode(data["context"]["execution_mode"]),
            simulation_policy=data["context"].get("simulation_policy", "STRICT")
        )
        recovery = ExecutionRecovery(
            retry_count=data["recovery"].get("retry_count", 0),
            interrupted_at_step=data["recovery"].get("interrupted_at_step"),
            last_tx_check=data["recovery"].get("last_tx_check", 0.0)
        )
        return cls(
            wallet=data["wallet"],
            actions=actions,
            risk_score=data["risk_score"],
            block_number=data["block_number"],
            context=context,
            lifecycle=ExecutionLifecycle(data["lifecycle"]),
            recovery=recovery,
            created_at=data["created_at"],
            expires_at=data["expires_at"],
            fingerprint=data["fingerprint"]
        )
