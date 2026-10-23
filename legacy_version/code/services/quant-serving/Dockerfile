FROM python:3.12.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY packages/contracts /app/packages/contracts
COPY packages/service-auth /app/packages/service-auth
COPY packages/portfolio-core /app/packages/portfolio-core
COPY services/quant-serving /app/services/quant-serving
RUN python -m pip install -c /app/services/quant-serving/requirements.lock /app/packages/contracts /app/packages/service-auth /app/packages/portfolio-core /app/services/quant-serving \
    && useradd --system --uid 10001 --create-home service
USER service
EXPOSE 8000
CMD ["uvicorn", "quant_service.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
