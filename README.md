# 🚀 Full Blog Automation with Human Feedback using LangGraph

Welcome to the **Full Blog Automation System**, a powerful notebook that automates the creation of high-quality blog posts on trending **WordPress** topics — with a human-in-the-loop for quality control.

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
pip install -r requirements.txt
```

- Run this command to enable the crawl4ai
```python
crawl4ai-setup
```

- Complete the test for crawl4ai
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


POSTGRES_URL = POSTGRESS URI

```

3. Update configuration in `config/config.yaml`

## Usage

Run the main application:

```bash
langgraph dev --allow-blocking 
```

We can access the api doc on this url
```bash
http://127.0.0.1:2024/docs
```
## Data Storage

The project uses both CSV and database storage:
- `full_blog.csv`: Contains blog post data
- `langgraph.db`: Database for graph operations
- `langgraph.json`: JSON configuration for LangGraph

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
