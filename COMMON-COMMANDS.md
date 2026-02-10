# 📝 Common Commands Cheat Sheet

Quick reference for daily development tasks.

---

## 🚀 Starting Development

### Full Startup (Recommended)
```bash
./start-dev.sh
```
This automatically:
1. ✅ Checks if Docker is running
2. ✅ Starts Redis & PostgreSQL containers
3. ✅ Starts LangGraph dev server on port 2024

### Manual Startup
# 1. Start infrastructure
docker-compose up -d redis langgraph-redis langgraph-postgres

# 2. Start backend server
.venv/bin/langgraph dev
```

---

## 🛑 Stopping Development

### Stop Backend Server
Press `Ctrl+C` in the terminal running `langgraph dev`

### Stop Docker Containers
```bash
# Stop all containers (data preserved)
docker-compose stop

# OR stop specific ones
docker stop rext-redis langgraph-redis rext-backend-langgraph-postgres-1
```

### Complete Shutdown
```bash
# Stop containers and remove them (data preserved in volumes)
docker-compose down

# ⚠️ DANGEROUS: Delete everything including data
docker-compose down -v
```

---

## 💾 Database Commands

### Quick Database Tasks
```bash
# Check migration status
python scripts/db.py status

# Run pending migrations
python scripts/db.py migrate

# Fresh start (delete all data + migrate)
python scripts/db.py seed
```

### Manual Migration Commands
```bash
# Apply migrations
.venv/bin/alembic upgrade head

# Create new migration
.venv/bin/alembic revision -m "description"

# Check current version
.venv/bin/alembic current

# Rollback one migration
.venv/bin/alembic downgrade -1
```

---

## 🐳 Docker Commands

### Check Status
```bash
# See running containers
docker-compose ps

# OR
docker ps

# See all containers (including stopped)
docker ps -a
```

### View Logs
```bash
# All services (live)
docker-compose logs -f

# Specific service
docker-compose logs -f langgraph-postgres
docker-compose logs -f redis

# Last 50 lines only
docker-compose logs --tail=50
```

### Restart Services
```bash
# Restart all
docker-compose restart

# Restart PostgreSQL only
docker-compose restart langgraph-postgres

# Restart Redis only
docker-compose restart redis
```

---

## 🗄️ Direct Database Access

### PostgreSQL Shell
```bash
# Option 1: Via Docker
docker exec -it rext-backend-langgraph-postgres-1 psql -U postgres

# Option 2: If psql installed locally
psql -h localhost -p 5433 -U postgres -d postgres
```

### Common SQL Commands (inside psql)
```sql
-- List all tables
\dt

-- Describe table structure
\d users
\d content

-- Query data
SELECT * FROM users LIMIT 5;
SELECT email, created_at FROM users WHERE status = 'active';

-- Count records
SELECT COUNT(*) FROM users;

-- Quit
\q
```

### Backup & Restore
```bash
# Create backup
docker exec rext-backend-langgraph-postgres-1 pg_dump -U postgres postgres > backup.sql

# Restore backup
cat backup.sql | docker exec -i rext-backend-langgraph-postgres-1 psql -U postgres postgres

# Backup with timestamp
docker exec rext-backend-langgraph-postgres-1 pg_dump -U postgres postgres > backup_$(date +%Y%m%d_%H%M%S).sql
```

---

## 🔍 Debugging

### Check Backend Health
```bash
curl http://localhost:2024/health | python3 -m json.tool
```

### Check Database Connection
```bash
# Quick test
docker exec rext-backend-langgraph-postgres-1 pg_isready -U postgres

# Test from Python
python -c "from src.api.database.async_database import async_engine; import asyncio; asyncio.run(async_engine.connect())"
```

### Check Redis Connection
```bash
# From Docker
docker exec rext-redis redis-cli ping
# Should return: PONG

# Test connection
docker exec rext-redis redis-cli
> ping
> exit
```

### View Resource Usage
```bash
docker stats
```

---

## 🧹 Cleanup

### Remove Unused Docker Resources
```bash
# Safe cleanup (removes stopped containers, unused images)
docker system prune

# More aggressive (also removes unused volumes)
docker system prune -a

# Check disk usage
docker system df
```

### Reset Everything (Fresh Start)
```bash
# 1. Stop all containers
docker-compose down -v

# 2. Remove Python cache
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete

# 3. Start fresh
docker-compose up -d redis langgraph-redis langgraph-postgres
python scripts/db.py seed
```

---

## 📊 TablePlus Connection

**Quick Copy-Paste Settings:**
```
Name:     Rext Local (Docker)
Host:     localhost
Port:     5433          ⬅️ Important: NOT 5432!
User:     postgres
Password: postgres
Database: postgres
```

---

## 🔧 Environment Variables

### Check Current Settings
```bash
# View specific variable
echo $POSTGRES_URI_CUSTOM

# Show all rext-related variables
env | grep -i "postgres\|redis\|secret"
```

### Reload .env Changes
```bash
# Backend auto-reloads .env, but to be sure:
# 1. Stop backend (Ctrl+C)
# 2. Restart
./start-dev.sh
```

---

## 🚨 Common Issues & Fixes

### Port Already in Use
```bash
# Check what's using port 2024
lsof -i :2024

# Kill the process
kill -9 <PID>
```

### Database Connection Refused
```bash
# 1. Check if PostgreSQL is running
docker-compose ps | grep postgres

# 2. Check port is correct
lsof -i :5433

# 3. Restart PostgreSQL
docker-compose restart langgraph-postgres

# 4. Check logs
docker-compose logs langgraph-postgres
```

### Docker Daemon Not Running
```bash
# Start Docker Desktop app
open -a Docker

# Wait for it to start, then check
docker info
```

### Migration Errors
```bash
# Reset and try again
python scripts/db.py seed

# OR manually
.venv/bin/alembic downgrade base
.venv/bin/alembic upgrade head
```

---

## 💡 Pro Tips

1. **Use `./start-dev.sh`** - One command to start everything
2. **Keep Docker Desktop running** - Saves startup time
3. **Don't use `docker-compose down -v`** - You'll lose all data
4. **Check logs first** - Most issues show up in logs
5. **Use TablePlus** - Much easier than command line for viewing data

---

## 📞 Quick Help

| I want to... | Command |
|--------------|---------|
| Start everything | `./start-dev.sh` |
| Stop backend | `Ctrl+C` |
| Stop Docker | `docker-compose stop` |
| Reset database | `python scripts/db.py seed` |
| View database | Open TablePlus → localhost:5433 |
| Check logs | `docker-compose logs -f` |
| Create backup | `docker exec rext-backend-langgraph-postgres-1 pg_dump -U postgres postgres > backup.sql` |

---

## 📚 Related Guides

- [DOCKER-GUIDE.md](DOCKER-GUIDE.md) - Detailed Docker explanation
- [DEVELOPMENT.md](DEVELOPMENT.md) - Full development setup
- [QUICK-START.md](../QUICK-START.md) - Getting started guide
