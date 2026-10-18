FROM node:22-alpine AS dependencies
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
# Check/build stages always need development tools, even when npm defaults omit them.
RUN npm ci --include=dev \
    && node -e "if(require('typescript/package.json').name !== 'typescript') process.exit(1)" \
    && ./node_modules/.bin/eslint --version \
    && ./node_modules/.bin/tsc --version

FROM dependencies AS check
COPY . .
CMD ["npm", "run", "check"]

FROM check AS builder
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
