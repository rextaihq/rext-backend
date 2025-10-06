"""seed004_content_data

Revision ID: 433637d4726c
Revises: b68e304117f0
Create Date: 2025-10-03 16:29:09.543687

Seeds sample content data for testing and development.
Creates 5 content items with full supporting data:
- content records (main table)
- content_metadata (descriptions, audience, etc.)
- content_seo_data (keywords, meta descriptions)
- content_ai_config (AI generation settings)
- content_structure (structure preferences)
- content_progress (for items being generated)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
import uuid
import json


# revision identifiers, used by Alembic.
revision: str = '433637d4726c'
down_revision: Union[str, Sequence[str], None] = 'b68e304117f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed sample content data."""

    connection = op.get_bind()

    # Fetch existing data
    workspaces = connection.execute(
        sa.text("SELECT id FROM workspace ORDER BY created_at LIMIT 3")
    ).fetchall()

    users = connection.execute(
        sa.text("SELECT id FROM users WHERE deleted_at IS NULL ORDER BY created_at LIMIT 5")
    ).fetchall()

    topics = connection.execute(
        sa.text("SELECT id FROM topics ORDER BY created_at LIMIT 2")
    ).fetchall()

    if not workspaces or not users:
        print("⚠️  No workspaces or users found. Skipping content seed.")
        return

    print("\n" + "="*80)
    print("SEEDING CONTENT DATA")
    print("="*80)
    print(f"Available workspaces: {len(workspaces)}")
    print(f"Available users: {len(users)}")
    print(f"Available topics: {len(topics)}")
    print()

    # Sample content data
    content_samples = [
        {
            "title": "10 AI Marketing Strategies That Drive Results in 2024",
            "slug": "10-ai-marketing-strategies-drive-results-2024",
            "content_type": "Blog Post",
            "status": "published",
            "body_markdown": """# 10 AI Marketing Strategies That Drive Results in 2024

## Introduction

AI marketing is transforming how businesses engage with customers. This comprehensive guide explores proven strategies that deliver measurable results.

## Key Strategies

1. **Personalized Content Generation** - Use AI to create tailored content at scale
2. **Predictive Analytics** - Forecast customer behavior and optimize campaigns
3. **Chatbot Automation** - Provide 24/7 customer support with intelligent bots

[Read more...]""",
            "keywords": ["AI marketing", "marketing automation", "digital marketing"],
            "meta_description": "Discover 10 proven AI marketing strategies that drive real results in 2024. Learn how to leverage AI for personalized content, analytics, and automation."
        },
        {
            "title": "Complete Guide to SEO Content Optimization",
            "slug": "complete-guide-seo-content-optimization",
            "content_type": "Guide",
            "status": "ready",
            "body_markdown": """# Complete Guide to SEO Content Optimization

## Introduction

Learn the fundamentals of SEO content optimization to improve your search rankings and drive organic traffic.

## Core Principles

- **Keyword Research** - Find the right keywords for your audience
- **On-Page SEO** - Optimize titles, meta descriptions, and content structure
- **Content Quality** - Create valuable, engaging content that ranks

[Continue reading...]""",
            "keywords": ["SEO optimization", "content marketing", "search ranking"],
            "meta_description": "Master SEO content optimization with this comprehensive guide. Learn keyword research, on-page SEO, and content quality best practices."
        },
        {
            "title": "How to Build a Content Marketing Strategy",
            "slug": "how-to-build-content-marketing-strategy",
            "content_type": "Blog Post",
            "status": "draft",
            "body_markdown": """# How to Build a Content Marketing Strategy

## Getting Started

A solid content strategy starts with understanding your audience and business goals.

## Key Components

1. **Audience Research** - Know who you're creating content for
2. **Content Planning** - Map out topics and formats
3. **Distribution Channels** - Choose the right platforms

[Draft continues...]""",
            "keywords": ["content strategy", "content marketing", "marketing planning"],
            "meta_description": "Build an effective content marketing strategy from scratch. Learn audience research, content planning, and distribution tactics."
        },
        {
            "title": "AI Tools for Content Creators in 2024",
            "slug": "ai-tools-for-content-creators-2024",
            "content_type": "Listicle",
            "status": "generating",
            "body_markdown": None,  # Being generated
            "keywords": ["AI tools", "content creation", "productivity"],
            "meta_description": "Explore the best AI tools for content creators in 2024. Boost your productivity with these cutting-edge solutions."
        },
        {
            "title": "Data-Driven Marketing: Best Practices",
            "slug": "data-driven-marketing-best-practices",
            "content_type": "White Paper",
            "status": "ready",
            "body_markdown": """# Data-Driven Marketing: Best Practices

## Executive Summary

Discover how to leverage data to drive marketing decisions and improve ROI.

## Core Practices

- **Analytics Setup** - Implement comprehensive tracking
- **Data Analysis** - Extract actionable insights
- **Campaign Optimization** - Use data to improve performance

[White paper continues...]""",
            "keywords": ["data-driven marketing", "marketing analytics", "ROI optimization"],
            "meta_description": "Learn data-driven marketing best practices to improve ROI. Master analytics, insights, and campaign optimization."
        },
    ]

    created_count = 0
    now = datetime.now(timezone.utc)

    # Create content for each sample
    for idx, sample in enumerate(content_samples):
        workspace_id = workspaces[idx % len(workspaces)][0]
        user_id = users[idx % len(users)][0]
        topic_id = topics[idx % len(topics)][0] if topics and idx < len(topics) else None
        content_id = uuid.uuid4()

        # Insert content
        connection.execute(
            sa.text("""
                INSERT INTO content (
                    id, workspace_id, topic_id, created_by_user_id,
                    title, slug, body_markdown, content_format, status, content_language,
                    created_at, updated_at
                ) VALUES (
                    :id, :workspace_id, :topic_id, :user_id,
                    :title, :slug, :body_markdown, 'Markdown', :status, 'English',
                    :created_at, :updated_at
                )
            """),
            {
                "id": content_id,
                "workspace_id": workspace_id,
                "topic_id": topic_id,
                "user_id": user_id,
                "title": sample["title"],
                "slug": sample["slug"],
                "body_markdown": sample.get("body_markdown"),
                "status": sample["status"],
                "created_at": now,
                "updated_at": now,
            }
        )

        # Insert content_metadata
        connection.execute(
            sa.text("""
                INSERT INTO content_metadata (
                    content_id, content_type, content_summary, target_audience,
                    content_tone, content_word_count, reading_time_minutes,
                    created_at, updated_at
                ) VALUES (
                    :content_id, :content_type, :summary, :audience,
                    :tone, :word_count, :reading_time,
                    :created_at, :updated_at
                )
            """),
            {
                "content_id": content_id,
                "content_type": sample["content_type"],
                "summary": f"Summary for {sample['title'][:50]}...",
                "audience": ["Marketing Directors", "Content Strategists", "Business Owners"],
                "tone": ["Professional", "Insightful", "Practical"],
                "word_count": 2500 if sample.get("body_markdown") else 0,
                "reading_time": 10 if sample.get("body_markdown") else 0,
                "created_at": now,
                "updated_at": now,
            }
        )

        # Insert content_seo_data
        connection.execute(
            sa.text("""
                INSERT INTO content_seo_data (
                    content_id, content_primary_keywords, content_secondary_keywords,
                    content_meta_description, content_search_intent,
                    content_seo_score, content_readability_score,
                    created_at, updated_at
                ) VALUES (
                    :content_id, :primary_keywords, :secondary_keywords,
                    :meta_description, :search_intent,
                    :seo_score, :readability_score,
                    :created_at, :updated_at
                )
            """),
            {
                "content_id": content_id,
                "primary_keywords": sample["keywords"],
                "secondary_keywords": ["digital transformation", "business growth"],
                "meta_description": sample["meta_description"],
                "search_intent": ["informational", "commercial"],
                "seo_score": 85.5,
                "readability_score": 72.3,
                "created_at": now,
                "updated_at": now,
            }
        )

        # Insert content_ai_config
        connection.execute(
            sa.text("""
                INSERT INTO content_ai_config (
                    content_id, ai_model, temperature, max_output_tokens,
                    top_p, frequency_penalty, generation_params,
                    created_at
                ) VALUES (
                    :content_id, :ai_model, :temperature, :max_tokens,
                    :top_p, :frequency_penalty, :params,
                    :created_at
                )
            """),
            {
                "content_id": content_id,
                "ai_model": "gpt-4",
                "temperature": 0.7,
                "max_tokens": 4000,
                "top_p": 0.9,
                "frequency_penalty": 0.3,
                "params": json.dumps({"style": "professional", "tone": "informative"}),
                "created_at": now,
            }
        )

        # Insert content_structure
        connection.execute(
            sa.text("""
                INSERT INTO content_structure (
                    content_id, content_length, include_toc, include_summary,
                    include_cta, include_key_takeaways, include_examples,
                    include_statistics, created_at, updated_at
                ) VALUES (
                    :content_id, :length, :toc, :summary,
                    :cta, :takeaways, :examples,
                    :statistics, :created_at, :updated_at
                )
            """),
            {
                "content_id": content_id,
                "length": json.dumps({"min_words": 2000, "max_words": 3000, "target_words": 2500}),
                "toc": True,
                "summary": True,
                "cta": True,
                "takeaways": True,
                "examples": True,
                "statistics": True,
                "created_at": now,
                "updated_at": now,
            }
        )

        # Insert content_progress for "generating" status
        if sample["status"] == "generating":
            connection.execute(
                sa.text("""
                    INSERT INTO content_progress (
                        content_id, current_step, progress_percent,
                        status_message, step_details,
                        created_at, updated_at
                    ) VALUES (
                        :content_id, :step, :percent,
                        :message, :details,
                        :created_at, :updated_at
                    )
                """),
                {
                    "content_id": content_id,
                    "step": "writing",
                    "percent": 65,
                    "message": "Generating content sections...",
                    "details": json.dumps({"sections_completed": 3, "sections_total": 5}),
                    "created_at": now,
                    "updated_at": now,
                }
            )

        created_count += 1
        topic_str = f" (linked to topic)" if topic_id else ""
        print(f"✓ Created: {sample['title'][:50]}... [{sample['status']}]{topic_str}")

    print()
    print("="*80)
    print(f"✅ CONTENT SEED COMPLETE!")
    print("="*80)
    print(f"  • Content items created: {created_count}")
    print(f"  • Metadata records: {created_count}")
    print(f"  • SEO records: {created_count}")
    print(f"  • AI config records: {created_count}")
    print(f"  • Structure records: {created_count}")
    print(f"  • Progress records: 1 (for generating content)")
    print(f"  • Total records: {created_count * 5 + 1}")
    print("="*80)
    print()


def downgrade() -> None:
    """
    This is a data seeding migration.
    Downgrade is not supported as it would delete sample/test data.
    If you need to remove seeded content, do it manually via SQL.
    """
    print("⚠️  Downgrade not supported for data seeding migrations")
    print("   If you need to remove seeded content, use SQL:")
    print("   DELETE FROM content WHERE slug LIKE '%-2024' OR slug LIKE 'complete-guide-%';")
    pass
