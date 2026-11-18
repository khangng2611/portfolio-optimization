FROM python:3.12.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/quant-serving/requirements.lock /app/requirements.lock
COPY services/auth /app/services/auth
RUN python -m pip install -c requirements.lock /app/services/auth \
    && useradd --system --uid 10001 --create-home service
USER service
EXPOSE 8000
CMD ["uvicorn", "auth_service.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
