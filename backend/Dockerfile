# WORKDIR imite l'arborescence du dépôt (backend/app/core/config.py cherche le `.env` 3
# dossiers au-dessus de lui) : docker-compose injecte les variables via `env_file`, le
# fichier n'a donc pas besoin d'être copié dans l'image.
FROM python:3.11-slim
WORKDIR /srv/backend

COPY pyproject.toml ./
COPY app ./app
# Seul l'index déjà calculé est nécessaire pour servir le chat (voir docs/rag-v3.md §6) :
# le PDF et les chunks bruts ne servent qu'à régénérer l'index, inutiles ici.
COPY data/index.json.gz ./data/index.json.gz

RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
