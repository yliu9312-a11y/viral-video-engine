FROM node:20-bookworm

# Install ffmpeg (required by Remotion for video encoding)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy monorepo structure needed for rendering
COPY package.json ./
COPY services/node/package.json services/node/
COPY web/package.json web/

# Install all dependencies
RUN cd services/node && npm install --production=false
RUN cd web && npm install --production=false

# Copy source code
COPY services/node/ services/node/
COPY web/ web/
COPY scripts/ scripts/

ENV NODE_ENV=production
ENV PYTHON_URL=http://python:8000
ENV PROJECT_ROOT=/app
# Tell Remotion where to find Chrome (bundled by @remotion/cli)
ENV PUPPETEER_SKIP_DOWNLOAD=true

EXPOSE 3000

CMD ["npx", "tsx", "services/node/src/index.ts"]
