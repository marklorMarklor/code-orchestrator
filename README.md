# code-orchestrator
l'orchestrateur des agents qui créent des projets complexes en travaillant en parallèle

📘 README – Orchestration distribuée d’un MCP multi-agents
Ce projet repose sur un principe de développement modulaire, distribué et orchestré par LLM.
Chaque module est défini dans un fichier spec.json, situé dans le dépôt code_orchestrateur, et confié à un agent GPT spécialisé, capable de travailler de façon autonome selon cette spécification.

📂 Structure des rôles
Agent	Rôle	Modules assignés
AgentRouter	expose les routes et l’API FastAPI	main.py, router.py
AgentOrchestrator	coordonne tous les appels internes	orchestrator.py
AgentLLM	appelle un LLM pour transformer une question en plan d’action	llm_agent.py
AgentPlanner	planifie l’ordre d’exécution à partir de la sortie du LLM	planner.py
AgentAPIFetch	interroge data.gouv.fr et télécharge les fichiers	datagouv_api.py, downloader.py
AgentParsers	parse les fichiers selon leur format	parsers/*.py
AgentVisualizer	génère cartes animées et graphiques	visualizer/*.py
AgentUtils	fonctions temporelles, géo, format	utils/*.py

✅ Objectif
Orchestrer un projet complet (MCP d’exploration data.gouv.fr) via des prompts parallèles

Centraliser la spec dans https://raw.githubusercontent.com/ju/code_orchestrateur/main/spec.json

Rassembler automatiquement les fichiers produits dans le dossier mcp_datagouv/
