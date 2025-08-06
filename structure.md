# 📁 Projet : mcp_datagouv

# Ce répertoire est une base pour un MCP (Model Context Protocol) orienté
# vers la fouille, l'extraction et la visualisation de données exposées sur data.gouv.fr.
# Il est conçu pour être branché à un frontend React (monÉtat) ou utilisé en ligne de commande.

# ================================
# 📦 Structure de fichiers
# ================================

mcp_datagouv/
├── main.py                  # Entrypoint FastAPI (API REST LLM-compatible)
├── orchestrator.py          # Coeur MCP : reçoit une question NL, orchestre les actions
├── planner.py               # Transforme un prompt NL en "plan d'action" (JSON structuré)
├── llm_agent.py             # Appelle OpenAI / Claude / modèle local pour interpréter la requête
├── datagouv_api.py          # Interroge le catalogue data.gouv.fr via API
├── downloader.py            # Télécharge les fichiers (CSV, JSON, GeoJSON...)
├── router.py                # Définit les routes FastAPI à exposer

# 🧠 Modules de parsing & traitement
├── parsers/
│   ├── __init__.py
│   ├── csv_parser.py        # Utilise pandas pour parser les CSV intelligemment
│   ├── json_parser.py
│   ├── xml_parser.py
│   ├── geojson_parser.py
│   └── xls_parser.py

# 📊 Modules de visualisation
├── visualizer/
│   ├── __init__.py
│   ├── map_animator.py      # Utilise folium / geopandas / imageio
│   └── summary_chart.py     # Génère des graphes de synthèse (matplotlib / seaborn)

# 📂 Modules utilitaires
├── utils/
│   ├── file_utils.py        # Détection des formats, conversion, extraction temporaire
│   ├── temporal_utils.py    # Reformatage de dates, regroupement temporel
│   └── geo_utils.py         # Conversion, centroides, coordonnées, shapefiles...

# 🧪 Tests
├── tests/
│   ├── test_orchestrator.py
│   └── test_parsers.py

# 📚 Config & dépendances
├── requirements.txt         # Dépendances (pandas, requests, openai, fastapi...)
├── README.md                # Documentation du MCP

# ================================
# 📌 Étapes suivantes
# ================================
# 1. Créer le orchestrator de base : question NL → plan JSON → exécution du plan
# 2. Intégrer un premier parseur CSV avec test sur un dataset data.gouv.fr
# 3. Créer route FastAPI /query qui reçoit une question
# 4. Côté front (monÉtat), ajouter un composant <ChatMCP /> qui dialogue avec l’API
