FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: check yesterday (UTC) for betika. Override CMD at Cloud Run Job
# creation time (or via --date) for a backfill / different client.
CMD ["python", "main.py", "--client", "betika"]
