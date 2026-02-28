# Backend Setup Guide — Kairos · Beyond Stars

This document covers the complete setup process for the Kairos Django Backend — installation, configuration, database setup, email configuration, and the full `manage.py` command reference.

---

## 📋 Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation Steps](#2-installation-steps)
3. [Environment Configuration](#3-environment-configuration)
4. [Database Setup](#4-database-setup)
5. [manage.py Command Reference](#5-managepy-command-reference)
6. [Email Configuration](#6-email-configuration)
7. [Running the Backend](#7-running-the-backend)
8. [Common Issues](#8-common-issues)
9. [Related Documents](#related-documents)

---

## 1. Prerequisites

| Tool | Minimum Version | Purpose |
|------|----------------|---------|
| Python | 3.11 | Runtime |
| pip | 23+ | Package manager |
| virtualenv / venv | built-in | Isolated environment |
| SQLite | 3.35+ | Default development database (bundled with Python) |
| Mailhog | any | Local SMTP server for email testing |

**Install Mailhog for local email testing:**

```bash
# macOS
brew install mailhog

# Linux
go install github.com/mailhog/MailHog@latest

# Docker
docker run -d -p 1025:1025 -p 8025:8025 mailhog/mailhog
```

---

## 2. Installation Steps

```bash
# 1. Navigate to the Backend directory
cd /path/to/Kairos-Beyond-Stars/Backend

# 2. Create a Python virtual environment
python3 -m venv .venv

# 3. Activate the virtual environment
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\activate             # Windows PowerShell

# 4. Install all dependencies
pip install -r requirements.txt

# 5. Apply database migrations
python manage.py migrate

# 6. Create a superuser (optional, for Django admin panel)
python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver 0.0.0.0:8000
```

The Backend will be available at `http://localhost:8000`.

---

## 3. Environment Configuration

The Backend reads its configuration from `beyondstars_backend/settings.py`. For production, these values must be moved to environment variables.

### Current settings (hardcoded — must fix before production)

| Setting | Current Value | Required Change |
|---------|---------------|----------------|
| `SECRET_KEY` | Hardcoded string | Move to `os.environ['DJANGO_SECRET_KEY']` |
| `DEBUG` | `True` | Set to `False` in production |
| `ALLOWED_HOSTS` | `["*"]` | Replace with specific domain list |
| `DATABASES['default']` | SQLite3 `db.sqlite3` | Replace with PostgreSQL in production |

### CORS configuration

The `CORS_ALLOWED_ORIGINS` list controls which Frontend origins can make cross-origin requests. Update this for your production Frontend URL:

```python
# In settings.py
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",            # Local Frontend
    "https://kairos.gokulp.online",     # Production Frontend
]
```

### Service token for Agent calls

The Backend passes `SERVICE_TOKEN` to the Agent for all inter-service calls. This must match the Agent's `SERVICE_TOKEN` environment variable exactly:

```python
# In settings.py or env var
AGENT_SERVICE_TOKEN = os.environ.get("SERVICE_TOKEN", "dev-token-replace-in-prod")
AGENT_BASE_URL = os.environ.get("AGENT_BASE_URL", "http://localhost:4021")
```

---

## 4. Database Setup

### Development (SQLite3)

SQLite3 is the default database for development. No configuration is needed — the `db.sqlite3` file is created automatically.

```bash
# Apply all migrations
python manage.py migrate

# View current migration state
python manage.py showmigrations
```

### Production (PostgreSQL)

Replace the `DATABASES` setting:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}
```

Install the PostgreSQL adapter:

```bash
pip install psycopg2-binary
```

---

## 5. `manage.py` Command Reference

| Command | Description | When to Use |
|---------|-------------|-------------|
| `migrate` | Apply all pending migrations | After setting up or after pulling new migration files |
| `makemigrations` | Generate new migration files from model changes | After editing `core/models.py` |
| `showmigrations` | List all migrations and their applied status | Audit/debug |
| `createsuperuser` | Create a Django admin superuser | First-time setup |
| `runserver [port]` | Start development server with auto-reload | Local development |
| `shell` | Open interactive Django shell with all models imported | Debugging, quick queries |
| `dbshell` | Open the database CLI attached to `DATABASES['default']` | Direct SQL queries |
| `check` | Validate the Django project for configuration errors | CI/pre-deploy |
| `collectstatic` | Gather static files to `STATIC_ROOT` | Production deployment only |

### Useful shell commands

```bash
# Open Django shell
python manage.py shell

# Example: Inspect all users
>>> from core.models import User
>>> User.objects.all().values("email", "is_verified", "auth_token")
```

---

## 6. Email Configuration

The Backend uses SMTP to send email verification links. For local development, use Mailhog to capture outbound emails without actually sending them.

### Settings (in `settings.py`)

```python
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "localhost"
EMAIL_PORT = 2525        # Mailhog SMTP port
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False
DEFAULT_FROM_EMAIL = "noreply@kairos.com"
```

**Access captured emails** at `http://localhost:8025` in your browser (Mailhog web UI).

### Production SMTP

Replace with a real SMTP provider (SendGrid, SES, Mailgun):

```python
EMAIL_HOST = "smtp.sendgrid.net"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "apikey"
EMAIL_HOST_PASSWORD = os.environ["SENDGRID_API_KEY"]
```

---

## 7. Running the Backend

### Development

```bash
cd Backend
source .venv/bin/activate
python manage.py runserver 0.0.0.0:8000
```

### Production (Gunicorn)

```bash
cd Backend
source .venv/bin/activate
gunicorn beyondstars_backend.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --worker-class sync \
    --timeout 120 \
    --log-level info
```

### Via Docker Compose

```bash
# From the repository root
docker compose up backend
```

---

## 8. Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `django.db.utils.OperationalError: no such table: core_user` | Migrations not applied | Run `python manage.py migrate` |
| `ModuleNotFoundError: No module named 'rest_framework'` | Missing dependencies | Run `pip install -r requirements.txt` |
| Emails not received locally | Mailhog not running | Start Mailhog; check `EMAIL_PORT=2525` in settings |
| `CORS policy error` from Frontend | Origin not in `CORS_ALLOWED_ORIGINS` | Add `http://localhost:3000` to `CORS_ALLOWED_ORIGINS` in settings.py |
| Agent 401 Unauthorized on sync call | `SERVICE_TOKEN` mismatch | Ensure Backend and Agent use the same token value |
| `Invalid secret key` warning | Using default DEBUG key | Set a unique `SECRET_KEY` before production |

---

## Related Documents

- [Backend/README.md](../README.md) — Backend module entry point
- [Backend/docs/ARCHITECTURE.md](ARCHITECTURE.md) — Django module graph and component reference
- [Backend/docs/API.md](API.md) — Full endpoint reference
- [Backend/docs/DATABASE.md](DATABASE.md) — Database schema and migrations
- [docs/SETUP.md](../../docs/SETUP.md) — Full project setup (all modules)
