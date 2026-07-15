# Multi-stage Dockerfile for Leasora Next.js frontend

# Stage 1: Dependencies
FROM node:24-alpine AS deps
WORKDIR /app
RUN npm install -g pnpm
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/package.json ./apps/web/
COPY packages/ts-config ./packages/ts-config
COPY packages/shared-types ./packages/shared-types
RUN pnpm install --frozen-lockfile --prod=false


# Stage 2: Builder
FROM node:24-alpine AS builder
WORKDIR /app
RUN npm install -g pnpm
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=deps /app/packages ./packages
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web ./apps/web

# Build frontend
WORKDIR /app/apps/web
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN pnpm build


# Stage 3: Development (optional, for docker-compose.dev.yml)
FROM node:24-alpine AS development
WORKDIR /app
RUN npm install -g pnpm
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/package.json ./apps/web/
COPY packages/ts-config ./packages/ts-config
COPY packages/shared-types ./packages/shared-types
COPY apps/web ./apps/web
RUN pnpm install --frozen-lockfile
WORKDIR /app/apps/web
EXPOSE 3000
CMD ["pnpm", "dev"]


# Stage 4: Production
FROM node:24-alpine AS production
WORKDIR /app

# Create non-root user
RUN adduser -D -u 1000 leasora && \
    chown -R leasora:leasora /app

# Install production dependencies only
RUN npm install -g pnpm
COPY --chown=leasora:leasora pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY --chown=leasora:leasora apps/web/package.json ./apps/web/
COPY --chown=leasora:leasora packages/ts-config ./packages/ts-config
COPY --chown=leasora:leasora packages/shared-types ./packages/shared-types

# Install only production deps
RUN pnpm install --frozen-lockfile --prod=true

# Copy built application from builder
COPY --from=builder --chown=leasora:leasora /app/apps/web/.next ./apps/web/.next
COPY --chown=leasora:leasora apps/web/next.config.js ./apps/web/

# Switch to non-root user
USER leasora

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/health || exit 1

EXPOSE 3000

WORKDIR /app/apps/web
ENV NODE_ENV=production

CMD ["pnpm", "start"]
