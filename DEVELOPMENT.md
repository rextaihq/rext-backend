# Development Setup Guide

This guide provides cross-platform instructions for setting up the Wrext backend for local development on **macOS**, **Windows**, and **Linux**.

## Prerequisites

### Required (All Platforms)
- **Docker Desktop** (or Docker Engine on Linux)
  - macOS: [Download Docker Desktop](https://www.docker.com/products/docker-desktop/)
  - Windows: [Download Docker Desktop](https://www.docker.com/products/docker-desktop/)
  - Linux: `sudo apt-get install docker.io docker-compose` (Ubuntu/Debian)

- **Python 3.11+**
  - macOS: `brew install python@3.11` or download from [python.org](https://www.python.org)
  - Windows: Download from [python.org](https://www.python.org)
  - Linux: `sudo apt-get install python3.11 python3.11-venv`

- **PostgreSQL** (for local development without Docker)
  - macOS: `brew install postgresql@16` or use [Postgres.app](https://postgresapp.com/)
  - Windows: [Download installer](https://www.postgresql.org/download/windows/)
  - Linux: `sudo apt-get install postgresql-16`

## Quick Start (Docker - Recommended)

This is the **recommended approach** as it works identically on all platforms and matches production.

### 1. Start Infrastructure Services

```bash
# Start Redis and PostgreSQL (if using Docker for databases)
docker-compose up -d redis langgraph-redis

# Verify services are running
docker-compose ps
```

### 2. Setup Python Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# macOS/Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat

# Install dependencies
pip install -e .
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
# Make sure these are set:
# - REDIS_URL=redis://localhost:6379/0
# - POSTGRES_URI_CUSTOM=postgresql://localhost/your_db_name
# - CACHE_ENABLED=false  (or true if you want caching)
```

### 4. Run Database Migrations

```bash
# Apply migrations
.venv/bin/alembic upgrade head
```

### 5. Start the Server

**Option A: FastAPI only (no LangGraph)**
```bash
# macOS/Linux:
.venv/bin/python -m uvicorn src.api.server:app --host 0.0.0.0 --port 2024 --reload

# Windows:
.venv\Scripts\python -m uvicorn src.api.server:app --host 0.0.0.0 --port 2024 --reload
```

**Option B: With LangGraph**
```bash
# macOS/Linux:
.venv/bin/langgraph dev

# Windows:
.venv\Scripts\langgraph dev
```

### 6. Verify Server is Running

Open your browser to:
- **API Docs**: http://localhost:2024/docs
- **Health Check**: http://localhost:2024/health

---

## Development Without Docker

If you prefer to install services natively:

### Install Redis

**macOS:**
```bash
brew install redis
brew services start redis
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

**Windows:**
- Download from [Redis Windows port](https://github.com/tporadowski/redis/releases)
- Or use [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) and install Redis inside WSL

### Install PostgreSQL

**macOS:**
```bash
brew install postgresql@16
brew services start postgresql@16
createdb your_db_name
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install postgresql-16
sudo systemctl start postgresql
sudo -u postgres createdb your_db_name
```

**Windows:**
1. Download installer from [postgresql.org](https://www.postgresql.org/download/windows/)
2. Run installer and follow prompts
3. Use pgAdmin or command line to create database

Then follow steps 2-6 from Quick Start above.

---

## Configuration Reference

### Environment Variables (.env)

```bash
# Server
HOST=0.0.0.0
PORT=2024

# Database (adjust based on your setup)
POSTGRES_URI_CUSTOM=postgresql://localhost/your_db_name

# Redis Configuration
REDIS_URL=redis://localhost:6379/0           # For application cache
REDIS_URI=redis://langgraph-redis:6379        # For LangGraph (Docker)
CACHE_ENABLED=false                            # Set to true to enable caching

# Security (REQUIRED - generate secure keys!)
SECRET_KEY=<generate-with-scripts/generate_jwt_secret.py>
REFRESH_SECRET_KEY=<generate-with-scripts/generate_jwt_secret.py>
ALGORITHM=HS256

# Frontend
FRONTEND_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Environment
ENVIRONMENT=development
DEBUG=false
```

### Generate Secure Keys

```bash
# macOS/Linux:
.venv/bin/python scripts/generate_jwt_secret.py

# Windows:
.venv\Scripts\python scripts\generate_jwt_secret.py
```

---

## Troubleshooting

### Connection Refused Errors

**Symptom:** `[Errno 61] Connection refused` or similar

**Solutions:**

1. **Redis not running:**
   ```bash
   # Check if Redis is running
   docker ps | grep redis
   # Or natively:
   redis-cli ping  # Should return PONG
   ```

2. **PostgreSQL not running:**
   ```bash
   # Check if PostgreSQL is running
   # macOS:
   brew services list | grep postgresql
   # Linux:
   sudo systemctl status postgresql
   # Windows:
   # Check Services app for PostgreSQL service
   ```

3. **Wrong connection string:**
   - If using Docker: `redis://localhost:6379/0`
   - If using Docker Compose network: `redis://redis:6379/0`
   - Check `.env` file has correct connection strings

### Port Already in Use

**Symptom:** `Address already in use` when starting server

**Solution:**
```bash
# Find what's using the port
# macOS/Linux:
lsof -i :2024
# Windows:
netstat -ano | findstr :2024

# Kill the process or change PORT in .env
```

### Migration Errors

**Symptom:** Database schema errors

**Solution:**
```bash
# Reset migrations (DEVELOPMENT ONLY - destroys data!)
.venv/bin/alembic downgrade base
.venv/bin/alembic upgrade head

# Or recreate database
dropdb your_db_name && createdb your_db_name
.venv/bin/alembic upgrade head
```

---

## Production Deployment

For production, use Docker containers:

```bash
# Build production image
docker build -t wrext-backend:latest .

# Run with docker-compose
docker-compose -f docker-compose.prod.yml up -d
```

See `docker-compose.yml` for production configuration examples.

---

## Common Commands

```bash
# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\Activate.ps1  # Windows

# Install dependencies
pip install -e .

# Run migrations
alembic upgrade head

# Create new migration
alembic revision -m "description"

# Run tests
pytest

# Start server (FastAPI only)
uvicorn src.api.server:app --reload --port 2024

# Start server (with LangGraph)
langgraph dev

# Stop Docker services
docker-compose down

# View logs
docker-compose logs -f redis
```

---

## VS Code Setup

Recommended `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.terminal.activateEnvironment": true,
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black"
}
```

---

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Docker Documentation](https://docs.docker.com/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Redis Documentation](https://redis.io/documentation)
