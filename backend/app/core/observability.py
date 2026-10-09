"""Point d'extension unique pour l'observabilité (tracing, métriques, coûts).

Tous les appels LangChain passent leurs callbacks par `get_callbacks()`. Pour brancher
Langfuse (ou autre) plus tard, il suffit de modifier cette fonction : aucun autre code
n'a besoin de changer.
"""

from langchain_core.callbacks import BaseCallbackHandler


def get_callbacks() -> list[BaseCallbackHandler]:
    # Aucun handler pour l'instant. Exemple d'extension future :
    #   from langfuse.langchain import CallbackHandler
    #   return [CallbackHandler()]
    return []


def runnable_config() -> dict:
    """Config LangChain à passer à `invoke`/`ainvoke` (`config=...`)."""
    return {"callbacks": get_callbacks()}
