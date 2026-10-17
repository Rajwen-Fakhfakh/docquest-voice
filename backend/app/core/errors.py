class ConfigurationError(Exception):
    """Configuration manquante ou invalide (ex. GEMINI_API_KEY absente)."""


class ProviderError(Exception):
    """Échec d'un appel à un fournisseur externe (LLM, etc.)."""


class RateLimitError(Exception):
    """Trop de requêtes (limite par IP ou plafond journalier de la démo)."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after
