# Encefalus web — TanStack Start compiled by nitro to a Node server.
# bun.lock is the authoritative lockfile (package-lock.json was stale).
FROM oven/bun:1 AS build
WORKDIR /app
COPY package.json bun.lock bunfig.toml ./
RUN bun install --frozen-lockfile
COPY . .
RUN bun run build

# Runtime: trixie base like the rest of the fleet (the fleet's Debian 13
# .snyk policy applies), and no npm/yarn — nothing here uses them (the app
# is a bundled .mjs), and their manifests make Snyk scan phantom npm
# projects that are not part of the shipped runtime.
FROM node:22-trixie-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NITRO_PORT=3000
RUN apt-get update && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
        /opt/yarn* \
        /usr/local/lib/node_modules/npm \
        /usr/local/lib/node_modules/corepack \
        /usr/local/bin/npm \
        /usr/local/bin/npx \
        /usr/local/bin/yarn \
        /usr/local/bin/yarnpkg \
        /usr/local/bin/corepack
COPY --from=build /app/.output ./.output
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://localhost:'+(process.env.NITRO_PORT||3000)+'/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", ".output/server/index.mjs"]
