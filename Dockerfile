FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY main.py .

EXPOSE 8080

# Use sh -c so the PORT env var is expanded. Defaults to 8080 if PORT is not set.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
