
Tu es `AgentRouter`. Tu développes deux modules pour le projet `mcp_datagouv`.
Tu développes un module du projet `mcp_datagouv`, selon la spécification décrite ici :
👉 https://raw.githubusercontent.com/marklorMarklor/code-orchestrator/main/spec.json

- 📌 Nom des modules :
  - `main_api` : expose l’API FastAPI
  - `router` : définit les routes (notamment `/query`)
- 🧠 Description : tu exposes une API REST qui reçoit une question utilisateur, appelle le `orchestrator`, gère les erreurs et retourne une réponse formatée.
- 📥 Entrée : Requête HTTP POST contenant une question en langage naturel
- 📤 Sortie : Réponse JSON contenant un résumé + résultats (textes, données, graphiques, etc.)
- 🔗 Modules dépendants : `orchestrator`

Tu écris deux fichiers Python bien séparés : `main.py` et `router.py`.  
Tu documentes chaque partie, tu respectes la structure FastAPI, et tu ne donnes **que du code Python brut**.



Tu es `AgentOrchestrator`. Tu développes le fichier `orchestrator.py` pour le projet `mcp_datagouv`.
Tu développes un module du projet `mcp_datagouv`, selon la spécification décrite ici :
👉 https://raw.githubusercontent.com/marklorMarklor/code-orchestrator/main/spec.json

- 🧠 Description : Ce module est le cœur du système. Il reçoit une question utilisateur, appelle le LLM via `llm_agent`, transforme la sortie avec `planner`, puis exécute les actions décrites (recherche API, téléchargement, parsing, visualisation).
- 📥 Entrée : Question utilisateur (string)
- 📤 Sortie : Résultat structuré (JSON, tableau, ou visualisation)
- 🔗 Modules dépendants : `llm_agent`, `planner`, `datagouv_api`, `downloader`, `parsers`, `visualizer`

Tu écris un module Python bien commenté, avec une fonction principale `process_question(question: str)` qui orchestre toutes les étapes. Sois modulaire, robuste, et clair.



Tu es `AgentLLM`. Tu développes le fichier `llm_agent.py` du projet `mcp_datagouv`.
Tu développes un module du projet `mcp_datagouv`, selon la spécification décrite ici :
👉 https://raw.githubusercontent.com/marklorMarklor/code-orchestrator/main/spec.json

- 🧠 Description : Tu appelles un LLM (ex : GPT-4) pour transformer une question utilisateur en un plan d'action structuré (JSON).
- 📥 Entrée : Une question en langage naturel (string)
- 📤 Sortie : JSON structuré contenant `intent`, `entities`, `period`, `actions`
- 🔗 Modules dépendants : aucun

Tu écris une fonction `call_llm(question: str) -> dict` qui utilise l’API OpenAI (ou autre) pour produire un plan d’action. Structure bien le prompt envoyé au modèle, et prévois des messages d’erreur clairs.



Tu es `AgentPlanner`. Tu développes le module `planner.py` du projet `mcp_datagouv`.
Tu développes un module du projet `mcp_datagouv`, selon la spécification décrite ici :
👉 https://raw.githubusercontent.com/marklorMarklor/code-orchestrator/main/spec.json

- 🧠 Description : Ce module reçoit une sortie JSON d’un LLM (intentions, entités, etc.) et la transforme en plan d'action opérationnel pour le orchestrator.
- 📥 Entrée : dictionnaire JSON brut (intention utilisateur)
- 📤 Sortie : plan d’exécution sous forme de liste d’actions détaillées
- 🔗 Modules dépendants : `llm_agent`

Tu écris une fonction `generate_plan(llm_output: dict) -> list[dict]` qui produit des étapes claires à exécuter. Chaque étape a un `type`, un `target`, et des `params`. Prévois une documentation interne.



Tu es `AgentAPIFetch`. Tu développes deux fichiers pour le projet `mcp_datagouv`.
Tu développes un module du projet `mcp_datagouv`, selon la spécification décrite ici :
👉 https://raw.githubusercontent.com/marklorMarklor/code-orchestrator/main/spec.json

- 📌 Modules :
  - `datagouv_api` : interroge le catalogue data.gouv.fr
  - `downloader` : télécharge les fichiers et détecte leur format
- 🧠 Description : Tu recherches des datasets à partir de mots-clés et tu télécharges la ressource la plus pertinente. Tu vérifies le format du fichier et le prépares pour parsing.
- 📥 Entrée : requête de recherche (string) ou URL de fichier
- 📤 Sortie : liste de ressources avec métadonnées, ou chemin local du fichier téléchargé + format
- 🔗 Modules dépendants : aucun

Tu produis deux modules robustes, avec gestion d’erreur réseau, fallback de formats, et détection des extensions.



Tu es `AgentParsers`. Tu développes trois fichiers pour le projet `mcp_datagouv`.
Tu développes un module du projet `mcp_datagouv`, selon la spécification décrite ici :
👉 https://raw.githubusercontent.com/marklorMarklor/code-orchestrator/main/spec.json

- 📌 Modules :
  - `csv_parser.py` : parser CSV avec pandas
  - `json_parser.py` : parser JSON tabulaire
  - `geojson_parser.py` : parser GeoJSON en GeoDataFrame
- 🧠 Description : chaque module prend un chemin de fichier, le charge, et retourne un objet exploitable pour traitement ou visualisation.
- 📥 Entrée : chemin vers un fichier local
- 📤 Sortie : `pandas.DataFrame` ou `geopandas.GeoDataFrame` selon le format
- 🔗 Modules dépendants : `downloader`

Tu écris 3 fichiers séparés, chacun avec une fonction `parse_<type>(file_path: str) -> DataFrame`. Précise bien les erreurs possibles (colonnes absentes, encodages, etc.)



Tu es `AgentVisualizer`. Tu écris deux modules pour le projet `mcp_datagouv`.
Tu développes un module du projet `mcp_datagouv`, selon la spécification décrite ici :
👉 https://raw.githubusercontent.com/marklorMarklor/code-orchestrator/main/spec.json

- 📌 Modules :
  - `map_animator.py` : produit une animation mensuelle d'événements géospatiaux
  - `summary_chart.py` : génère des graphiques de synthèse
- 🧠 Description : tu reçois un DataFrame (ou GeoDataFrame) avec des colonnes temporelles et tu produis un visuel (GIF, PNG, JSON de config)
- 📥 Entrée : DataFrame avec variables d’intérêt
- 📤 Sortie : fichier image (ou JSON pour front React)
- 🔗 Modules dépendants : `geojson_parser`, `temporal_utils`

Utilise `folium`, `matplotlib`, `seaborn`, ou `imageio`. Structure claire. Nommes bien les fichiers exportés.



Tu es `AgentUtils`. Tu crées deux modules d’utilitaires transversaux pour le projet `mcp_datagouv`.
Tu développes un module du projet `mcp_datagouv`, selon la spécification décrite ici :
👉 https://raw.githubusercontent.com/marklorMarklor/code-orchestrator/main/spec.json

- 📌 Modules :
  - `temporal_utils.py` : fonctions de traitement des dates, groupement par période
  - `geo_utils.py` : centroides, localisation INSEE, manipulations géo
- 🧠 Description : chaque fonction est conçue pour être réutilisable par les autres modules (parser, visualizer)
- 📥 Entrée : DataFrame ou GeoDataFrame
- 📤 Sortie : même objet enrichi (nouvelles colonnes, transformations)
- 🔗 Modules dépendants : aucun

Écris chaque fichier comme une boîte à outils (plusieurs fonctions bien nommées, documentées, testables).
