FROM python:3.12.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY packages/contracts /app/packages/contracts
COPY packages/service-auth /app/packages/service-auth
COPY packages/service-observability /app/packages/service-observability
COPY services/market-data /app/services/market-data
RUN python -m pip install -c /app/services/market-data/requirements.lock /app/packages/contracts /app/packages/service-auth /app/packages/service-observability /app/services/market-data \
    && useradd --system --uid 10001 --create-home service
USER service
EXPOSE 8000
CMD ["uvicorn", "market_service.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
