"""Authority boundary compatibility surface.

The provider can use these pure helpers, while activation remains owned by
the human review routes.  Keeping the surface separate prevents callers from
mistaking a proposal for an activated asset authority.
"""

from core.visual_authoring_provider import (  # noqa: F401
    ALLOWED_FIELDS,
    FORBIDDEN_FIELDS,
    VISUAL_AUTHORING_PROVIDER_CONTRACT_VERSION,
    VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION,
    build_visual_authoring_provider_context,
    proposal_payload_fingerprint,
    validate_visual_authoring_proposal,
)

__all__ = [
    "ALLOWED_FIELDS", "FORBIDDEN_FIELDS", "VISUAL_AUTHORING_PROVIDER_CONTRACT_VERSION",
    "VISUAL_AUTHORING_PROPOSAL_SCHEMA_VERSION", "build_visual_authoring_provider_context",
    "proposal_payload_fingerprint", "validate_visual_authoring_proposal",
]
