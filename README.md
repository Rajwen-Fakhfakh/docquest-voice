# DocQuest Voice

[![CI](https://github.com/Rajwen-Fakhfakh/docquest-voice/actions/workflows/ci.yml/badge.svg)](https://github.com/Rajwen-Fakhfakh/docquest-voice/actions/workflows/ci.yml)

Assistant conversationnel (texte + voix) sur le Document d'Enregistrement Universel (DEU)
2025 de TotalEnergies, avec RAG (Retrieval-Augmented Generation) pour ancrer les réponses
dans le document plutôt que dans la mémoire du modèle.

**Démo en ligne : [docquest-voice.vercel.app](https://docquest-voice.vercel.app)** — essayez par
exemple « Quel est le dividende proposé par action pour 2025 ? ». Le premier appel peut prendre
une cinquantaine de secondes (le backend gratuit se réveille), voir [Déploiement](#déploiement).

## Architecture

```text
Navigateur ──► Next.js (Vercel) ── /api/chat ──► FastAPI (Render) ──► Gemini (chat)
     │                                               │
     │ WebSocket /ws/voice (direct)                  └──► Qdrant Cloud (RAG)
     └───────────────────────────────────────────────►    Gemini Live (voix)
                                                          (outil search_deu ──► même RAG)
```

- **Backend** (`backend/`) : FastAPI + Gemini (`google-genai`). Expose `POST /chat`,
  `POST /chat/stream`, `GET /health` et le WebSocket `/ws/voice` (mode vocal, Gemini Live).
  Une limite de débit en mémoire (par IP et par jour) protège le quota Gemini de la démo publique.
- **Frontend** (`frontend/`) : Next.js (App Router). `ChatShell` pilote le chat texte
  (streaming via `/api/chat`, un proxy serveur vers le backend) et le mode vocal (WebSocket
  direct vers le backend, micro + lecture audio).
- **RAG** : chunks du DEU indexés avec `gemini-embedding-001`, recherche par similarité
  cosinus, extraits injectés dans le prompt système, pages citées dans la réponse. Les vecteurs
  sont dans **Qdrant Cloud** (collection `deu2025`) quand `QDRANT_URL` est défini ; sinon le
  backend charge l'index local versionné (`backend/data/index.json.gz`, ≈ 190 Mo en mémoire),
  ce qui permet de tout lancer après un simple clone. Le mode vocal utilise le même retriever :
  Gemini Live appelle l'outil `search_deu` et reçoit les extraits du DEU avec leur page.
  Détails : [`docs/rag-v3.md`](docs/rag-v3.md).

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
  - `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` — Qdrant Cloud pour le RAG (optionnel :
    sans `QDRANT_URL`, l'index local est utilisé). `python scripts/upload_qdrant.py` charge la collection.
  - `RATE_LIMIT_PER_MINUTE`, `DAILY_REQUEST_CAP` — requêtes par minute et par IP, et plafond
    global par jour (`0` = désactivé). Défauts : 20 et 500.
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

### Secrets

Aucun workflow n'a besoin de secret (tests avec doublures, index RAG déjà commité). Les clés
(`GEMINI_API_KEY`, `QDRANT_API_KEY`) ne sont requises qu'**à l'exécution**. Les **secrets GitHub
Actions** ne servent qu'aux workflows : Render et Vercel ne les lisent pas. Sur Render, les clés
se définissent comme variables d'environnement du service (voir [Déploiement](#déploiement)).
Render et Vercel redéploient automatiquement à chaque push sur leur branche, indépendamment du
workflow CD, qui se contente de publier les images Docker.

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

<!-- TODO: ajouter une capture ou un GIF du chat (réponse avec pages citées) et du mode vocal,
     par exemple dans docs/img/, puis les référencer ici. -->

## Diagramme d'architecture

[Ouvrir le diagramme interactif](https://htmlpreview.github.io/?https://github.com/Rajwen-Fakhfakh/docquest-voice/blob/main/docs/architecture-docquest.html)
([`docs/architecture-docquest.html`](docs/architecture-docquest.html), à ouvrir dans un navigateur
après un clone).
