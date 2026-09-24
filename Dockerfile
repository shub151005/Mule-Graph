FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=7860 MULEGRAPH_DATA_DIR=/app/runtime
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
COPY backend/constraints.txt /app/backend/constraints.txt
RUN pip install -r /app/backend/requirements.txt && useradd --create-home --uid 1000 appuser && mkdir /app/runtime && chown appuser:appuser /app/runtime
COPY --chown=appuser:appuser backend /app/backend
USER appuser
EXPOSE 7860
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
