# 🚀 Full Blog Automation with Human Feedback using LangGraph

Welcome to the **Full Blog Automation System**, a powerful notebook that automates the creation of high-quality blog posts on trending **WordPress** topics — with a human-in-the-loop for quality control.

#10 Essential Email Marketing Best Practices for 2023
#blog

> 🧠 AI-Powered | 🤖 Fully Automated | 👤 Human Feedback | 📈 SEO-Ready

---

## 🌟 What This Project Does

✅ Scrapes and selects trending blog topics from multiple sources (WordPress + local articles)  
✅ Scores articles based on **relevance** and **trending level**  
✅ Combines article content for deeper context  
✅ Uses LLMs to **generate blog outlines**  
✅ Allows **human feedback** on outlines (approve/reject)  
✅ Generates the final blog post from approved outlines  
✅ Modular and scalable workflow using **LangGraph**

---

## ⚙️ Technology Stack

- **LangGraph** – Agentic state machine for LLM workflows
- **LangChain** – LLM integrations and tool orchestration
- **OpenAI GPT** – Text generation
- **Python (3.11+)** – Core logic
- **BeautifulSoup & Requests** – Web scraping

---

## 🧩 Workflow Overview

## 🧩 Workflow Overview

## 📂 Project Structure

```
📘 Full_Blog_Automation_With_Human_Feedback.ipynb
├── 1. Fetch and Combine Articles
├── 2. Score Relevance and Trendiness
├── 3. Scrape Full Content from URLs
├── 4. Generate Outlines using LLMs
├── 5. Human-in-the-loop Outline Approval
└── 6. Final Blog Generation (Approved Only)
```

---

# Content Automation

A Python-based blog post automation system that processes and generates content using LangGraph.

## Project Structure

```
├── config/
│   └── config.yaml         # Configuration settings
├── data/
│   └── full_blog.csv      # Blog post data
├── src/
│   ├── data/              # Data processing modules
│   ├── model/             # Model implementations
│   ├── nodes/             # Graph nodes
│   ├── prompts/           # Prompt templates
│   ├── states/            # State management
│   ├── utils/             # Utility functions
│   └── workflow/          # Workflow definitions
├── .langgraph_api/        # LangGraph checkpoint files
├── main.py                # Application entry point
├── requirements.txt       # Python dependencies
├── pyproject.toml         # Project configuration
└── .env                   # Environment variables
```

## Setup

1. Install dependencies:
```bash
pip install uv
```

2. Install the required packages
```bash
uv sync
```

3. Run this command to enable the crawl4ai
```python
crawl4ai-setup
```

4. Complete the test for crawl4ai
```python
crawl4ai-doctor
```

# Setup Postgress DB
- Run this command in `docker`
```bash
docker run --name langgraph-postgres   -e POSTGRES_USER=YourUserName  -e POSTGRES_PASSWORD=YourPassword  -e POSTGRES_DB=dbName   -p 5432:5432   -d postgres:15D
```


2. Configure environment variables:
- Copy `.env.example` to `.env`
- Update the variables as needed
```bash
OPENAI_API_KEY = OPENAI_API_KEY

GNEWS_API_KEY = GNEWS_API_KEY

LANGSMITH_API_KEY = LANGSMITH URI

WP_URL = BaseURL/wp-json/wp/v2/posts
WP_TOKEN = WORDPRESS_TOKEN


POSTGRES_URI_CUSTOM = POSTGRESS URI
REDIS_URI = redis://langgraph-redis:6379

```

3. Update configuration in `config/config.yaml`

## Usage

Run the main application:

```bash
langgraph up
```
- It can build a docker image and run the application in the containr.

We can access the api doc on this url
```bash
http://localhost:8123/docs
```

**Run the streamlit app**
```bash
streamlit run app.py
```

- In steamlit app set the configration for the blog **(done)**.
- Afer Seting the config working on blog generation part.
- `Note` Make sure that before running the streamit app first run the backend api by running this command `http://localhost:8123/docs`
## Data Storage

The project uses both CSV and database storage:
- `full_blog.csv`: Contains blog post data
- `langgraph.db`: Database for graph operations
- `langgraph.json`: JSON configuration for LangGraph

## Database Migrations

This project uses Alembic for database schema management with asyncpg driver.

### Quick Commands (npm-style)

```bash
# Fresh start (reset + migrate) - recommended for first setup
.venv/bin/db seed

# Reset database only (⚠️ destroys all data)
.venv/bin/db reset

# Run migrations only
.venv/bin/db migrate

# Check migration status
.venv/bin/db status
```

### Manual Reset (if needed)

To completely reset the database manually (⚠️ **destroys all data**):

```bash
.venv/bin/python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv()

async def reset_db():
    db_url = os.getenv('POSTGRES_URI_CUSTOM')
    if not db_url.startswith('postgresql+asyncpg'):
        db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://')

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(text('DROP SCHEMA public CASCADE'))
        await conn.execute(text('CREATE SCHEMA public'))
        print('✅ Database reset')
    await engine.dispose()

asyncio.run(reset_db())
"

# Then run migrations to recreate tables and seed data
.venv/bin/alembic upgrade head
```

### Common Commands

```bash
# Check current migration status
alembic current

# Upgrade to latest migration
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "description of changes"

# Downgrade one migration (use with caution!)
alembic downgrade -1

# View migration history
alembic history
```

### Using the Migration Utility

```bash
# Check status
python migrate.py status

# Upgrade database
python migrate.py upgrade

# Create new migration
python migrate.py create "add user avatar field"

# View history
python migrate.py history
```

### Migration Workflow

1. **Modify Models**: Make changes to SQLAlchemy models in `src/api/models/`
2. **Generate Migration**: Run `alembic revision --autogenerate -m "description"`
3. **Review Migration**: Check the generated file in `alembic/versions/`
4. **Test Migration**: Run `alembic upgrade head --sql` to preview SQL
5. **Apply Migration**: Run `alembic upgrade head`
6. **Verify**: Check database and test application

### Important Notes

- **Never** modify migration files after they've been committed and applied
- **Always** review autogenerated migrations before applying
- **Test** migrations in development before applying to production
- **Backup** database before running migrations in production

## Database Seeding

### Production Seeds (via Migrations)

Essential data required for the application to function is automatically seeded via Alembic migrations:

- **Default Permissions**: 6 permissions (content & topic CRUD operations)
  - Automatically created when running: `alembic upgrade head`
  - Migration: `4883f6e4c3f5_seed_default_permissions.py`
  - Idempotent: Safe to run multiple times

### Development/Test Data

Development and test data should be created on-demand when needed:

- **NOT maintained in repository** - Environment-specific and changes frequently
- **Create fresh for test scenarios** - Use database clients or custom scripts
- **Never run dummy data in production** ⚠️

### Seeding Best Practices

- ✅ **Production-critical data**: Add to Alembic migrations (idempotent)
- ✅ **Run migrations**: `alembic upgrade head` to apply all seeds
- ❌ **Never commit**: Large dummy data scripts to repository
- ❌ **Never run**: Development seeds in production environment

## Development

Python version: See `.python-version` file
Package management: Using `uv` (lock file: `uv.lock`)

---

## 💡 Use Cases

- Automated SEO blog generation for digital marketing
- Editorial tools for content teams with LLMs
- Newsletter and content repurposing bots
- LLM-based writing assistants with human control

---

## 🤝 Contributions

Pull requests and feedback are welcome! Let’s make this more powerful and production-ready together.

---

## 📄 License

Licensed under the MIT License.

---

> Made with ❤️ using LangGraph + LLMs
