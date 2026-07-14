"""Central operation-class registry for SDK and CLI methods.

SDK-CLIENT-15 section9 + section15.3: All public operations must belong to a declared
operation class. The registry prevents route-by-route drift.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, Optional


class OperationClass(enum.Enum):
    """Classified operation types per section9."""

    READ_ONLY = "READ_ONLY"
    WRITE_IDEMPOTENT_REQUIRED = "WRITE_IDEMPOTENT_REQUIRED"
    NATURALLY_CONVERGENT_EXEMPT = "NATURALLY_CONVERGENT_EXEMPT"
    INTERNAL_ONLY_NOT_EXPOSED = "INTERNAL_ONLY_NOT_EXPOSED"


class RetryPolicy(enum.Enum):
    """Retry strategies per section12."""

    SAFE_READ = "SAFE_READ"
    SAFE_WRITE_IDEMPOTENT = "SAFE_WRITE_IDEMPOTENT"
    NO_RETRY = "NO_RETRY"


@dataclass(frozen=True)
class OperationDescriptor:
    """Describes a single registered operation's transport posture."""

    name: str
    operation_class: OperationClass
    retry_policy: RetryPolicy
    idempotency_required: bool
    proof_required: bool = False


# --------------------------------------------------------------
# Canonical Operation Registry
# --------------------------------------------------------------
# section15.3: Central registry mapping public methods/routes to
# operation class, idempotency requirement, retry policy, proof.

_REGISTRY: Dict[str, OperationDescriptor] = {}


def register_operation(descriptor: OperationDescriptor) -> None:
    """Register an operation descriptor in the central registry."""
    _REGISTRY[descriptor.name] = descriptor


def get_operation(name: str) -> Optional[OperationDescriptor]:
    """Lookup an operation descriptor by name."""
    return _REGISTRY.get(name)


def get_all_operations() -> Dict[str, OperationDescriptor]:
    """Return a copy of the full registry."""
    return dict(_REGISTRY)


def is_registered(name: str) -> bool:
    """Check whether an operation name is registered."""
    return name in _REGISTRY


def requires_idempotency(name: str) -> bool:
    """Check whether an operation requires an idempotency key."""
    desc = _REGISTRY.get(name)
    return desc is not None and desc.idempotency_required


# --------------------------------------------------------------
# Built-in operation registrations - current SDK surface
# --------------------------------------------------------------

_BUILTIN_OPERATIONS = [
    # section 9.1 READ_ONLY - no idempotency key
    OperationDescriptor(
        name="capabilities",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="whoami",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="registration_status",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="health",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="identity",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="state",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="context.compile",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="context.inspect",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="run.status",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="events.query",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="gaps.list",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="lineage.get.v0_1",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="convergence.status.v0_1",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    # section 9.2 WRITE_IDEMPOTENT_REQUIRED - key required
    OperationDescriptor(
        name="register",
        operation_class=OperationClass.WRITE_IDEMPOTENT_REQUIRED,
        retry_policy=RetryPolicy.SAFE_WRITE_IDEMPOTENT,
        idempotency_required=True,
        proof_required=True,
    ),
    OperationDescriptor(
        name="run.start",
        operation_class=OperationClass.WRITE_IDEMPOTENT_REQUIRED,
        retry_policy=RetryPolicy.SAFE_WRITE_IDEMPOTENT,
        idempotency_required=True,
        proof_required=True,
    ),
    OperationDescriptor(
        name="realize",
        operation_class=OperationClass.WRITE_IDEMPOTENT_REQUIRED,
        retry_policy=RetryPolicy.SAFE_WRITE_IDEMPOTENT,
        idempotency_required=True,
        proof_required=True,
    ),
    OperationDescriptor(
        name="ingest.submit",
        operation_class=OperationClass.WRITE_IDEMPOTENT_REQUIRED,
        retry_policy=RetryPolicy.SAFE_WRITE_IDEMPOTENT,
        idempotency_required=True,
        proof_required=True,
    ),
    OperationDescriptor(
        name="repo.register",
        operation_class=OperationClass.WRITE_IDEMPOTENT_REQUIRED,
        retry_policy=RetryPolicy.SAFE_WRITE_IDEMPOTENT,
        idempotency_required=True,
        proof_required=True,
    ),
    # section SDK-CLIENT-08: Capability Discovery and Resolution
    OperationDescriptor(
        name="capability.search",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="capability.resolve",
        operation_class=OperationClass.WRITE_IDEMPOTENT_REQUIRED,
        retry_policy=RetryPolicy.SAFE_WRITE_IDEMPOTENT,
        idempotency_required=True,
        proof_required=True,
    ),
    # section SDK-CLIENT-11: Alignment Guidance (READ_ONLY - advisory, no repo mutation)
    OperationDescriptor(
        name="alignment.guidance",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    # section SDK-CLIENT-19: Budget/limit visibility (READ_ONLY - inspection only)
    OperationDescriptor(
        name="run.budget",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    # section SDK-CLIENT-20: Governance explainability (READ_ONLY - explain/inspect)
    OperationDescriptor(
        name="run.explain",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="request.inspect",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    # section SDK-CLIENT-22: Account deregistration (write, idempotent, proof-bearing)
    OperationDescriptor(
        name="auth.remove",
        operation_class=OperationClass.WRITE_IDEMPOTENT_REQUIRED,
        retry_policy=RetryPolicy.SAFE_WRITE_IDEMPOTENT,
        idempotency_required=True,
        proof_required=True,
    ),
    # section SDK-CLIENT-24: Runtime contract verification - read-only discovery
    # and compatibility check exposed by SDK-SERVER-24.
    OperationDescriptor(
        name="sdk.runtime.surface.get.v1",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="sdk.runtime.compatibility.check.v1",
        operation_class=OperationClass.READ_ONLY,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    # section 9.3 NATURALLY_CONVERGENT_EXEMPT - key recommended but not required
    OperationDescriptor(
        name="verify",
        operation_class=OperationClass.NATURALLY_CONVERGENT_EXEMPT,
        retry_policy=RetryPolicy.SAFE_READ,
        idempotency_required=False,
    ),
    OperationDescriptor(
        name="login",
        operation_class=OperationClass.NATURALLY_CONVERGENT_EXEMPT,
        retry_policy=RetryPolicy.NO_RETRY,
        idempotency_required=False,
    ),
]

# Auto-register all built-in operations at import time
for _op in _BUILTIN_OPERATIONS:
    register_operation(_op)
