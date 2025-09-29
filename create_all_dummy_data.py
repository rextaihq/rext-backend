#!/usr/bin/env python3
"""
FINAL Complete Dummy Data Script for Wrext Backend Database

This comprehensive script creates all sample data for testing with correct table schemas:
- Multiple test users with various profiles
- Workspaces with detailed metadata
- Web knowledge with various processing statuses
- File knowledge entries across different file types
- Text knowledge entries with rich content
- Complete brand voice data with all attributes

Features:
- ✅ Corrected table schemas based on actual database structure
- ✅ Idempotent (safe to run multiple times)
- ✅ Comprehensive error handling
- ✅ Direct SQL creation to avoid import issues
- ✅ Detailed progress reporting
- ✅ Complete verification
- ✅ Handles JSONB fields correctly
- ✅ Uses proper column names

Run with: python setup_complete_dummy_data.py

PASSWORD FOR ALL USERS: password123
"""

import os
import sys
import uuid
import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database setup
SQLALCHEMY_DATABASE_URL = os.getenv("POSTGRES_URI_CUSTOM")
if not SQLALCHEMY_DATABASE_URL:
    print("❌ Error: POSTGRES_URI_CUSTOM environment variable not set")
    sys.exit(1)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def hash_password_safe(password: str) -> str:
    """Hash password with fallback"""
    try:
        # Try using the app's hash function first
        if 'hash_password' in globals():
            return hash_password(password)
    except Exception as e:
        print(f"⚠️ Error using hash_password function: {e}")

    # Fallback: Use bcrypt directly
    try:
        import bcrypt
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    except ImportError:
        print("⚠️ bcrypt not available, using fallback hash")
        return "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LeSkTLN.d8P84SgTe"

def create_users_comprehensive():
    """Create a comprehensive set of test users"""
    users_data = [
        {
            "email": "test@example.com",
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "display_name": "Test User",
            "role": "Primary test account"
        },
        {
            "email": "john.doe@example.com",
            "username": "johndoe",
            "first_name": "John",
            "last_name": "Doe",
            "display_name": "John Doe",
            "role": "Workspace owner - TechCorp"
        },
        {
            "email": "jane.smith@company.com",
            "username": "janesmith",
            "first_name": "Jane",
            "last_name": "Smith",
            "display_name": "Jane Smith",
            "role": "Workspace owner - Analytics"
        },
        {
            "email": "mike.wilson@startup.io",
            "username": "mikewilson",
            "first_name": "Mike",
            "last_name": "Wilson",
            "display_name": "Mike Wilson",
            "role": "Workspace owner - Growth"
        },
        {
            "email": "admin@wrext.com",
            "username": "admin",
            "first_name": "Admin",
            "last_name": "User",
            "display_name": "Admin User",
            "role": "System administrator"
        },
        {
            "email": "demo@wrext.com",
            "username": "demo",
            "first_name": "Demo",
            "last_name": "Account",
            "display_name": "Demo Account",
            "role": "Demonstration user"
        }
    ]

    with engine.connect() as connection:
        created_users = []

        for user_data in users_data:
            try:
                # Check if user exists
                result = connection.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": user_data["email"]}
                )
                existing = result.fetchone()

                if existing:
                    # Update password
                    connection.execute(text("""
                        UPDATE users
                        SET password_hash = :password_hash, updated_at = :now
                        WHERE email = :email
                    """), {
                        "password_hash": hash_password_safe("password123"),
                        "now": datetime.utcnow(),
                        "email": user_data["email"]
                    })
                    print(f"✅ Updated user: {user_data['email']}")
                else:
                    # Create new user
                    user_id = str(uuid.uuid4())
                    connection.execute(text("""
                        INSERT INTO users (
                            id, email, username, password_hash, first_name, last_name,
                            display_name, email_verified, status, created_at, updated_at
                        ) VALUES (
                            :id, :email, :username, :password_hash, :first_name, :last_name,
                            :display_name, :email_verified, :status, :created_at, :updated_at
                        )
                    """), {
                        "id": user_id,
                        "email": user_data["email"],
                        "username": user_data["username"],
                        "password_hash": hash_password_safe("password123"),
                        "first_name": user_data["first_name"],
                        "last_name": user_data["last_name"],
                        "display_name": user_data["display_name"],
                        "email_verified": True,
                        "status": "active",
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    })
                    print(f"✅ Created user: {user_data['email']} ({user_data['role']})")
                    created_users.append(user_data)

            except Exception as e:
                print(f"❌ Error with user {user_data['email']}: {e}")
                continue

        connection.commit()
        return created_users

def create_workspaces_comprehensive():
    """Create comprehensive workspace data"""

    # First get user IDs
    with engine.connect() as connection:
        users_result = connection.execute(text("""
            SELECT id, email, display_name FROM users
            WHERE email IN ('john.doe@example.com', 'jane.smith@company.com', 'mike.wilson@startup.io', 'test@example.com')
        """))
        users_dict = {row.email: {"id": row.id, "name": row.display_name} for row in users_result}

    workspaces_data = [
        {
            "name": "TechCorp Marketing Hub",
            "description": "Central workspace for TechCorp's marketing team to manage content, campaigns, and brand messaging across all digital channels.",
            "url": "https://techcorp.com",
            "owner_email": "john.doe@example.com"
        },
        {
            "name": "E-commerce Analytics",
            "description": "Workspace for analyzing e-commerce trends, customer behavior, and market insights to drive strategic business decisions.",
            "url": "https://ecommerce-analytics.io",
            "owner_email": "jane.smith@company.com"
        },
        {
            "name": "Startup Growth Engine",
            "description": "Growth-focused workspace for startup companies to scale their content marketing and customer acquisition strategies.",
            "url": "https://startupgrowth.co",
            "owner_email": "mike.wilson@startup.io"
        },
        {
            "name": "Health & Wellness Blog",
            "description": "Content workspace for health and wellness publications, research, and educational material creation.",
            "url": "https://healthwellness.blog",
            "owner_email": "john.doe@example.com"
        },
        {
            "name": "FinTech Innovations",
            "description": "Financial technology workspace for market research, product positioning, and regulatory compliance content.",
            "url": "https://fintech-innovations.com",
            "owner_email": "jane.smith@company.com"
        }
    ]

    with engine.connect() as connection:
        created_workspaces = []

        for workspace_data in workspaces_data:
            try:
                # Check if workspace exists
                result = connection.execute(
                    text("SELECT id FROM workspace WHERE name = :name"),
                    {"name": workspace_data["name"]}
                )
                existing = result.fetchone()

                if existing:
                    print(f"✅ Workspace already exists: {workspace_data['name']}")
                    created_workspaces.append({**workspace_data, "id": str(existing.id)})
                    continue

                # Get owner ID
                owner_info = users_dict.get(workspace_data["owner_email"])
                if not owner_info:
                    print(f"❌ Owner not found for workspace: {workspace_data['name']}")
                    continue

                # Create workspace
                workspace_id = str(uuid.uuid4())
                connection.execute(text("""
                    INSERT INTO workspace (
                        id, name, description, url, user_id, created_at
                    ) VALUES (
                        :id, :name, :description, :url, :user_id, :created_at
                    )
                """), {
                    "id": workspace_id,
                    "name": workspace_data["name"],
                    "description": workspace_data["description"],
                    "url": workspace_data["url"],
                    "user_id": owner_info["id"],
                    "created_at": datetime.utcnow()
                })

                print(f"✅ Created workspace: {workspace_data['name']} (Owner: {owner_info['name']})")
                created_workspaces.append({**workspace_data, "id": workspace_id})

            except Exception as e:
                print(f"❌ Error with workspace {workspace_data['name']}: {e}")
                continue

        connection.commit()
        return created_workspaces

def create_brand_voices_comprehensive():
    """Create comprehensive brand voice data"""

    # Get workspace IDs
    with engine.connect() as connection:
        workspaces_result = connection.execute(text("SELECT id, name FROM workspace"))
        workspaces_dict = {row.name: row.id for row in workspaces_result}

    brand_voices_data = [
        {
            "workspace_name": "TechCorp Marketing Hub",
            "about": "TechCorp is a leading enterprise technology solutions provider specializing in AI-driven automation, cloud infrastructure, and digital transformation services for Fortune 500 companies.",
            "customer_profile": "Chief Technology Officers and IT Directors at large enterprises (5000+ employees) who are responsible for digital transformation initiatives and technology stack modernization.",
            "selling_position": "The most trusted partner for enterprise-grade AI automation solutions that reduce operational costs by 40% while accelerating digital transformation timelines.",
            "target_audience": ["Enterprise CTOs", "IT Directors", "Digital Transformation Leaders", "Technology Consultants"],
            "brand_voice": ["Professional", "Authoritative", "Innovation-focused", "Data-driven", "Solution-oriented"],
            "competitors": ["IBM", "Microsoft", "Salesforce", "Oracle"],
            "content_strategy": ["Thought leadership in enterprise AI", "ROI-focused case studies", "Technical whitepapers", "Executive insights on digital transformation"]
        },
        {
            "workspace_name": "E-commerce Analytics",
            "about": "E-commerce Analytics provides advanced data analysis tools and market insights to help online retailers optimize their customer acquisition, retention, and revenue growth strategies.",
            "customer_profile": "E-commerce managers and digital marketing directors at mid-to-large online retailers who need actionable insights to improve conversion rates and customer lifetime value.",
            "selling_position": "The only analytics platform that combines real-time customer behavior tracking with predictive AI to increase e-commerce revenue by an average of 35%.",
            "target_audience": ["E-commerce Managers", "Digital Marketing Directors", "Data Analysts", "Online Retail Executives"],
            "brand_voice": ["Data-focused", "Results-driven", "Practical", "Growth-oriented", "Customer-centric"],
            "competitors": ["Google Analytics", "Adobe Analytics", "Klaviyo", "Shopify Analytics"],
            "content_strategy": ["Performance benchmarking reports", "Conversion optimization guides", "Customer behavior analysis", "ROI-focused case studies"]
        },
        {
            "workspace_name": "Startup Growth Engine",
            "about": "Startup Growth Engine is a comprehensive growth marketing platform that helps early-stage startups scale their customer acquisition through data-driven marketing strategies and growth hacking techniques.",
            "customer_profile": "Startup founders and growth marketers at early-stage companies (pre-Series B) who need scalable, cost-effective customer acquisition strategies with limited budgets.",
            "selling_position": "The growth platform that helps startups achieve product-market fit 3x faster through proven growth frameworks used by unicorn companies.",
            "target_audience": ["Startup Founders", "Growth Marketers", "Product Managers", "Early-stage Investors"],
            "brand_voice": ["Energetic", "Innovative", "Scrappy", "Growth-focused", "Community-driven"],
            "competitors": ["HubSpot", "Mixpanel", "Amplitude", "Hotjar"],
            "content_strategy": ["Growth hacking playbooks", "Startup success stories", "Viral marketing case studies", "Founder interview series"]
        },
        {
            "workspace_name": "Health & Wellness Blog",
            "about": "Health & Wellness Blog is a trusted source for evidence-based health information, fitness guidance, and wellness tips designed to help individuals achieve optimal physical and mental well-being.",
            "customer_profile": "Health-conscious individuals aged 25-55 who actively seek reliable, science-backed information to improve their physical fitness, mental health, and overall lifestyle.",
            "selling_position": "The most comprehensive and scientifically-accurate wellness resource that makes healthy living accessible and sustainable for busy professionals.",
            "target_audience": ["Fitness Enthusiasts", "Busy Professionals", "Health-conscious Parents", "Wellness Seekers"],
            "brand_voice": ["Encouraging", "Scientific", "Accessible", "Empowering", "Holistic"],
            "competitors": ["WebMD", "Healthline", "Mayo Clinic", "Verywell Health"],
            "content_strategy": ["Evidence-based health articles", "Workout routines", "Nutrition guides", "Expert healthcare interviews"]
        },
        {
            "workspace_name": "FinTech Innovations",
            "about": "FinTech Innovations develops cutting-edge financial technology solutions including blockchain payments, digital banking platforms, and regulatory compliance tools for modern financial institutions.",
            "customer_profile": "Financial services executives and fintech decision-makers who need innovative technology solutions to stay competitive while maintaining strict regulatory compliance and security standards.",
            "selling_position": "The only fintech platform that combines blockchain security, regulatory compliance, and user experience excellence to modernize traditional banking operations.",
            "target_audience": ["Bank Executives", "Fintech Entrepreneurs", "Compliance Officers", "Financial Technology Investors"],
            "brand_voice": ["Trustworthy", "Innovative", "Secure", "Regulatory-aware", "Future-focused"],
            "competitors": ["Stripe", "Square", "PayPal", "Coinbase"],
            "content_strategy": ["Regulatory update analyses", "Blockchain technology guides", "Digital banking trends", "Security-focused thought leadership"]
        }
    ]

    with engine.connect() as connection:
        created_brand_voices = []

        for brand_data in brand_voices_data:
            try:
                workspace_id = workspaces_dict.get(brand_data["workspace_name"])
                if not workspace_id:
                    print(f"❌ Workspace not found: {brand_data['workspace_name']}")
                    continue

                # Check if brand voice exists
                result = connection.execute(
                    text("SELECT id FROM brand_voice WHERE workspace_id = :workspace_id"),
                    {"workspace_id": workspace_id}
                )
                existing = result.fetchone()

                if existing:
                    print(f"✅ Brand voice already exists for: {brand_data['workspace_name']}")
                    continue

                # Create brand voice
                brand_voice_id = str(uuid.uuid4())
                connection.execute(text("""
                    INSERT INTO brand_voice (
                        id, workspace_id, about, customer_profile, selling_position,
                        target_audience, brand_voice, competitors, content_strategy
                    ) VALUES (
                        :id, :workspace_id, :about, :customer_profile, :selling_position,
                        :target_audience, :brand_voice, :competitors, :content_strategy
                    )
                """), {
                    "id": brand_voice_id,
                    "workspace_id": workspace_id,
                    "about": brand_data["about"],
                    "customer_profile": brand_data["customer_profile"],
                    "selling_position": brand_data["selling_position"],
                    "target_audience": json.dumps(brand_data["target_audience"]),  # JSONB
                    "brand_voice": json.dumps(brand_data["brand_voice"]),  # JSONB
                    "competitors": json.dumps(brand_data["competitors"]),  # JSONB
                    "content_strategy": json.dumps(brand_data["content_strategy"])  # JSONB
                })

                print(f"✅ Created brand voice for: {brand_data['workspace_name']}")
                created_brand_voices.append(brand_data)

            except Exception as e:
                print(f"❌ Error with brand voice {brand_data['workspace_name']}: {e}")
                continue

        connection.commit()
        return created_brand_voices

def create_web_knowledge_comprehensive():
    """Create comprehensive web knowledge with various statuses"""

    # Get workspace IDs
    with engine.connect() as connection:
        workspaces_result = connection.execute(text("SELECT id, name FROM workspace"))
        workspaces_dict = {row.name: row.id for row in workspaces_result}

    web_knowledge_data = [
        # TechCorp Marketing Hub
        {"url": "https://techcrunch.com/2024/01/15/enterprise-ai-trends", "workspace": "TechCorp Marketing Hub", "status": "completed", "content_stats": {"words": 850, "chars": 4500}},
        {"url": "https://venturebeat.com/ai/enterprise-automation-guide", "workspace": "TechCorp Marketing Hub", "status": "completed", "content_stats": {"words": 1150, "chars": 6200}},
        {"url": "https://forbes.com/digital-transformation-2024", "workspace": "TechCorp Marketing Hub", "status": "scraping"},
        {"url": "https://wired.com/enterprise-security-trends", "workspace": "TechCorp Marketing Hub", "status": "pending"},
        {"url": "https://techrepublic.com/cloud-computing-guide", "workspace": "TechCorp Marketing Hub", "status": "failed"},

        # E-commerce Analytics
        {"url": "https://shopify.com/blog/ecommerce-trends-2024", "workspace": "E-commerce Analytics", "status": "completed", "content_stats": {"words": 980, "chars": 5200}},
        {"url": "https://bigcommerce.com/articles/customer-analytics", "workspace": "E-commerce Analytics", "status": "completed", "content_stats": {"words": 720, "chars": 3800}},
        {"url": "https://ecommerceguide.com/conversion-optimization", "workspace": "E-commerce Analytics", "status": "processing", "content_stats": {"words": 780, "chars": 4100}},
        {"url": "https://retaildive.com/mobile-commerce-statistics", "workspace": "E-commerce Analytics", "status": "completed", "content_stats": {"words": 550, "chars": 2900}},

        # Startup Growth Engine
        {"url": "https://ycombinator.com/library/growth-marketing", "workspace": "Startup Growth Engine", "status": "completed", "content_stats": {"words": 1350, "chars": 7200}},
        {"url": "https://growthhackers.com/viral-marketing-strategies", "workspace": "Startup Growth Engine", "status": "completed", "content_stats": {"words": 1100, "chars": 5800}},
        {"url": "https://medium.com/startup-grind/customer-acquisition", "workspace": "Startup Growth Engine", "status": "scraping"},
        {"url": "https://firstround.com/review/product-market-fit", "workspace": "Startup Growth Engine", "status": "completed", "content_stats": {"words": 1250, "chars": 6500}},

        # Health & Wellness Blog
        {"url": "https://mayoclinic.org/healthy-lifestyle/nutrition", "workspace": "Health & Wellness Blog", "status": "completed", "content_stats": {"words": 800, "chars": 4200}},
        {"url": "https://harvard.edu/health/exercise-benefits", "workspace": "Health & Wellness Blog", "status": "completed", "content_stats": {"words": 680, "chars": 3600}},
        {"url": "https://webmd.com/diet/meditation-health-benefits", "workspace": "Health & Wellness Blog", "status": "processing", "content_stats": {"words": 610, "chars": 3200}},
        {"url": "https://healthline.com/sleep-quality-improvement", "workspace": "Health & Wellness Blog", "status": "completed", "content_stats": {"words": 920, "chars": 4800}},

        # FinTech Innovations
        {"url": "https://bloomberg.com/fintech-trends-2024", "workspace": "FinTech Innovations", "status": "completed", "content_stats": {"words": 1050, "chars": 5500}},
        {"url": "https://reuters.com/cryptocurrency-regulation", "workspace": "FinTech Innovations", "status": "completed", "content_stats": {"words": 800, "chars": 4200}},
        {"url": "https://coindesk.com/blockchain-enterprise-adoption", "workspace": "FinTech Innovations", "status": "failed"},
        {"url": "https://techcrunch.com/digital-banking-innovation", "workspace": "FinTech Innovations", "status": "scraping"}
    ]

    with engine.connect() as connection:
        created_websites = []

        for web_data in web_knowledge_data:
            try:
                workspace_id = workspaces_dict.get(web_data["workspace"])
                if not workspace_id:
                    print(f"❌ Workspace not found: {web_data['workspace']}")
                    continue

                # Check if website exists
                result = connection.execute(
                    text("SELECT id FROM website WHERE url = :url"),
                    {"url": web_data["url"]}
                )
                existing = result.fetchone()

                if existing:
                    print(f"✅ Website already exists: {web_data['url']}")
                    continue

                # Create website entry
                website_id = str(uuid.uuid4())

                # Handle different statuses
                content_stats = web_data.get("content_stats", {})
                word_count = content_stats.get("words")
                char_count = content_stats.get("chars")

                connection.execute(text("""
                    INSERT INTO website (
                        id, workspace_id, url, status, word_count, char_count
                    ) VALUES (
                        :id, :workspace_id, :url, :status, :word_count, :char_count
                    )
                """), {
                    "id": website_id,
                    "workspace_id": workspace_id,
                    "url": web_data["url"],
                    "status": web_data["status"],
                    "word_count": word_count,
                    "char_count": char_count
                })

                print(f"✅ Created web knowledge: {web_data['url']} ({web_data['status']})")
                created_websites.append(web_data)

            except Exception as e:
                print(f"❌ Error with website {web_data['url']}: {e}")
                continue

        connection.commit()
        return created_websites

def create_file_knowledge_comprehensive():
    """Create comprehensive file knowledge entries"""

    # Get workspace IDs
    with engine.connect() as connection:
        workspaces_result = connection.execute(text("SELECT id, name FROM workspace"))
        workspaces_dict = {row.name: row.id for row in workspaces_result}

    file_knowledge_data = [
        # TechCorp Marketing Hub
        {"file_name": "enterprise_ai_whitepaper.pdf", "workspace": "TechCorp Marketing Hub", "size": 2048000, "type": "application/pdf"},
        {"file_name": "digital_transformation_guide.docx", "workspace": "TechCorp Marketing Hub", "size": 1536000, "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        {"file_name": "security_best_practices.txt", "workspace": "TechCorp Marketing Hub", "size": 512000, "type": "text/plain"},

        # E-commerce Analytics
        {"file_name": "ecommerce_metrics_report.pdf", "workspace": "E-commerce Analytics", "size": 3072000, "type": "application/pdf"},
        {"file_name": "customer_journey_analysis.xlsx", "workspace": "E-commerce Analytics", "size": 1024000, "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},

        # Startup Growth Engine
        {"file_name": "growth_hacking_playbook.pdf", "workspace": "Startup Growth Engine", "size": 4096000, "type": "application/pdf"},
        {"file_name": "mvp_development_guide.md", "workspace": "Startup Growth Engine", "size": 256000, "type": "text/markdown"},
        {"file_name": "investor_pitch_template.pptx", "workspace": "Startup Growth Engine", "size": 5120000, "type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},

        # Health & Wellness Blog
        {"file_name": "nutrition_research_summary.pdf", "workspace": "Health & Wellness Blog", "size": 1792000, "type": "application/pdf"},
        {"file_name": "exercise_routines.txt", "workspace": "Health & Wellness Blog", "size": 128000, "type": "text/plain"},

        # FinTech Innovations
        {"file_name": "blockchain_implementation_guide.pdf", "workspace": "FinTech Innovations", "size": 6144000, "type": "application/pdf"},
        {"file_name": "regulatory_compliance_checklist.docx", "workspace": "FinTech Innovations", "size": 768000, "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ]

    with engine.connect() as connection:
        created_files = []

        for file_data in file_knowledge_data:
            try:
                workspace_id = workspaces_dict.get(file_data["workspace"])
                if not workspace_id:
                    print(f"❌ Workspace not found: {file_data['workspace']}")
                    continue

                # Check if file exists
                result = connection.execute(
                    text("SELECT id FROM knowledge_files WHERE file_name = :file_name AND workspace_id = :workspace_id"),
                    {"file_name": file_data["file_name"], "workspace_id": workspace_id}
                )
                existing = result.fetchone()

                if existing:
                    print(f"✅ File already exists: {file_data['file_name']}")
                    continue

                # Create file entry
                file_id = str(uuid.uuid4())
                connection.execute(text("""
                    INSERT INTO knowledge_files (
                        id, workspace_id, file_name, file_type, file_size, file_path
                    ) VALUES (
                        :id, :workspace_id, :file_name, :file_type, :file_size, :file_path
                    )
                """), {
                    "id": file_id,
                    "workspace_id": workspace_id,
                    "file_name": file_data["file_name"],
                    "file_type": file_data["type"],
                    "file_size": file_data["size"],
                    "file_path": f"/uploads/{workspace_id}/{file_data['file_name']}"
                })

                print(f"✅ Created file knowledge: {file_data['file_name']} ({file_data['size']/1024/1024:.2f} MB)")
                created_files.append(file_data)

            except Exception as e:
                print(f"❌ Error with file {file_data['file_name']}: {e}")
                continue

        connection.commit()
        return created_files

def create_text_knowledge_comprehensive():
    """Create comprehensive text knowledge entries"""

    # Get workspace IDs
    with engine.connect() as connection:
        workspaces_result = connection.execute(text("SELECT id, name FROM workspace"))
        workspaces_dict = {row.name: row.id for row in workspaces_result}

    text_knowledge_data = [
        # TechCorp Marketing Hub
        {
            "workspace": "TechCorp Marketing Hub",
            "content": """# Enterprise AI Implementation Strategy

Key considerations for implementing AI in enterprise environments:

## Phase 1: Assessment
- Current technology audit
- Business process analysis
- ROI potential evaluation
- Risk assessment

## Phase 2: Planning
- AI use case prioritization
- Technology stack selection
- Team skill development
- Change management strategy

## Phase 3: Implementation
- Pilot program launch
- Performance monitoring
- Iterative improvements
- Scaling successful initiatives"""
        },
        {
            "workspace": "TechCorp Marketing Hub",
            "content": """# Digital Transformation Checklist

## Technology Infrastructure
- [ ] Cloud migration strategy
- [ ] Legacy system integration
- [ ] Data architecture modernization
- [ ] Security framework update

## Process Optimization
- [ ] Workflow automation
- [ ] Performance metrics definition
- [ ] Quality assurance protocols
- [ ] Continuous improvement processes"""
        },

        # E-commerce Analytics
        {
            "workspace": "E-commerce Analytics",
            "content": """# Customer Acquisition Cost (CAC) Analysis

CAC is a critical metric for e-commerce businesses. Here's how to optimize it:

## Calculation Methods
- Total marketing spend / New customers acquired
- Channel-specific CAC analysis
- Cohort-based calculations
- Lifetime value comparison

## Optimization Strategies
- Conversion rate improvements
- Customer retention programs
- Referral systems
- Content marketing efficiency"""
        },
        {
            "workspace": "E-commerce Analytics",
            "content": """# E-commerce Conversion Rate Optimization

## Key Areas to Focus:

1. **Product Pages**
   - High-quality images
   - Detailed descriptions
   - Customer reviews
   - Clear pricing

2. **Checkout Process**
   - Simplified forms
   - Multiple payment options
   - Trust signals
   - Mobile optimization"""
        },

        # Startup Growth Engine
        {
            "workspace": "Startup Growth Engine",
            "content": """# Product-Market Fit Indicators

Signs that your startup has achieved product-market fit:

## Quantitative Signals
- High organic growth rate (>20% month-over-month)
- Strong user retention (>40% monthly retention)
- Low customer acquisition cost
- High net promoter score (>50)

## Qualitative Signals
- Users actively recommend your product
- Difficult to keep up with demand
- Clear value proposition resonance
- Strong word-of-mouth growth"""
        },
        {
            "workspace": "Startup Growth Engine",
            "content": """# Viral Marketing Strategies for Startups

## Essential Elements:

1. **Shareable Content**
   - Emotional connection
   - Practical value
   - Unique perspective
   - Visual appeal

2. **Growth Mechanisms**
   - Referral programs
   - Social sharing incentives
   - User-generated content
   - Community building

3. **Distribution Channels**
   - Social media optimization
   - Influencer partnerships
   - Content marketing
   - Email campaigns"""
        },

        # Health & Wellness Blog
        {
            "workspace": "Health & Wellness Blog",
            "content": """# Benefits of Regular Exercise

Regular physical activity provides numerous health benefits:

## Physical Benefits
- Improved cardiovascular health
- Increased muscle strength and endurance
- Better bone density
- Weight management
- Enhanced immune system function

## Mental Health Benefits
- Reduced stress and anxiety
- Improved mood and self-esteem
- Better sleep quality
- Enhanced cognitive function
- Increased energy levels

## Recommended Guidelines
- 150 minutes of moderate aerobic activity per week
- 2+ days of strength training per week
- Flexibility and balance exercises
- Gradual progression for beginners"""
        },
        {
            "workspace": "Health & Wellness Blog",
            "content": """# Nutrition Guidelines for Optimal Health

## Macronutrients Balance:
- **Carbohydrates**: 45-65% of total calories
- **Proteins**: 10-35% of total calories
- **Fats**: 20-35% of total calories

## Key Principles:
- Eat a variety of nutrient-dense foods
- Stay hydrated (8+ glasses of water daily)
- Limit processed foods and added sugars
- Practice portion control
- Include fruits and vegetables in every meal

## Meal Planning Tips:
- Plan meals in advance
- Prep ingredients on weekends
- Keep healthy snacks available
- Listen to hunger cues"""
        },

        # FinTech Innovations
        {
            "workspace": "FinTech Innovations",
            "content": """# Blockchain in Financial Services

Blockchain technology is revolutionizing financial services:

## Use Cases:
- **Payments**: Cross-border transactions
- **Trade Finance**: Supply chain transparency
- **Identity**: KYC/AML compliance
- **Smart Contracts**: Automated execution
- **Central Bank Digital Currencies**: CBDC implementation

## Benefits:
- Increased transparency
- Reduced settlement time
- Lower transaction costs
- Enhanced security
- Improved compliance

## Implementation Considerations:
- Regulatory compliance
- Scalability requirements
- Integration complexity
- Energy consumption
- User adoption"""
        },
        {
            "workspace": "FinTech Innovations",
            "content": """# FinTech Regulatory Landscape 2024

## Key Regulatory Trends:

### Open Banking
- API standardization
- Data sharing protocols
- Consumer consent management
- Third-party provider licensing

### Digital Assets
- Cryptocurrency classification
- Stablecoin regulations
- DeFi oversight
- NFT compliance frameworks

### Data Protection
- GDPR compliance
- Data localization requirements
- Cybersecurity standards
- Privacy by design principles

### Consumer Protection
- Fair lending practices
- Transparent fee structures
- Dispute resolution mechanisms
- Financial inclusion initiatives"""
        }
    ]

    with engine.connect() as connection:
        created_texts = []

        for text_data in text_knowledge_data:
            try:
                workspace_id = workspaces_dict.get(text_data["workspace"])
                if not workspace_id:
                    print(f"❌ Workspace not found: {text_data['workspace']}")
                    continue

                # Check if similar text exists (by content length and workspace)
                result = connection.execute(
                    text("SELECT id FROM text_knowledge WHERE workspace_id = :workspace_id AND LENGTH(content) = :content_length"),
                    {"workspace_id": workspace_id, "content_length": len(text_data["content"])}
                )
                existing = result.fetchone()

                if existing:
                    print(f"✅ Text knowledge already exists for workspace: {text_data['workspace']}")
                    continue

                # Create text knowledge entry
                text_id = str(uuid.uuid4())
                connection.execute(text("""
                    INSERT INTO text_knowledge (
                        id, workspace_id, content
                    ) VALUES (
                        :id, :workspace_id, :content
                    )
                """), {
                    "id": text_id,
                    "workspace_id": workspace_id,
                    "content": text_data["content"]
                })

                print(f"✅ Created text knowledge for: {text_data['workspace']} ({len(text_data['content'])} chars)")
                created_texts.append(text_data)

            except Exception as e:
                print(f"❌ Error with text for {text_data['workspace']}: {e}")
                continue

        connection.commit()
        return created_texts

def create_workspace_members():
    """Create workspace member associations"""

    with engine.connect() as connection:
        # Get workspace and user data
        workspaces_result = connection.execute(text("""
            SELECT w.id as workspace_id, w.name, w.user_id as owner_id, u.email as owner_email
            FROM workspace w
            JOIN users u ON w.user_id = u.id
        """))
        workspaces = list(workspaces_result)

        # Get all users
        users_result = connection.execute(text("SELECT id, email, display_name FROM users"))
        users = list(users_result)

        created_memberships = []

        for workspace in workspaces:
            # Check if owner membership exists
            result = connection.execute(text("""
                SELECT id FROM workspace_members
                WHERE workspace_id = :workspace_id AND user_id = :user_id
            """), {
                "workspace_id": workspace.workspace_id,
                "user_id": workspace.owner_id
            })
            existing = result.fetchone()

            if not existing:
                # Create owner membership
                member_id = str(uuid.uuid4())
                connection.execute(text("""
                    INSERT INTO workspace_members (
                        id, user_id, workspace_id, status, is_default, joined_at
                    ) VALUES (
                        :id, :user_id, :workspace_id, :status, :is_default, :joined_at
                    )
                """), {
                    "id": member_id,
                    "user_id": workspace.owner_id,
                    "workspace_id": workspace.workspace_id,
                    "status": "active",
                    "is_default": True,
                    "joined_at": datetime.utcnow()
                })
                print(f"✅ Created owner membership: {workspace.owner_email} → {workspace.name}")
                created_memberships.append({
                    "workspace": workspace.name,
                    "user": workspace.owner_email,
                    "role": "owner"
                })

            # Also add test@example.com user to all workspaces for testing
            test_user = next((u for u in users if u.email == "test@example.com"), None)
            if test_user and str(test_user.id) != str(workspace.owner_id):
                result = connection.execute(text("""
                    SELECT id FROM workspace_members
                    WHERE workspace_id = :workspace_id AND user_id = :user_id
                """), {
                    "workspace_id": workspace.workspace_id,
                    "user_id": test_user.id
                })
                existing = result.fetchone()

                if not existing:
                    member_id = str(uuid.uuid4())
                    connection.execute(text("""
                        INSERT INTO workspace_members (
                            id, user_id, workspace_id, status, is_default, joined_at
                        ) VALUES (
                            :id, :user_id, :workspace_id, :status, :is_default, :joined_at
                        )
                    """), {
                        "id": member_id,
                        "user_id": test_user.id,
                        "workspace_id": workspace.workspace_id,
                        "status": "active",
                        "is_default": False,
                        "joined_at": datetime.utcnow()
                    })
                    print(f"✅ Added test user to workspace: test@example.com → {workspace.name}")
                    created_memberships.append({
                        "workspace": workspace.name,
                        "user": "test@example.com",
                        "role": "member"
                    })

        connection.commit()
        return created_memberships

def verify_data_creation():
    """Verify all data was created successfully"""

    with engine.connect() as connection:
        # Count records
        users_count = connection.execute(text("SELECT COUNT(*) FROM users")).scalar()
        workspaces_count = connection.execute(text("SELECT COUNT(*) FROM workspace")).scalar()
        brand_voices_count = connection.execute(text("SELECT COUNT(*) FROM brand_voice")).scalar()
        websites_count = connection.execute(text("SELECT COUNT(*) FROM website")).scalar()
        files_count = connection.execute(text("SELECT COUNT(*) FROM knowledge_files")).scalar()
        texts_count = connection.execute(text("SELECT COUNT(*) FROM text_knowledge")).scalar()

        print(f"\n📊 FINAL Data Verification Summary:")
        print(f"   👥 Users: {users_count}")
        print(f"   🏢 Workspaces: {workspaces_count}")
        print(f"   🎯 Brand Voices: {brand_voices_count}")
        print(f"   🌐 Web Knowledge: {websites_count}")
        print(f"   📁 File Knowledge: {files_count}")
        print(f"   📝 Text Knowledge: {texts_count}")

        # Show test user credentials
        print(f"\n🔑 ALL Test User Credentials (password: 'password123'):")
        users_result = connection.execute(text("SELECT email, display_name FROM users ORDER BY created_at"))
        for user in users_result:
            display = user.display_name or "No display name"
            print(f"   • {user.email} → {display}")

        # Show workspace summary
        print(f"\n🏢 Workspace Summary:")
        workspace_result = connection.execute(text("""
            SELECT w.name, u.display_name as owner_name, u.email as owner_email
            FROM workspace w
            JOIN users u ON w.user_id = u.id
            ORDER BY w.created_at
        """))
        for ws in workspace_result:
            print(f"   • {ws.name} (Owner: {ws.owner_name} - {ws.owner_email})")

def main():
    """Main function to create all comprehensive dummy data"""
    print("🚀 FINAL Complete Dummy Data Setup for Wrext Backend Database")
    print("=" * 80)
    print("📋 This script creates:")
    print("   • 6 comprehensive test users")
    print("   • 5 detailed workspaces")
    print("   • Complete brand voice profiles")
    print("   • Web knowledge with various statuses")
    print("   • File uploads simulation")
    print("   • Rich text content")
    print("=" * 80)

    try:
        print("\n📊 Creating comprehensive dummy data...")

        users = create_users_comprehensive()
        print(f"✅ Processed users: {len(users)} new")

        workspaces = create_workspaces_comprehensive()
        print(f"✅ Processed workspaces: {len(workspaces)} total")

        brand_voices = create_brand_voices_comprehensive()
        print(f"✅ Processed brand voices: {len(brand_voices)} new")

        websites = create_web_knowledge_comprehensive()
        print(f"✅ Processed web knowledge: {len(websites)} new")

        files = create_file_knowledge_comprehensive()
        print(f"✅ Processed file knowledge: {len(files)} new")

        texts = create_text_knowledge_comprehensive()
        print(f"✅ Processed text knowledge: {len(texts)} new")

        memberships = create_workspace_members()
        print(f"✅ Processed workspace memberships: {len(memberships)} new")

        # Verify everything was created
        verify_data_creation()

        print("\n" + "=" * 80)
        print("🎉 COMPLETE DUMMY DATA SETUP FINISHED!")
        print("\n✨ Your database is now fully populated with:")
        print("   • Realistic test users with working credentials")
        print("   • Diverse workspaces with rich metadata")
        print("   • Web knowledge in all processing states")
        print("   • File uploads across different formats")
        print("   • Comprehensive text content")
        print("   • Complete brand voice profiles")
        print("\n🔧 Ready for comprehensive frontend testing!")
        print("\n🔐 REMEMBER: All users have password 'password123'")
        print("🌟 Primary test user: test@example.com")

    except Exception as e:
        print(f"❌ Error in main execution: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()