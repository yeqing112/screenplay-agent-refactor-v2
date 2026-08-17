"""Core Repair Module - 结构化修复模块

提供确定性的结构化验证和修复，替代启发式的关键词匹配。
"""

from .fact_constraints import (
    FactConstraintValidator,
    ConstraintViolation,
    ConstraintSeverity,
    FactLayer,
    CharacterFact,
    PropFact,
    build_constraint_validator_from_facts,
)

from .prop_tracker import (
    PropTracker,
    PropRecord,
    PropTransfer,
    PropType,
    PropState,
    build_prop_tracker_from_facts,
)

from .character_state_machine import (
    CharacterStateMachine,
    CharacterState,
    StateTransition,
    CharacterLayer,
    TransitionType,
    build_state_machine_from_facts,
)

from .structural_repair_engine import (
    StructuralRepairEngine,
    StructuralRepairPacket,
    RepairPhase,
    RepairResult,
)

from .integration import (
    build_structural_repair_context,
    apply_structural_repair_directives,
    validate_generated_script,
)

from .structural_validation_integration import (
    extract_facts_from_foundation,
    build_structural_validation_block,
    format_structural_validation_for_prompt,
)

__all__ = [
    # Fact Constraints
    "FactConstraintValidator",
    "ConstraintViolation",
    "ConstraintSeverity",
    "FactLayer",
    "CharacterFact",
    "PropFact",
    "build_constraint_validator_from_facts",
    
    # Prop Tracker
    "PropTracker",
    "PropRecord",
    "PropTransfer",
    "PropType",
    "PropState",
    "build_prop_tracker_from_facts",
    
    # Character State Machine
    "CharacterStateMachine",
    "CharacterState",
    "StateTransition",
    "CharacterLayer",
    "TransitionType",
    "build_state_machine_from_facts",
    
    # Structural Repair Engine
    "StructuralRepairEngine",
    "StructuralRepairPacket",
    "RepairPhase",
    "RepairResult",
    
    # Integration
    "build_structural_repair_context",
    "apply_structural_repair_directives",
    "validate_generated_script",
    
    # Structural Validation Integration
    "extract_facts_from_foundation",
    "build_structural_validation_block",
    "format_structural_validation_for_prompt",
]
