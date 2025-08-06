"""
main.py
---------

Point d'entrée pour l'API REST du projet ``mcp_datagouv``.  
Ce module instancie une application FastAPI, configure les métadonnées
de documentation et branche les routes définies dans ``router.py``.

Le but de ce fichier est de fournir un service HTTP compatible avec le MCP
(Model Context Protocol) décrit dans la spécification du projet. Les
requêtes en langage naturel arrivent via une route POST et sont
traitées par l'orchestrateur via le routeur dédié.  

À l'exécution, vous pouvez démarrer l'API avec ``uvicorn`` ou tout
autre serveur ASGI :

    uvicorn mcp_datagouv.main:app --reload

Le module ne contient volontairement aucune logique métier : il se
contente de déclarer l'application et de brancher les composants.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

# Le router défini dans ``router.py`` expose les routes publiques.
from .router import api_router


def create_app() -> FastAPI:
    """Crée et configure l'application FastAPI pour le MCP.

    Cette fonction est isolée afin de faciliter les tests unitaires et
    d'autoriser une configuration plus fine (middlewares, CORS, etc.) si
    nécessaire.  

    :returns: une instance de :class:`~fastapi.FastAPI` prête à être
              servie.
    """
    app = FastAPI(
        title="MCP DataGouv API",
        description=(
            "API REST pour interroger et visualiser les données du portail "
            "data.gouv.fr via des requêtes en langage naturel. Elle fait "
            "office de façade pour l'orchestrateur du modèle, en renvoyant des "
            "résumés et des résultats structurés (données tabulaires, graphiques, "
            "cartes, etc.)."
        ),
        version="0.1",
        contact={
            "name": "MCP DataGouv",
            "url": "https://github.com/marklorMarklor/code-orchestrator",
        },
    )

    # Inclure les routes exposées par le router principal.
    app.include_router(api_router)

    @app.get("/", summary="Racine de l'API", tags=["root"])
    async def root() -> dict[str, str]:
        """Route racine très simple.

        Fournit un message d'accueil et rappelle l'utilité de l'API. Cette
        route peut également servir de test de l'aliveness du service.

        :returns: un dictionnaire avec un message de bienvenue.
        """

        return {
            "message": (
                "Bienvenue sur l'API MCP DataGouv. Utilisez la route POST /query "
                "pour poser vos questions en langage naturel."
            )
        }

    return app


# Instance globale de l'application, importée par les serveurs ASGI
app = create_app()


if __name__ == "__main__":  # pragma: no cover
    # Permet de lancer l'application directement avec ``python -m mcp_datagouv.main``
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
