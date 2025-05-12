FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
# ENV SCRAPER_SERVICE_URL=http://zara-scraper:5002/api/scrape
ENV ZARA_SCRAPER_URL=http://zara-scraper:5002/api/scrape
ENV HM_SCRAPER_URL=http://hm-scraper:5003/api/scrape

# Create directory for temporary files
RUN mkdir -p /root/fashion_finder_tmp

# Create gunicorn config file
RUN echo 'timeout = 300\nworkers = 1\nthreads = 2\nworker_class = "gthread"' > gunicorn_config.py

# Run gunicorn with increased timeout and single worker
CMD ["gunicorn", "--config", "gunicorn_config.py", "--bind", "0.0.0.0:5001", "app:app"]