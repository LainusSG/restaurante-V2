#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PY'
import os
import socket
import time
from urllib.parse import urlparse

database_url = os.getenv("DATABASE_URL", "")
if database_url:
    parsed_url = urlparse(database_url)
    host = parsed_url.hostname
    default_port = 5432 if parsed_url.scheme.startswith("postgres") else 3306
    port = parsed_url.port or default_port
else:
    engine = os.getenv("DB_ENGINE", "").lower()
    host = (
        os.getenv("DB_HOST")
        or os.getenv("MYSQL_HOST")
        or os.getenv("POSTGRES_HOST")
    )
    if not host and engine not in {"mysql", "postgresql", "postgres"}:
        raise SystemExit(0)
    host = host or "db"
    default_port = "5432" if engine in {"postgresql", "postgres"} else "3306"
    port = int(
        os.getenv("DB_PORT")
        or os.getenv("MYSQL_PORT")
        or os.getenv("POSTGRES_PORT")
        or default_port
    )

if not host:
    raise SystemExit("Database host is not configured.")

while True:
    try:
        with socket.create_connection((host, port), timeout=3):
            break
    except OSError:
        time.sleep(1)
PY

echo "Applying migrations..."
python manage.py migrate --no-input

echo "Creating default admin user if needed..."
python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.getenv("DJANGO_SUPERUSER_USERNAME", "Admin")
email = os.getenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "Admin2026")

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"Superuser created: {username}")
else:
    print(f"Superuser already exists: {username}")
PY

echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Starting server..."
exec gunicorn --env DJANGO_SETTINGS_MODULE=restaurante.settings restaurante.wsgi:application --bind 0.0.0.0:${PORT:-8000}
