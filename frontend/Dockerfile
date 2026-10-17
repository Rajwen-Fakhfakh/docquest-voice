FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* est lu par le navigateur : il doit être figé dans le bundle au build,
# pas seulement passé à `docker run` (voir docker-compose.yml `build.args`).
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
RUN npm run build

# `output: "standalone"` (next.config.js) : l'image finale n'a besoin que de ce dossier,
# pas de node_modules complet.
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# Le mode standalone ne recopie pas public/ (PDF du DEU servi en statique).
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
