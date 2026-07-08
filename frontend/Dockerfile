# syntax=docker/dockerfile:1.7
FROM node:24-alpine

ARG PNPM_VERSION=11.9.0
ARG REGISTRY_STRICT_SSL=false

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
ENV NPM_CONFIG_STRICT_SSL=$REGISTRY_STRICT_SSL
ENV PNPM_CONFIG_STRICT_SSL=$REGISTRY_STRICT_SSL

WORKDIR /app
RUN npm install -g pnpm@${PNPM_VERSION}
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=knetraai-frontend-pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir /pnpm/store
COPY . .
RUN pnpm run build

EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
