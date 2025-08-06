import os
import json
from typing import Any, Dict

try:
    import openai  # type: ignore
except ImportError:
    # Provide a clear error message if openai is not installed
    openai = None  # type: ignore


def call_llm(question: str) -> Dict[str, Any]:
    """
    Transform a natural language question into a structured action plan using a language model.

    This function leverages the OpenAI ChatCompletion API (e.g. GPT-4) to parse
    a user question written in natural language and return a structured JSON-like
    dictionary containing the following keys:

        - intent: a brief description of what the user is trying to accomplish.
        - entities: a list of relevant entities, topics, or dataset names extracted
          from the question.
        - period: a string or structure describing the time period implied by the
          question (e.g. "2010-2020", "dernier mois").
        - actions: an ordered list of high‑level actions that need to be taken to
          fulfil the request (e.g. ["rechercher datasets", "télécharger données",
          "calculer statistiques"]).

    Parameters
    ----------
    question : str
        The user's question in natural language.

    Returns
    -------
    dict
        A dictionary with the keys ``intent``, ``entities``, ``period`` and ``actions``.

    Raises
    ------
    ValueError
        If the OpenAI API key is missing, the model response is not valid JSON,
        or required keys are missing from the response.
    RuntimeError
        If there is a problem communicating with the OpenAI API.
    ImportError
        If the openai library is not installed.
    """
    if openai is None:
        raise ImportError(
            "The `openai` package is required to use call_llm but is not installed."
        )

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Parameter 'question' must be a non-empty string.")

    # Retrieve the API key from environment variables
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "Missing OpenAI API key. Please set the 'OPENAI_API_KEY' environment variable."
        )

    openai.api_key = api_key

    # Construct the messages for the chat completion call.
    # A system message sets the behaviour and format expectations,
    # and a user message supplies the actual question.
    system_prompt = (
        "Vous êtes un assistant qui convertit des questions en langage naturel en plans "
        "d'actions structurés pour interroger des données publiques. Votre tâche consiste "
        "à analyser la question de l'utilisateur et à générer un JSON strict (aucun "
        "commentaire ni texte en dehors du JSON) avec les clés suivantes :\n"
        " - intent : une chaîne décrivant l'intention principale de la requête.\n"
        " - entities : une liste d'entités ou de sujets cités dans la question.\n"
        " - period : la période temporelle implicite ou explicite à laquelle la question se réfère.\n"
        " - actions : une liste ordonnée des actions à exécuter pour satisfaire la demande.\n"
        "Le JSON retourné doit être auto‑suffisant et valide. Utilisez le fuseau horaire Europe/Paris "
        "pour interpréter les périodes relatives. Si la période n'est pas précisée, définissez‑la à null "
        "ou une chaîne vide. Répondez uniquement avec le JSON."
    )

    user_prompt = (
        f"Question utilisateur : \"{question.strip()}\"\n"
        "Analysez cette question et produisez un JSON conforme aux spécifications ci‑dessus."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = openai.ChatCompletion.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4"),
            messages=messages,
            temperature=0,
            max_tokens=512,
        )
    except Exception as exc:
        # Wrap all exceptions from the OpenAI client into a RuntimeError
        raise RuntimeError(f"Erreur lors de l'appel à l'API OpenAI : {exc}") from exc

    # Extract the content of the first choice and attempt to parse it as JSON.
    try:
        content = response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Réponse inattendue de l'API OpenAI : impossible d'extraire le contenu du message. {exc}"
        ) from exc

    try:
        plan = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Le modèle a retourné une réponse qui n'est pas un JSON valide : {content}"
        ) from exc

    # Validate the presence of required keys in the response.
    required_keys = {"intent", "entities", "period", "actions"}
    missing = required_keys - plan.keys()
    if missing:
        raise ValueError(
            f"La réponse du modèle est incomplète : clés manquantes {', '.join(sorted(missing))}."
        )

    return plan


__all__ = ["call_llm"]
