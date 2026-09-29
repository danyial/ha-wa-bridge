FROM node:22-trixie-slim

# System Chromium: Google ships no Linux arm64 Chrome, and puppeteer's own
# download is skipped (PUPPETEER_EXECUTABLE_PATH is set).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        fonts-freefont-ttf \
        fonts-ipafont-gothic \
        fonts-kacst \
        fonts-thai-tlwg \
        fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_DOWNLOAD=1 \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    NODE_ENV=production

WORKDIR /usr/src/app

COPY package.json package-lock.json ./
# --ignore-scripts: the only install script is puppeteer's browser download.
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force

COPY . .
RUN chmod +x run.sh

# io.hass.* labels are set by the Home Assistant builder (CI) or by the
# Supervisor when it builds the image locally.
LABEL \
    org.opencontainers.image.source="https://github.com/danyial/ha-wa-bridge" \
    org.opencontainers.image.licenses="MIT"

EXPOSE 3000

CMD [ "./run.sh" ]
