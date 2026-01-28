FROM python:3.11-slim

WORKDIR /app

# Dipendenze di sistema
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Installa dipendenze Python
RUN pip install --no-cache-dir -r requirements.txt

# Copy applicazione
COPY . .

# Espone porta
EXPOSE 5000

# Entry point: avvia API REST
CMD ["python", "-m", "backend.api_rest"]
