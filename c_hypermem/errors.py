class CHyperMemError(Exception):
    """Base exception for C-HyperMem."""


class ConfigError(CHyperMemError):
    """Raised when a memory config cannot be loaded or validated."""


class StoreError(CHyperMemError):
    """Raised when the persistence layer fails."""


class IngestionNotConfiguredError(CHyperMemError):
    """Raised when add() is called without a configured extraction pipeline."""
