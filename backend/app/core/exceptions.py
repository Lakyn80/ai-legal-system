class ApplicationError(Exception):
    """Base application error."""


class DocumentUploadError(ApplicationError):
    """Raised when a document cannot be uploaded."""


class DocumentProcessingError(ApplicationError):
    """Raised when a document cannot be processed."""


class JurisdictionResolutionError(ApplicationError):
    """Raised when a jurisdiction cannot be resolved."""


class EmbeddingMismatchError(ApplicationError):
    """Raised when collection embeddings do not match the current configuration."""
