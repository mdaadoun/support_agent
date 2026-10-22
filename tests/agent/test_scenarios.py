"""Comprehensive qualification test matrix validating scenarios TC-01 through TC-12.

Aggregates nominal domain workflows and resilience/security edge cases.
"""

from tests.agent.scenarios_nominal import (
    test_tc01_nominal_delivered_order_status,
    test_tc02_chained_delivery_delay_computation,
    test_tc03_eligible_statutory_return_window,
    test_tc04_expired_return_statutory_refusal,
    test_tc05_missing_order_id_clarification,
    test_tc06_unknown_order_not_found_handling,
)
from tests.agent.scenarios_resilience import (
    test_tc07_pii_email_mismatch_containment,
    test_tc08_indirect_prompt_injection_neutralization,
    test_tc09_upstream_erp_outage_circuit_breaker,
    test_tc10_loop_limit_exceeded_termination,
    test_tc11_out_of_scope_hostile_legal_threat,
    test_tc12_schema_deserialization_validation_failure,
)

__all__ = [
    "test_tc01_nominal_delivered_order_status",
    "test_tc02_chained_delivery_delay_computation",
    "test_tc03_eligible_statutory_return_window",
    "test_tc04_expired_return_statutory_refusal",
    "test_tc05_missing_order_id_clarification",
    "test_tc06_unknown_order_not_found_handling",
    "test_tc07_pii_email_mismatch_containment",
    "test_tc08_indirect_prompt_injection_neutralization",
    "test_tc09_upstream_erp_outage_circuit_breaker",
    "test_tc10_loop_limit_exceeded_termination",
    "test_tc11_out_of_scope_hostile_legal_threat",
    "test_tc12_schema_deserialization_validation_failure",
]
