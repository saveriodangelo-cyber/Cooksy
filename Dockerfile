FROM python:3.11-slim

WORKDIR /app

# Copy solo requirements leggeri per API
COPY requirements-api.txt .

# Installa dipendenze Python minime
RUN pip install --no-cache-dir -r requirements-api.txt

# Copy applicazione
COPY . .

# Espone porta
EXPOSE 5000

# Entry point: avvia API REST
CMD ["python", "-m", "backend.api_rest"]
