# 🐳 Docker Guide for Beginners

## What is Docker? (Simple Explanation)

Imagine Docker as a **"shipping container" for software**:
- Your app and its dependencies (PostgreSQL, Redis) are packaged together
- It runs the same way on **any computer** (Mac, Windows, Linux)
- You can start/stop services without installing them permanently

**Key Terms:**
- **Container** = A running mini-computer (like PostgreSQL running)
- **Image** = A template/blueprint (like `postgres:16`)
- **Volume** = Permanent storage (data survives even if container stops)

---

## 📦 What Docker Containers Are You Running?

When you run `docker-compose up`, these containers start:

### 1. PostgreSQL Database
- **Container Name**: `rext-backend-langgraph-postgres-1`
- **Image**: `postgres:16`
- **Port**: 5433 (on your computer) → 5432 (inside container)
- **Username**: `postgres`
- **Password**: `postgres`
- **Database**: `postgres`

### 2. Redis (App Cache)
- **Container Name**: `rext-redis`
- **Image**: `redis:7-alpine`
- **Port**: 6379 (shared with your computer)

### 3. Redis (LangGraph)
- **Container Name**: `langgraph-redis`
- **Image**: `redis:6`
- **Port**: Only accessible to other Docker containers

---

## 🎯 Essential Docker Commands

### Start Services
```bash
# Start all services in background (-d = detached mode)
docker-compose up -d

# Start specific services only
docker-compose up -d redis langgraph-postgres

# Start with logs visible (no -d)
docker-compose up
```

### Check Status
```bash
# See all running containers
docker-compose ps

# See detailed info
docker ps

# Example output:
# NAME                          STATUS                   PORTS
# rext-redis                   Up 5 minutes (healthy)   6379/tcp
# langgraph-postgres            Up 5 minutes (healthy)   0.0.0.0:5433->5432/tcp
```

### View Logs
```bash
# All services
docker-compose logs

# Specific service (live tail)
docker-compose logs -f langgraph-postgres
docker-compose logs -f redis

# Last 50 lines
docker-compose logs --tail=50
```

### Stop Services
```bash
# Stop all containers (data is preserved)
docker-compose stop

# Stop and remove containers (data is preserved in volumes)
docker-compose down

# Stop, remove containers AND delete all data (⚠️ DANGEROUS)
docker-compose down -v
```

### Restart Services
```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart langgraph-postgres
```

---

## 💾 Database Management

### Your Existing Commands Still Work!

The `db` script automatically connects to Docker PostgreSQL (via `.env` settings).

```bash
# Check what migrations have been applied
python scripts/db.py status

# Run new migrations
python scripts/db.py migrate

# Reset database (⚠️ deletes all data)
python scripts/db.py reset

# Fresh start (reset + migrate + create super admin)
python scripts/db.py seed
```

### Direct Database Commands

**Option 1: Using Docker exec**
```bash
# Open PostgreSQL shell inside container
docker exec -it rext-backend-langgraph-postgres-1 psql -U postgres

# Once inside, you can run SQL:
\dt              # List tables
\d users         # Describe users table
SELECT * FROM users LIMIT 5;
\q               # Quit
```

**Option 2: From your computer (if psql installed)**
```bash
psql -h localhost -p 5433 -U postgres -d postgres
```

### Run SQL Files
```bash
# Execute SQL file inside container
docker exec -i rext-backend-langgraph-postgres-1 psql -U postgres < backup.sql

# Create a backup
docker exec rext-backend-langgraph-postgres-1 pg_dump -U postgres postgres > backup.sql
```

---

## 🗄️ Connecting TablePlus to Docker PostgreSQL

**TablePlus** is a GUI database client. Here's how to connect:

### Step 1: Make Sure PostgreSQL is Running
```bash
docker-compose ps | grep postgres
# Should show: Up X minutes (healthy)
```

### Step 2: Open TablePlus

1. Click **"Create a new connection"**
2. Choose **PostgreSQL**

### Step 3: Enter Connection Details

| Field      | Value              | Notes                              |
|------------|--------------------|------------------------------------|
| **Name**   | Rext Local (Docker) | Any name you want             |
| **Host**   | `localhost`        | Or `127.0.0.1`                     |
| **Port**   | `5433`             | **NOT 5432!** (Docker mapped port) |
| **User**   | `postgres`         | Default from docker-compose.yml    |
| **Password** | `postgres`       | Default from docker-compose.yml    |
| **Database** | `postgres`       | Default database name              |

### Step 4: Test & Connect

1. Click **"Test"** - should show ✅ Success
2. Click **"Connect"**
3. You'll see all your tables!

### Visual Guide:
```
┌─────────────────────────────────────┐
│  TablePlus Connection               │
├─────────────────────────────────────┤
│  Name: Rext Local (Docker)         │
│  Host: localhost                    │
│  Port: 5433  ← IMPORTANT!           │
│  User: postgres                     │
│  Password: postgres                 │
│  Database: postgres                 │
│                                     │
│  [Test]  [Connect]                  │
└─────────────────────────────────────┘
```

---

## 🔄 Common Workflows

### Reset Database (Fresh Start)
```bash
# Method 1: Using db script (recommended)
python scripts/db.py seed

# Method 2: Manual
docker-compose down -v          # Delete everything including data
docker-compose up -d            # Start fresh containers
python scripts/db.py migrate    # Run migrations
```

### Check Database Connection
```bash
# From Python
python -c "from src.api.database.async_database import async_engine; import asyncio; asyncio.run(async_engine.connect())"

# From Docker
docker exec rext-backend-langgraph-postgres-1 pg_isready -U postgres
```

### View Container Resource Usage
```bash
docker stats

# Output shows:
# CONTAINER     CPU %   MEM USAGE / LIMIT   MEM %   NET I/O
# postgres      0.5%    45MB / 2GB          2.25%   1.2kB / 860B
```

---

## 🚨 Troubleshooting

### Container Won't Start

**Check logs:**
```bash
docker-compose logs langgraph-postgres
```

**Common issues:**
- Port already in use → Change port in `docker-compose.yml`
- Not enough disk space → Run `docker system prune`

### Database Connection Refused

**Solutions:**
```bash
# 1. Check if container is running
docker-compose ps

# 2. Check if port is correct (5433 not 5432)
lsof -i :5433

# 3. Restart PostgreSQL container
docker-compose restart langgraph-postgres

# 4. Check logs for errors
docker-compose logs langgraph-postgres
```

### Lost All Data After Restart

**Cause:** You ran `docker-compose down -v` (the `-v` flag deletes volumes)

**Solution:**
```bash
# Always use this instead:
docker-compose down      # Without -v to keep data
```

### Can't Connect from TablePlus

**Checklist:**
1. ✅ Container running? `docker-compose ps`
2. ✅ Using port **5433** not 5432?
3. ✅ Password is `postgres` (lowercase)?
4. ✅ Host is `localhost` not `langgraph-postgres`?

---

## 📊 Data Persistence

### Where is Data Stored?

Docker stores data in **volumes**:

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect rext-backend_langgraph-data

# Output shows where data is stored:
# "Mountpoint": "/var/lib/docker/volumes/rext-backend_langgraph-data/_data"
```

### Backup & Restore

**Create Backup:**
```bash
# Database backup
docker exec rext-backend-langgraph-postgres-1 pg_dump -U postgres postgres > backup_$(date +%Y%m%d).sql

# Volume backup (all data)
docker run --rm -v rext-backend_langgraph-data:/data -v $(pwd):/backup alpine tar czf /backup/db-backup.tar.gz -C /data .
```

**Restore Backup:**
```bash
# Database restore
cat backup_20251016.sql | docker exec -i rext-backend-langgraph-postgres-1 psql -U postgres postgres
```

---

## 🎓 Quick Reference

| Task | Command |
|------|---------|
| Start all services | `docker-compose up -d` |
| Stop all services | `docker-compose stop` |
| View logs | `docker-compose logs -f` |
| Reset database | `python scripts/db.py seed` |
| Run migrations | `python scripts/db.py migrate` |
| Check status | `docker-compose ps` |
| Open database shell | `docker exec -it rext-backend-langgraph-postgres-1 psql -U postgres` |
| Backup database | `docker exec rext-backend-langgraph-postgres-1 pg_dump -U postgres postgres > backup.sql` |

---

## 🔗 Useful Resources

- [Docker Documentation](https://docs.docker.com/)
- [PostgreSQL Docker Image](https://hub.docker.com/_/postgres)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [TablePlus Documentation](https://tableplus.com/blog/2018/04/postgresql-gui-client-tableplus.html)

---

## 💡 Pro Tips

1. **Always check logs first** when something isn't working
   ```bash
   docker-compose logs -f
   ```

2. **Use `docker-compose down` without `-v`** to preserve data

3. **Restart individual services** instead of all:
   ```bash
   docker-compose restart langgraph-postgres
   ```

4. **Monitor resource usage** to catch issues early:
   ```bash
   docker stats
   ```

5. **Clean up unused resources** periodically:
   ```bash
   docker system prune   # Remove unused containers/images
   ```
