FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY careerflow/ ./careerflow/
RUN pip install --no-cache-dir ".[documents]"
COPY web-platform/ ./web-platform/
RUN pip install --no-cache-dir ./web-platform
ENV PYTHONPATH=/app/web-platform/document-worker:/app/web-platform:/app
WORKDIR /app/web-platform
RUN useradd --create-home --uid 10002 document && chown -R document:document /app
USER document
EXPOSE 8081
CMD ["uvicorn", "document_worker.main:app", "--app-dir", "document-worker", "--host", "0.0.0.0", "--port", "8081", "--proxy-headers"]

