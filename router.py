"""
router.py
---------

Définition des routes HTTP exposées par l'API ``mcp_datagouv``. Ce module
contient toute la logique liée à la validation des requêtes entrantes,
l'appel à l'orchestrateur et la normalisation des réponses.  

La route principale ``/query`` reçoit une question en langage naturel via
une requête POST, invoque l'orchestrateur pour produire un résultat
structuré et renvoie une réponse JSON contenant au minimum un résumé
textuel et éventuellement des objets annexes (données tabulaires,
graphiques, cartes, etc.).  

Les exceptions sont interceptées afin de renvoyer des erreurs HTTP
cohérentes pour le client.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

try:
    # L'orchestrateur est implémenté dans un module voisin. Il se peut que
    # différents agents implémentent différentes signatures : nous restons
    # flexibles en détectant dynamiquement la fonction appropriée.
    import orchestrator  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - import failure handled in endpoint
    orchestrator = None  # type: ignore[assignment]
    logging.getLogger(__name__).warning(
        "Impossible d'importer l'orchestrateur : %s", exc
    )


logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    """Schéma Pydantic pour représenter une requête d'interrogation.

    Attributes
    ----------
    question : str
        La question posée par l'utilisateur en langage naturel. Ce champ est
        obligatoire et ne doit pas être vide.
    """

    question: str = Field(..., min_length=1, description="Question en langage naturel")


class QueryResponse(BaseModel):
    """Schéma Pydantic décrivant la structure de la réponse.

    Attributes
    ----------
    summary : str
        Un résumé synthétique de la réponse générée par l'orchestrateur.
    results : Optional[Any]
        Les résultats associés à la requête : il peut s'agir d'un
        dictionnaire ou d'une liste de structures décrivant des tableaux,
        graphiques ou cartes. Ce champ est optionnel car certaines
        réponses peuvent ne comporter qu'un résumé.
    error : Optional[str]
        Si une erreur est survenue, ce champ contiendra un message détaillé.
    """

    summary: str
    results: Optional[Any] = None
    error: Optional[str] = None


def _select_orchestrator_function(module: Any) -> Callable[[str], Any]:
    """Sélectionne dynamiquement la fonction de l'orchestrateur à appeler.

    L'implémentation de l'orchestrateur n'étant pas encore définie, ce
    helper recherche parmi un ensemble de noms usuels la première
    fonction disponible. Si aucune fonction connue n'est trouvée, une
    exception est levée.

    :param module: le module orchestrateur importé
    :returns: une fonction prenant une ``str`` en argument et renvoyant un objet
    :raises AttributeError: si aucune fonction attendue n'est présente
    """

    candidates = [
        "handle_query",
        "handle_question",
        "process_question",
        "process_query",
        "orchestrate",
        "run",
        "__call__",  # au cas où l'orchestrateur soit un objet callable
    ]
    for name in candidates:
        func = getattr(module, name, None)
        if callable(func):
            return func  # type: ignore[return-value]
    raise AttributeError(
        "Aucune fonction d'orchestration connue n'a été trouvée dans le module"
    )


def _invoke_orchestrator(func: Callable[[str], Any], question: str) -> Any:
    """Appelle la fonction d'orchestration en gérant la compatibilité async.

    Certaines implémentations de l'orchestrateur pourront renvoyer une
    coroutine ; ce helper détecte ce cas pour l'attendre via ``await``.

    :param func: fonction d'orchestration sélectionnée
    :param question: texte de la question utilisateur
    :returns: résultat retourné par l'orchestrateur (résolu si coroutine)
    """

    try:
        result = func(question)  # exécution éventuelle
        # Si la fonction renvoie un objet awaitable, on l'attend
        if inspect.isawaitable(result):
            return result  # retour de coroutine, FastAPI saura awaiter
        return result
    except Exception as exc:
        logger.exception("Erreur lors de l'appel à l'orchestrateur")
        raise exc


# Instanciation du routeur principal. Tous les endpoints sont ajoutés à ce router.
api_router = APIRouter(prefix="", tags=["query"])


@api_router.post(
    "/query",
    response_model=QueryResponse,
    summary="Interroger le MCP avec une question en langage naturel",
    response_description="Résumé et résultats structurés produits par l'orchestrateur",
)
async def query_endpoint(payload: QueryRequest) -> QueryResponse:
    """Point d'entrée HTTP pour interroger l'orchestrateur.

    Cette route reçoit une question via le champ ``question`` du corps de
    requête. Elle transmet ensuite ce texte à l'orchestrateur, récupère
    la réponse, la formate selon le schéma ``QueryResponse`` et gère
    proprement les erreurs en renvoyant des codes HTTP adaptés.

    :param payload: requête contenant la question utilisateur
    :returns: une instance de :class:`QueryResponse`
    :raises HTTPException: si l'orchestrateur n'est pas disponible ou renvoie
                          une erreur inattendue
    """

    # Vérifier que l'orchestrateur a pu être importé
    if orchestrator is None:
        # Retourner une erreur 500 si l'import a échoué à l'initialisation
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="L'orchestrateur n'est pas disponible. Vérifiez son installation.",
        )

    # Sélectionner dynamiquement la fonction à appeler
    try:
        orchestrate_func = _select_orchestrator_function(orchestrator)
    except AttributeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    try:
        # Appeler la fonction d'orchestration. Si elle renvoie une coroutine,
        # FastAPI gère automatiquement l'attente via ``await``.
        raw_result = _invoke_orchestrator(orchestrate_func, payload.question)
        # Si une coroutine a été retournée, on attend son résultat ici. Cela
        # fonctionne car ``_invoke_orchestrator`` renvoie soit un objet normal
        # soit une coroutine ; FastAPI attendra la coroutine implicitement.
        if inspect.isawaitable(raw_result):
            raw_result = await raw_result
    except ValueError as exc:
        # Les erreurs de validation renvoyées par l'orchestrateur sont
        # considérées comme des requêtes mal formées (400)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        # Ne pas encapsuler deux fois les HTTPException
        raise
    except Exception as exc:
        # Journaliser l'erreur et renvoyer une réponse 500
        logger.exception("Erreur inattendue dans le endpoint /query: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Une erreur interne est survenue lors du traitement de la requête.",
        ) from exc

    # Normaliser la réponse : l'orchestrateur peut renvoyer différentes structures.
    summary: str
    results: Optional[Any] = None
    error_msg: Optional[str] = None

    if isinstance(raw_result, dict):
        # Extraire un résumé potentiel. Plusieurs clés possibles pour la
        # compatibilité avec différents orchestrateurs.
        summary = (
            raw_result.get("summary")
            or raw_result.get("resume")
            or raw_result.get("abstract")
            or ""
        )
        # Extraire les résultats ou données supplémentaires
        # On normalise en None si rien n'est fourni.
        results = (
            raw_result.get("results")
            or raw_result.get("data")
            or raw_result.get("datasets")
            or raw_result.get("charts")
            or raw_result.get("tables")
        )
        # Message d'erreur éventuel
        error_msg = raw_result.get("error")
    else:
        # Si l'orchestrateur renvoie autre chose qu'un dict, utiliser sa
        # représentation textuelle comme résumé.
        summary = str(raw_result)

    # Retourner la réponse formatée. Toutes les clés optionnelles non
    # renseignées seront omises de la réponse JSON grâce à ``exclude_none``.
    return QueryResponse(summary=summary, results=results, error=error_msg)
