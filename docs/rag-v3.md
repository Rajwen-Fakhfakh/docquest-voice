# V3 — RAG (Retrieval-Augmented Generation)

Document de révision : comprendre le RAG et comment LangChain est utilisé dans DocQuest.

## 1. Le problème

Le DEU 2025 de TotalEnergies fait ~666 pages. Un LLM ne le connaît pas par cœur et il est trop
long pour tenir dans chaque prompt. Sans RAG, Gemini répond de mémoire (risque d'inventer).

## 2. L'idée du RAG

> Avant de répondre, on **retrouve** les passages pertinents du document et on les **donne** au LLM.

Deux phases :

```
INDEXATION (une fois)                      REQUÊTE (à chaque question)
PDF                                        Question de l'utilisateur
 └─ texte par page          (pypdf)         └─ embedding de la question
     └─ chunks de ~1000 car. (splitter)         └─ chunks les plus proches (top 5)
         └─ embedding de chaque chunk              └─ injectés dans le prompt système
             └─ index sauvé en JSON                    └─ Gemini répond + cite la page
```

## 3. Concepts clés

- **Chunk** : petit morceau de texte (~1000 caractères, 150 de chevauchement). Trop gros =
  réponse noyée ; trop petit = contexte perdu. Le chevauchement évite de couper une idée en deux.
- **Embedding** : un texte devient un vecteur de nombres (modèle `gemini-embedding-001`).
  Deux textes de sens proche ont des vecteurs proches.
- **Similarité** : on compare le vecteur de la question à ceux des chunks (cosinus) et on garde
  les `top_k` plus proches. C'est de la recherche *sémantique* (pas de mots-clés exacts).
- **Vector store** : la « base » qui stocke chunks + vecteurs et sait chercher les plus proches.
  Ici `InMemoryVectorStore` : en mémoire, sauvé/chargé via un fichier JSON. Zéro serveur.
  Pour de la prod : Chroma, pgvector, Qdrant… (même interface LangChain).
- **Métadonnées** : on stocke le numéro de page avec chaque chunk → le LLM peut citer `(p. 12)`.

## 4. LangChain : les briques utilisées

| Brique | Rôle | Où |
|---|---|---|
| `Document` | texte + métadonnées (`page_content`, `metadata`) | `rag.py` |
| `RecursiveCharacterTextSplitter` | découpe en chunks (essaie paragraphes, puis phrases, puis mots) | `split_documents` |
| `GoogleGenerativeAIEmbeddings` | transforme texte en vecteur via Gemini | `deps.py`, `ingest.py` |
| `InMemoryVectorStore` | stocke et cherche (`add_documents`, `asimilarity_search`, `dump`, `load`) | `rag.py` |
| `ChatGoogleGenerativeAI` | le LLM (déjà là depuis V1) | `providers/gemini.py` |

Note : on n'utilise **pas** de « chain » LangChain ici. Le pipeline est écrit à la main
(chercher → construire le prompt → appeler le LLM) : plus simple à lire et à déboguer.
LangChain fournit les briques, pas l'orchestration.

## 5. Fichiers

- `backend/app/core/rag.py` — chargement PDF, découpage, indexation, `Retriever`, mise en forme.
- `backend/scripts/ingest.py` — script d'indexation (à lancer une fois).
- `backend/app/core/chat.py` — `ChatService` : cherche les extraits puis enrichit le prompt système.
- `backend/app/api/deps.py` — charge l'index au démarrage (si présent) et l'injecte dans le service.
- `backend/app/core/config.py` — réglages : modèle d'embeddings, chemin PDF/index, `rag_top_k`.
- `backend/tests/test_rag.py` — tests avec embeddings factices (aucun appel réseau).

## 6. Utilisation

L'index prêt à l'emploi est versionné : `backend/data/index.json.gz` (2899 chunks avec leurs
embeddings, ~28 Mo) et `backend/data/chunks.jsonl` (texte découpé, source pour tout régénérer).
**Après un `git clone`, il n'y a rien à indexer** : il suffit de renseigner `GEMINI_API_KEY` dans
le `.env` et de lancer le backend. La clé sert encore à embedder chaque question (1 requête).

Pour régénérer l'index (autre document, autre modèle d'embeddings) :

```bash
cd backend
# chunks.jsonl dans backend/data/ (ou le PDF en secours), GEMINI_API_KEY dans le .env
.venv\Scripts\python scripts/ingest.py     # produit backend/data/index.json.gz
```

L'ingestion est reprenable (`index.json.gz.partial`) et bascule sur les clés de
`GEMINI_API_KEYS_EXTRA` quand le quota gratuit journalier (1000 requêtes) est épuisé.
Les vecteurs sont arrondis à 6 décimales et compressés en gzip (190 Mo -> 28 Mo).

Sans index, le chat fonctionne comme avant (sans RAG) : pas de plantage.

### Qdrant Cloud (optionnel)

Si `QDRANT_URL` (et `QDRANT_API_KEY`) sont dans le `.env`, la recherche interroge Qdrant au lieu
du fichier local (`Retriever.from_qdrant`, `QdrantVectorStore`). Collection : `QDRANT_COLLECTION`
(défaut `deu2025`). Pour la remplir à partir de `index.json.gz`, sans nouvel appel d'embedding :

```bash
cd backend
.venv\Scripts\python scripts/upload_qdrant.py   # relançable : mêmes ids, pas de doublons
```

Sans `QDRANT_URL`, on retombe sur l'index local. Le plan gratuit Qdrant supprime un cluster
inactif ; relancer le script suffit à recréer la collection.

## 7. Flux détaillé d'une question

1. `POST /chat` → `ChatService.reply(messages)`.
2. `_build_system_prompt` prend le **dernier message utilisateur** comme requête.
3. `Retriever.search` → embedding de la question → 5 chunks les plus proches.
4. Prompt système = consigne de base + « EXTRAITS : [page 12] … [page 40] … ».
5. Gemini répond en s'appuyant sur ces extraits et cite les pages.

## 8. Limites connues / pistes (V4+)

- Recherche sur la dernière question seule : « et en 2024 ? » (suite de conversation) retrouve mal.
  Piste : réécrire la question avec l'historique avant la recherche.
- Tableaux et graphiques du PDF mal extraits par `pypdf` (texte à plat).
- `InMemoryVectorStore` : tout en RAM, recherche linéaire. OK pour quelques milliers de chunks ;
  au-delà, passer à une vraie base vectorielle.
- Le mode vocal (Gemini Live) n'utilise pas encore le RAG.
- Pas de re-ranking ni de recherche hybride (mots-clés + sémantique).
- Quotas Gemini gratuits : `ingest.py` envoie 40 chunks par lot avec 30 s de pause (limite gratuite : 100/min, ~45 min pour le DEU) et réessaie sur 429 ; ajuster
  `BATCH_SIZE`/`BATCH_PAUSE_SECONDS` dans `rag.py` en cas d'erreur 429.
