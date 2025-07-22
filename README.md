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

```mermaid
graph LR
    A[📰 Step 1: Fetch Trending Topics (RSS Scraping)] 
        --> B[📊 Step 2: Score & Rank Topics]
    B --> C[👤 Step 3: Human Approval of Top 3 Topics]
    C --> D[📚 Step 4: Scrape Reference Content]
    D --> E[🧠 Step 5: Generate Outline with LLM]
    E --> F[👤 Human Approval of Outline]
    F --> G[📝 Step 6: Generate Full Blog Draft (1000-1500 words)]
    G --> H[👤 Step 7: Human Review (Plagiarism, SEO, AI Check)]
    H -->|✅ Approved| I[🌐 Step 8: Publish Draft to WordPress]
    I --> J[🔔 Step 9: Notify Marketing Team on Slack]
    J --> K[📂 Step 10: Save Final Approved Article for RAG]
    H -->|❌ Rejected| E
---

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

2. Configure environment variables:
- Copy `.env.example` to `.env`
- Update the variables as needed

3. Update configuration in `config/config.yaml`

## Usage

Run the main application:

```bash
python main.py
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

## 🚀 Getting Started

1. Clone this repo or download the notebook
2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the notebook in **Jupyter Notebook** or **Google Colab**
4. Provide human feedback when prompted
5. Get your final blog articles in minutes!

> ⚠️ This notebook is designed for experimentation and can be deployed in production via FastAPI or Streamlit.

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
