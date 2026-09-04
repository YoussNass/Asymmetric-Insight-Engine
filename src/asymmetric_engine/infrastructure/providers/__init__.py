"""Freely accessible evidence-provider adapters."""

from asymmetric_engine.application.sec_source_manifest import (
    SecFilingCatalogEntry,
    SecSubmissionCatalog,
    SecSubmissionHistoryPage,
)
from asymmetric_engine.infrastructure.providers.local_file import (
    LOCAL_MANUAL_PROVIDER,
    LocalFileEvidenceMetadata,
    LocalFileSourceProvider,
)
from asymmetric_engine.infrastructure.providers.sec_edgar import (
    ProviderAccessError,
    ProviderPayloadError,
    SecEdgarHttpFetcher,
    SecEdgarProvider,
    UnsupportedSecFilingError,
)
from asymmetric_engine.infrastructure.providers.sec_edgar_submissions import (
    SEC_SUBMISSIONS_ROOT,
    SecEdgarSubmissionsProvider,
    SecSubmissionCatalogPayloadError,
)

__all__ = [
    "LOCAL_MANUAL_PROVIDER",
    "SEC_SUBMISSIONS_ROOT",
    "LocalFileEvidenceMetadata",
    "LocalFileSourceProvider",
    "ProviderAccessError",
    "ProviderPayloadError",
    "SecEdgarHttpFetcher",
    "SecEdgarProvider",
    "SecEdgarSubmissionsProvider",
    "SecFilingCatalogEntry",
    "SecSubmissionCatalog",
    "SecSubmissionCatalogPayloadError",
    "SecSubmissionHistoryPage",
    "UnsupportedSecFilingError",
]
