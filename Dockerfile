# Base image
FROM python:3.14-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Serve static files
RUN mkdir -p /app/staticfiles

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Command to run the application
# Gunicorn flag'lari:
#  --workers 2: 2 ta worker process (2 CPU core uchun)
#  --threads 4: har worker'da 4 thread (I/O-bound view'lar uchun)
#  --timeout 120: 30s default kichik — monitoring va Excel eksport uchun 120s
#  --graceful-timeout 30: SIGTERM'dan keyin 30s kutadi
#  --keep-alive 5: connection alive 5s
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]