FROM node:22.22.2-bookworm-slim@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e
ARG PLAYWRIGHT_VERSION
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npm install --global --no-audit --no-fund "playwright@${PLAYWRIGHT_VERSION}" \
    && playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm
USER node
CMD ["playwright", "run-server", "--host", "0.0.0.0", "--port", "3000"]
