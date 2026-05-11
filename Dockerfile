FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Then copy the rest of the source.
COPY app/ ./app/
COPY webapp_static/ ./webapp_static/
COPY main.py ./

EXPOSE 8000

# Run via uvicorn so the FastAPI lifespan boots the bot polling task.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
