"""Auditable causal-path contracts at the evidence-to-underwriting boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from asymmetric_engine.domain.evidence import (
    Claim,
    ClaimType,
    EvidenceItem,
    SourceDocument,
)
from asymmetric_engine.domain.evidence.models import ContentHash, NonEmptyString
from asymmetric_engine.domain.evidence.source_documents import SubjectId
from asymmetric_engine.domain.temporal import KnowledgeBoundary

CausalObjectId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[a-z][a-z0-9_.:-]*$",
    ),
]


class CausalNodeKind(StrEnum):
    """Ordered economic roles in the Chapter 4 causal path."""

    REAL_WORLD_CHANGE = "real_world_change"
    ECONOMIC_DRIVER = "economic_driver"
    SUPPLY_CHAIN_ACTOR = "supply_chain_actor"
    BENEFICIARY = "beneficiary"


class CausalEdgeKind(StrEnum):
    """Allowed directional transitions between adjacent causal roles."""

    CHANGE_DRIVES_DRIVER = "change_drives_driver"
    DRIVER_TRANSMITS_TO_ACTOR = "driver_transmits_to_actor"
    ACTOR_MAPS_TO_BENEFICIARY = "actor_maps_to_beneficiary"


class CausalReadiness(StrEnum):
    """Epistemic hand-off state; none of these values is an investment decision."""

    INVESTIGATE = "investigate"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    READY_FOR_UNDERWRITING = "ready_for_underwriting"
    INVALIDATED = "invalidated"


class CausalNode(BaseModel):
    """One typed role in a causal beneficiary hypothesis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: CausalObjectId
    kind: CausalNodeKind
    label: NonEmptyString
    subject_id: SubjectId | None = None

    @model_validator(mode="after")
    def require_canonical_beneficiary_identity(self) -> Self:
        """Only the listed beneficiary is a canonical company subject in this slice."""

        if self.kind is CausalNodeKind.BENEFICIARY and self.subject_id is None:
            raise ValueError("a beneficiary requires a canonical subject_id")
        if self.kind is not CausalNodeKind.BENEFICIARY and self.subject_id is not None:
            raise ValueError("only beneficiary nodes may declare subject_id")
        return self


class CausalEdge(BaseModel):
    """A directional economic mechanism supported by explicitly typed claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: CausalObjectId
    kind: CausalEdgeKind
    source_node_id: CausalObjectId
    target_node_id: CausalObjectId
    mechanism: NonEmptyString
    claim_ids: tuple[UUID, ...] = Field(min_length=1)

    @field_validator("claim_ids")
    @classmethod
    def reject_duplicate_claim_references(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        """A repeated claim reference must not imply additional causal support."""

        if len(value) != len(set(value)):
            raise ValueError("duplicate claim_ids are not allowed")
        return value

    @model_validator(mode="after")
    def reject_self_reference(self) -> Self:
        """A causal mechanism must move between two distinct nodes."""

        if self.source_node_id == self.target_node_id:
            raise ValueError("a causal edge cannot reference the same node twice")
        return self


class CausalAnalysisDraft(BaseModel):
    """Validated analytical input before ledger bytes are verified and fingerprinted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: CausalObjectId
    title: NonEmptyString
    knowledge_boundary: KnowledgeBoundary
    method_version: NonEmptyString
    readiness: CausalReadiness
    source_document_ids: tuple[UUID, ...] = Field(min_length=1)
    nodes: tuple[CausalNode, ...] = Field(min_length=2)
    edges: tuple[CausalEdge, ...] = Field(min_length=1)
    evidence: tuple[EvidenceItem, ...] = Field(min_length=1)
    claims: tuple[Claim, ...] = Field(min_length=1)
    invalidation_conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    missing_data: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[NonEmptyString, ...] = ()
    assumptions: tuple[NonEmptyString, ...] = ()
    invalidation_reason: NonEmptyString | None = None

    @field_validator("source_document_ids")
    @classmethod
    def reject_duplicate_document_references(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        """A repeated source version must never appear to be independent corroboration."""

        if len(value) != len(set(value)):
            raise ValueError("duplicate source_document_ids are not allowed")
        return value

    @field_validator("invalidation_conditions", "missing_data", "conflicts", "assumptions")
    @classmethod
    def reject_duplicate_disclosures(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Keep disclosures explicit without inflating their apparent weight."""

        if len(value) != len(set(value)):
            raise ValueError("duplicate disclosure entries are not allowed")
        return value

    @model_validator(mode="after")
    def validate_causal_contract(self) -> Self:
        """Resolve the complete document-to-decision lineage and readiness gates."""

        nodes = {node.node_id: node for node in self.nodes}
        edges = {edge.edge_id: edge for edge in self.edges}
        evidence = {item.evidence_id: item for item in self.evidence}
        claims = {claim.claim_id: claim for claim in self.claims}
        if len(self.nodes) != len(nodes):
            raise ValueError("duplicate node_ids are not allowed")
        if len(self.edges) != len(edges):
            raise ValueError("duplicate edge_ids are not allowed")
        if len(self.evidence) != len(evidence):
            raise ValueError("duplicate evidence_ids are not allowed")
        if len(self.claims) != len(claims):
            raise ValueError("duplicate claim_ids are not allowed")
        source_document_ids = set(self.source_document_ids)

        for item in self.evidence:
            if (
                item.source_document_id is None
                or item.source_locator is None
                or item.extraction_method is None
            ):
                raise ValueError(
                    f"evidence {item.evidence_id} must link to an immutable source document"
                )
            if item.source_document_id not in source_document_ids:
                raise ValueError(
                    f"evidence {item.evidence_id} references an undeclared source document"
                )
            exclusion = item.knowledge_exclusion_reason(self.knowledge_boundary)
            if exclusion is not None:
                raise ValueError(
                    f"evidence {item.evidence_id} is outside the knowledge boundary: "
                    f"{exclusion.value}"
                )

        referenced_evidence: set[UUID] = set()
        for claim in self.claims:
            unknown_evidence = set(claim.evidence_ids).difference(evidence)
            if unknown_evidence:
                raise ValueError(f"claim {claim.claim_id} references unknown evidence_ids")
            referenced_evidence.update(claim.evidence_ids)
        if referenced_evidence != set(evidence):
            raise ValueError("every evidence item must support at least one claim")

        referenced_claims: set[UUID] = set()
        referenced_nodes: set[str] = set()
        allowed_roles = {
            CausalEdgeKind.CHANGE_DRIVES_DRIVER: (
                CausalNodeKind.REAL_WORLD_CHANGE,
                CausalNodeKind.ECONOMIC_DRIVER,
            ),
            CausalEdgeKind.DRIVER_TRANSMITS_TO_ACTOR: (
                CausalNodeKind.ECONOMIC_DRIVER,
                CausalNodeKind.SUPPLY_CHAIN_ACTOR,
            ),
            CausalEdgeKind.ACTOR_MAPS_TO_BENEFICIARY: (
                CausalNodeKind.SUPPLY_CHAIN_ACTOR,
                CausalNodeKind.BENEFICIARY,
            ),
        }
        inferential_types = {ClaimType.INFERENCE, ClaimType.HYPOTHESIS}

        for edge in self.edges:
            source = nodes.get(edge.source_node_id)
            target = nodes.get(edge.target_node_id)
            if source is None or target is None:
                raise ValueError(f"edge {edge.edge_id} references an unknown node")
            if (source.kind, target.kind) != allowed_roles[edge.kind]:
                raise ValueError(f"edge {edge.edge_id} does not match its typed causal roles")
            unknown_claims = set(edge.claim_ids).difference(claims)
            if unknown_claims:
                raise ValueError(f"edge {edge.edge_id} references unknown claim_ids")
            if not any(
                claims[claim_id].claim_type in inferential_types for claim_id in edge.claim_ids
            ):
                raise ValueError(
                    f"edge {edge.edge_id} requires at least one inference or hypothesis claim"
                )
            referenced_claims.update(edge.claim_ids)
            referenced_nodes.update((edge.source_node_id, edge.target_node_id))

        if referenced_claims != set(claims):
            raise ValueError("every claim must support at least one causal edge")
        if referenced_nodes != set(nodes):
            raise ValueError("every node must participate in at least one causal edge")
        if {item.source_document_id for item in self.evidence} != source_document_ids:
            raise ValueError(
                "every declared source document must support at least one evidence item"
            )

        if self.readiness is CausalReadiness.READY_FOR_UNDERWRITING and not self._has_complete_path(
            nodes, edges
        ):
            raise ValueError(
                "ready_for_underwriting requires a complete change-to-beneficiary path"
            )
        if self.readiness is CausalReadiness.INSUFFICIENT_EVIDENCE and not self.missing_data:
            raise ValueError("insufficient_evidence requires explicit missing_data")
        if self.readiness is CausalReadiness.INVALIDATED:
            if self.invalidation_reason is None:
                raise ValueError("invalidated analysis requires invalidation_reason")
        elif self.invalidation_reason is not None:
            raise ValueError("invalidation_reason is allowed only when readiness is invalidated")
        return self

    @staticmethod
    def _has_complete_path(
        nodes: dict[str, CausalNode],
        edges: dict[str, CausalEdge],
    ) -> bool:
        drivers = {
            edge.target_node_id
            for edge in edges.values()
            if edge.kind is CausalEdgeKind.CHANGE_DRIVES_DRIVER
            and nodes[edge.source_node_id].kind is CausalNodeKind.REAL_WORLD_CHANGE
        }
        actors = {
            edge.target_node_id
            for edge in edges.values()
            if edge.kind is CausalEdgeKind.DRIVER_TRANSMITS_TO_ACTOR
            and edge.source_node_id in drivers
        }
        return any(
            edge.kind is CausalEdgeKind.ACTOR_MAPS_TO_BENEFICIARY
            and edge.source_node_id in actors
            and nodes[edge.target_node_id].kind is CausalNodeKind.BENEFICIARY
            for edge in edges.values()
        )


class CausalAnalysis(CausalAnalysisDraft):
    """Ledger-verified, deterministic causal analysis ready for audit and hand-off."""

    analysis_id: UUID
    input_fingerprint: ContentHash
    source_documents: tuple[SourceDocument, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_canonical_source_bindings(self) -> Self:
        """Ensure every evidence item is an exact, knowable projection of its source version."""

        documents = {document.document_id: document for document in self.source_documents}
        if len(documents) != len(self.source_documents):
            raise ValueError("duplicate source documents are not allowed")
        if set(documents) != set(self.source_document_ids):
            raise ValueError("verified source documents must match source_document_ids exactly")

        for document in self.source_documents:
            exclusion = document.knowledge_exclusion_reason(self.knowledge_boundary)
            if exclusion is not None:
                raise ValueError(
                    f"source document {document.document_id} is outside the knowledge boundary: "
                    f"{exclusion.value}"
                )

        for item in self.evidence:
            document = documents[cast(UUID, item.source_document_id)]
            expected_provenance = (
                document.source_uri,
                document.source_type,
                document.effective_at,
                document.available_at,
                document.recorded_at,
                document.content_hash,
            )
            actual_provenance = (
                item.source_uri,
                item.source_type,
                item.effective_at,
                item.available_at,
                item.recorded_at,
                item.content_hash,
            )
            if actual_provenance != expected_provenance:
                raise ValueError(
                    f"evidence {item.evidence_id} provenance does not match its source document"
                )

        document_subjects = {document.subject_id for document in self.source_documents}
        beneficiary_subjects = {
            node.subject_id
            for node in self.nodes
            if node.kind is CausalNodeKind.BENEFICIARY and node.subject_id is not None
        }
        if not beneficiary_subjects.issubset(document_subjects):
            raise ValueError(
                "every beneficiary requires a source document for its canonical subject"
            )
        return self
