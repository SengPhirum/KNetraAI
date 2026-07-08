# syntax=docker/dockerfile:1.7
FROM node:24-alpine AS deps

ARG PNPM_VERSION=11.9.0
ARG REGISTRY_STRICT_SSL=false

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
ENV NPM_CONFIG_STRICT_SSL=$REGISTRY_STRICT_SSL
ENV PNPM_CONFIG_STRICT_SSL=$REGISTRY_STRICT_SSL

WORKDIR /app
RUN npm install -g pnpm@${PNPM_VERSION}
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN --mount=type=cache,id=knetraai-frontend-pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir /pnpm/store

FROM deps AS builder
WORKDIR /app
COPY frontend/ ./
RUN pnpm run build

FROM node:24-alpine AS runner
ENV NODE_ENV=production \
    NITRO_HOST=0.0.0.0 \
    NITRO_PORT=3000

WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=builder --chown=app:app /app/.output ./.output

USER app
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", ".output/server/index.mjs"]
