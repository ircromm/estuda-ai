FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory for SQLite. If Railway volume is mounted at /app/data,
# it will override this. Otherwise, data is ephemeral (lost on redeploy).
RUN mkdir -p /app/data

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
