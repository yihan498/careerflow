FROM node:22-alpine AS frontend
WORKDIR /build
COPY web-platform/frontend/package*.json ./
RUN npm ci
COPY web-platform/frontend/ ./
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_TURNSTILE_SITE_KEY
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY careerflow/ ./careerflow/
RUN pip install --no-cache-dir ".[pdf]"
COPY web-platform/ ./web-platform/
RUN pip install --no-cache-dir ./web-platform
COPY --from=frontend /build/dist ./web-platform/frontend/dist
WORKDIR /app/web-platform
RUN useradd --create-home --uid 10001 careerflow && chown -R careerflow:careerflow /app
USER careerflow
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
