class ConfigurationError(Exception):
    """Configuration manquante ou invalide (ex. GEMINI_API_KEY absente)."""


class ProviderError(Exception):
    """Échec d'un appel à un fournisseur externe (LLM, etc.)."""
