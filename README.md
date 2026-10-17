# DocQuest Voice

Assistant conversationnel (texte + voix) sur le Document d'Enregistrement Universel (DEU)
2025 de TotalEnergies, avec RAG (Retrieval-Augmented Generation) pour ancrer les réponses
dans le document plutôt que dans la mémoire du modèle.

## Architecture

- **Backend** (`backend/`) : FastAPI + Gemini (`google-genai`). Expose `POST /chat`,
  `POST /chat/stream` et le WebSocket `/ws/voice` (mode vocal, Gemini Live).
- **Frontend** (`frontend/`) : Next.js (App Router). `ChatShell` pilote le chat texte
  (streaming via `/api/chat`) et le mode vocal (WebSocket direct vers le backend, micro +
  lecture audio).
- **RAG** : chunks du DEU indexés avec `gemini-embedding-001`, recherche par similarité
  cosinus, extraits injectés dans le prompt système. Index déjà calculé et versionné
  (`backend/data/index.json.gz`) — rien à indexer après un clone. Détails : [`docs/rag-v3.md`](docs/rag-v3.md).

## Installation

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux : source .venv/bin/activate
pip install -e .[dev]
```

### Frontend

```bash
cd frontend
npm install
```

## Variables d'environnement

- **`.env`** (racine du dépôt, copier depuis `.env.example`) : lu par le backend.
  - `GEMINI_API_KEY` — clé API Gemini ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)).
  - `GEMINI_CHAT_MODEL`, `GEMINI_LIVE_MODEL`, `GEMINI_EMBEDDING_MODEL` — modèles utilisés.
  - `CORS_ORIGINS` — origines autorisées pour le front (séparées par des virgules).
  - `GEMINI_API_KEYS_EXTRA` — clés de secours, utilisées seulement par `scripts/ingest.py`.
- **`frontend/.env.local`** (copier depuis `frontend/.env.example`) :
  - `API_URL` — URL du backend appelée côté serveur par la route `/api/chat`.
  - `NEXT_PUBLIC_WS_URL` — URL WebSocket du backend, jointe directement par le navigateur.

Sans `GEMINI_API_KEY`, le backend démarre mais `/chat` répond 503.

## Lancer en local

```bash
# Backend (depuis backend/, venv activé)
uvicorn app.main:app --reload --port 8000

# Frontend (depuis frontend/, autre terminal)
npm run dev
```

Puis ouvrir [http://localhost:3000](http://localhost:3000).

## Lancer avec Docker

```bash
docker compose up --build
```

Démarre le backend (port 8000) et le frontend (port 3000). Nécessite un `.env` à la racine
(voir ci-dessus) — `docker-compose.yml` l'injecte dans le conteneur backend via `env_file`.

## Tests

```bash
# Backend (depuis backend/, venv activé)
pytest
ruff check .

# Frontend (depuis frontend/)
npm run test
npm run lint
```

Tous les tests backend utilisent des doublures (embeddings, provider Gemini) : aucun appel
réseau, aucune clé API requise.

## CI/CD

- **CI** (`.github/workflows/ci.yml`) : à chaque push/PR, lint + tests backend (ruff, pytest)
  et frontend (eslint, vitest). N'a besoin d'aucun secret.
- **CD** (`.github/workflows/cd.yml`) : sur push vers `main`, construit et publie les images
  Docker backend/frontend sur GitHub Container Registry (GHCR).

### Secret `GEMINI_API_KEY` sur GitHub

Aucun workflow n'en a besoin pour l'instant (tests avec doublures, index RAG déjà commité).
Elle est nécessaire **à l'exécution** pour qui déploie les images (ex. passée à
`docker run -e GEMINI_API_KEY=...` ou au `docker-compose.yml` de prod). Pour la rendre
disponible aux Actions si un futur step en a besoin :

1. Repo GitHub → **Settings** → **Secrets and variables** → **Actions**.
2. **New repository secret** → nom `GEMINI_API_KEY`, valeur = la clé.

## Déploiement

Démo publique, hébergée uniquement sur des plans gratuits :

- **Frontend** : [docquest-voice.vercel.app](https://docquest-voice.vercel.app) (Vercel Hobby)
- **Backend** : [docquest-voice-api.onrender.com](https://docquest-voice-api.onrender.com) (Render Free, Frankfurt)

### Backend sur Render (Web Service, Docker)

- Dépôt GitHub, branche `feat/qdrant`, contexte Docker `backend/`, Dockerfile `backend/Dockerfile`.
- Health check : `/health`. Le Dockerfile écoute sur le port 8000 (`PORT=8000`).
- Variables à renseigner dans **Environment → Environment Variables** (pas dans « Secret Files » :
  l'appli lit `os.environ`, pas `/etc/secrets`) :

| Variable | Valeur |
| --- | --- |
| `GEMINI_API_KEY` | clé API Gemini (secret) |
| `QDRANT_URL` | URL du cluster Qdrant Cloud (secret) |
| `QDRANT_API_KEY` | clé API Qdrant Cloud (secret) |
| `QDRANT_COLLECTION` | `deu2025` |
| `GEMINI_CHAT_MODEL` | modèle du chat texte |
| `CORS_ORIGINS` | URL exacte du front, sans slash final |
| `RATE_LIMIT_PER_MINUTE` | `20` (requêtes par minute et par IP, `0` = désactivé) |
| `DAILY_REQUEST_CAP` | `500` (plafond global par jour, `0` = désactivé) |

`QDRANT_URL` doit rester défini : sans lui, le backend charge l'index local (≈ 190 Mo en
mémoire) et dépasse les 512 Mo du plan gratuit.

### Frontend sur Vercel (projet Next.js)

- Répertoire racine : `frontend`.
- `API_URL` = URL du backend (`https://<service>.onrender.com`), appelée côté serveur par `/api/chat`.
- `NEXT_PUBLIC_WS_URL` = `wss://<service>.onrender.com`. Cette variable est figée dans le bundle
  au build : redéployer le front si l'URL du backend change.
- La protection « Vercel Authentication » doit être désactivée pour que la démo soit publique.
- `output: "standalone"` (`next.config.js`) est ignoré par Vercel et ne gêne pas son build.

### Limites du plan gratuit

- **Mise en veille** : Render Free endort le service après ≈ 15 min sans trafic ; le premier appel
  suivant prend ≈ 50 s (réveil + chargement).
- **Mémoire** : 512 Mo côté Render, d'où le recours à Qdrant Cloud pour le RAG.
- **Quotas** : la limite par IP et le plafond journalier sont en mémoire (une seule instance) et
  repartent de zéro à chaque redémarrage. Au-delà, le backend répond 429. Les quotas gratuits de
  Gemini et de Qdrant Cloud s'appliquent aussi.
- **Mode vocal** : le navigateur ouvre directement `wss://<backend>/ws/voice` et a besoin d'un micro.

## Captures

<!-- TODO: ajouter des captures d'écran / une démo du chat et du mode vocal -->
