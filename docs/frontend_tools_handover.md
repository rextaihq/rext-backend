# SEO & Writing Tools API - Frontend Integration Handover Document

## Overview

This document provides complete integration details for frontend engineers connecting to the **Rext AI SEO & Writing Tools API**.

All endpoints are hosted under the prefix `/api/v1/tools`.

---

## Response Wrapper Contract

Every tool endpoint returns responses in the standard `SuccessResponse` envelope:

```json
{
  "success": true,
  "data": { ... },
  "message": "Operation completed successfully",
  "request_id": "req-12345"
}
```

Error responses use the HTTP status (`400`, `413`, `422`, `429`, `500`) and the standard error envelope. Its top-level `message` is written for the visitor; show it as it is:

```json
{
  "success": false,
  "message": "You've reached today's limit for this free tool. Please try again tomorrow.",
  "data": null,
  "error": { "code": "...", "message": "...", "severity": "...", "status_code": 429 }
}
```

---

## Limits

The tools are public (no login) and bounded per UTC day (`src/api/tool/limits.py`):

- **Per visitor:** each address gets 20 calls a day to each tool that runs a model (meta description, title tags, questions, content ideas, grammar, hooks, SEO blog titles, outline, headline analyzer, paragraph rewriter), and 100 a day to each of the other tools. Past that, the tool answers `429`. A request that fails validation (`422`) isn't counted. When the server can't trust the address (`TRUSTED_PROXY_IPS` names no proxy), every caller counts as one visitor.
- **A daily budget for the model tools:** together they spend at most `FREE_TOOLS_DAILY_BUDGET_USD` (US$5 by default). Each call is charged its worst case before it runs: one token per byte of its body, as many times as its prompt repeats a field, plus its output cap. When the budget is used up, every model tool answers `429` ("The free AI tools have reached today's limit. Please try again tomorrow.") until midnight UTC; the other tools go on.
- **Input size:** a model tool's request body is at most 20,000 bytes (about 3,000 words); a longer one gets `413`.
- A `429` carries `Retry-After` (readable from the browser): the seconds until midnight UTC.
- Settings: `FREE_TOOLS_MODEL_CALLS_PER_DAY`, `FREE_TOOLS_CALLS_PER_DAY`, `FREE_TOOLS_DAILY_BUDGET_USD`.

The canonical tag and hreflang generators run no model: Google's rules for both are mechanical. An address without a scheme gets `https://`; one without a host is refused (`400`). Hreflang takes the ISO 639-1 languages, ISO 15924 scripts and ISO 3166-1 regions Google supports (`src/api/tool/iso_codes.py`).

---

## Summary of All Available Tool Endpoints

| Tool Name | Method | Endpoint URL | Purpose / Notes |
| :--- | :--- | :--- | :--- |
| **Title Tag Generator** | `POST` | `/api/v1/tools/title-tags` | Generates 5 SEO titles strictly **50–60 chars** (Pydantic validated) |
| **Grammar Checker** | `POST` | `/api/v1/tools/grammar-checker` | Context-aware proofreader (preserves `Pydantic`, `str`, `len`, `ContentIdea`, code) |
| **Content Outline Generator** | `POST` | `/api/v1/tools/outline-generator` | Auto-calculates section count based on target word count |
| **Headline Analyzer** | `POST` | `/api/v1/tools/headline-analyzer` | Computes CTR score (0–100), sentiment, quality, word count |
| **Hreflang Tag Generator** | `POST` | `/api/v1/tools/hreflang-generator` | Generates Google-compliant XML or HTML hreflang tags with deduplication |
| **Keyword Density Checker** | `POST` | `/api/v1/tools/keyword-density` | Computes exact n-gram counts, phrase frequency & target keyword density % |
| **Paragraph Rewriter** | `POST` | `/api/v1/tools/paragraph-rewriter` | Rewrites paragraphs by goal (*clarity, shorten, expand, professional*) and tone |
| **SERP Preview Tool** | `POST` | `/api/v1/tools/serp-preview` | Computes Google desktop pixel width (~9.5px/char) & truncation warnings |
| **Sitemap Generator** | `POST` | `/api/v1/tools/sitemap-generator` | Generates valid `sitemap.xml` string with XML escaping & deduplication |
| **Word Counter / Metrics** | `POST` | `/api/v1/tools/count_metrics` | Returns word, char, sentence, paragraph counts & reading time |
| **Meta Description Generator** | `POST` | `/api/v1/tools/meta-description/generate` | Generates 120–160 char meta descriptions with validation warnings |
| **Schema Generator** | `POST` | `/api/v1/tools/schema-generator` | Builds Schema.org JSON-LD (Article, Product, FAQ, etc.) |
| **Readability Checker** | `POST` | `/api/v1/tools/readability-checker` | Computes Flesch Reading Ease & Grade level |
| **Canonical Tag Generator** | `POST` | `/api/v1/tools/canonical-tag-generator` | Normalizes & validates canonical URLs |
| **Question Generator** | `POST` | `/api/v1/tools/question-generator` | Generates engaging user questions from text |
| **Link Checker** | `POST` | `/api/v1/tools/link-checker` | Tests if a URL is reachable (HTTP 200) |
| **Content Idea Generator** | `POST` | `/api/v1/tools/content-idea-generator` | Generates viral ideas for specified platforms |
| **Robots.txt Generator** | `POST` | `/api/v1/tools/robots-txt/generate` | Generates valid `robots.txt` plain text files |
| **Hook Generator** | `POST` | `/api/v1/tools/hook-generator` | Brainstorms attention-grabbing content hooks |
| **Blog Topic Generator** | `POST` | `/api/v1/tools/seo-blog-titles` | Generates SEO blog title topics based on word constraints |

---

## Detailed Endpoint Handover Specifications

---

### 1. Title Tag Generator (Audited & Updated)

**Endpoint:** `POST /api/v1/tools/title-tags`  
**Description:** Generates 5 distinct, high-CTR SEO title tags.  
**Strict Requirement:** Every returned title is individually validated via Pydantic (`TitleTag`) to be strictly **50–60 characters inclusive** (counting spaces and punctuation). Non-compliant titles are rejected and revised by the AI until 5 valid titles are obtained. Blind truncation (`title[:60]`) is never used.

#### Request Body Schema: `TitleRequest`
```json
{
  "keyword": "SEO Tools",
  "topic": "Best SEO Software 2026",
  "brand": "BrandName Tech",
  "tone": "Professional"
}
```

#### Response Body Schema: `SuccessResponse[TitleResponse]`
```json
{
  "success": true,
  "data": {
    "titles": [
      "7 Best SEO Tools for 2026 Strategy | BrandName Tech",
      "Ultimate SEO Tools Guide for Growth | BrandName Tech",
      "How to Choose Top SEO Tools Today | BrandName Tech",
      "Latest 2026 SEO Tools Comparison | BrandName Tech!",
      "Premier SEO Tools Solutions Hub | BrandName Tech Inc"
    ]
  },
  "message": "Operation completed successfully",
  "request_id": "req-123"
}
```

---

### 2. Grammar Checker (Audited & Updated)

**Endpoint:** `POST /api/v1/tools/grammar-checker`  
**Description:** Context-aware grammar and proofreading checker. Uses LLM structured output with strict Pydantic validation and correction-integrity filtering.  
**Key Guarantees:**
- **Preserves valid technical terms:** `Pydantic`, `FastAPI`, `LangChain`, `str`, `len`, `ContentIdea`, `TitleTag`, package names, APIs, frameworks.
- **Preserves code:** Inline backticks (`` `...` ``) and fenced code blocks (```...```) are untouched.
- **Zero false positives:** Technical code and terms return **0 issues**.
- **Pydantic Validation:** All reported issues are validated for issue type (`grammar`, `spelling`, `punctuation`, `clarity`), exact presence in original text, and context verifiability.

#### Request Body Schema: `GrammarCheckerRequest`
```json
{
  "text": "This are a test sentence using Pydantic and str."
}
```

#### Response Body Schema: `SuccessResponse[GrammarCheckerResponse]`
```json
{
  "success": true,
  "data": {
    "corrected_text": "This is a test sentence using Pydantic and str.",
    "issues": [
      {
        "original_phrase": "This are",
        "suggested_correction": "This is",
        "issue_type": "grammar"
      }
    ]
  },
  "message": "Operation completed successfully",
  "request_id": "req-456"
}
```

---

### 3. Content Outline Generator (New)

**Endpoint:** `POST /api/v1/tools/outline-generator`  
**Description:** Generates a structured article outline with H2/H3 subheadings and target word counts per section. Automatically calculates section count based on target word count (`<800` -> 4 sections, `800-1500` -> 5 sections, `1501-2500` -> 7 sections, `>2500` -> 9 sections).

#### Request Body Schema: `OutlineGeneratorRequest`
```json
{
  "topic": "Python Web Development in 2026",
  "target_word_count": 1500,
  "tone": "Informative"
}
```

#### Response Body Schema: `SuccessResponse[OutlineGeneratorResponse]`
```json
{
  "success": true,
  "data": {
    "title": "Comprehensive Guide to Python Web Development in 2026",
    "target_word_count": 1500,
    "sections_count": 5,
    "estimated_word_count": 1500,
    "sections": [
      {
        "heading": "1. Introduction to Modern Python Web Development",
        "subheadings": [
          "Evolution of Python Frameworks",
          "Why Choose Python in 2026"
        ],
        "key_points": [
          "Overview of FastAPI and Django ecosystem",
          "Performance benchmark overview"
        ],
        "target_word_count": 250
      }
    ]
  },
  "message": "Operation completed successfully"
}
```

---

### 4. Headline Analyzer (New)

**Endpoint:** `POST /api/v1/tools/headline-analyzer`  
**Description:** Evaluates headlines for CTR, emotional resonance, power words, readability, sentiment, and provides a 0–100 quality score with recommendations.

#### Request Body Schema: `HeadlineAnalyzerRequest`
```json
{
  "headline": "10 Mind-Blowing AI Tools You Need to Try Today"
}
```

#### Response Body Schema: `SuccessResponse[HeadlineAnalyzerResponse]`
```json
{
  "success": true,
  "data": {
    "headline": "10 Mind-Blowing AI Tools You Need to Try Today",
    "score": 88,
    "sentiment": "Positive",
    "word_count": 9,
    "character_count": 46,
    "power_words": ["Mind-Blowing", "Need"],
    "emotional_words": ["Try Today"],
    "recommendations": [
      "Great use of numbers and power words."
    ]
  },
  "message": "Operation completed successfully"
}
```

---

### 5. Hreflang Tag Generator (New)

**Endpoint:** `POST /api/v1/tools/hreflang-generator`  
**Description:** Generates Google-compliant XML sitemap tags (`output_format: "sitemap"`) or HTML `<link rel="alternate" ...>` tags, one per line, with x-default for the default URL. Codes are normalized (`EN_us` is `en-US`, a script as in `zh-Hant-TW` is kept). An entry whose language or region isn't a code is left out with a warning, and so is a repeated code.

#### Request Body Schema: `HreflangRequest`
```json
{
  "language_region_urls": [
    {"url": "https://example.com/en-us", "language": "en", "region": "us"},
    {"url": "https://example.com/es-es", "language": "es", "region": "es"}
  ],
  "default_url": "https://example.com/en-us",
  "include_x_default": true,
  "output_format": "html"
}
```

#### Response Body Schema: `SuccessResponse[HreflangResponse]`
```json
{
  "success": true,
  "data": {
    "hreflang_tags": "<link rel=\"alternate\" hreflang=\"en-US\" href=\"https://example.com/en-us\" />\n<link rel=\"alternate\" hreflang=\"es-ES\" href=\"https://example.com/es-es\" />\n<link rel=\"alternate\" hreflang=\"x-default\" href=\"https://example.com/en-us\" />",
    "warnings": null
  },
  "message": "Operation completed successfully"
}
```

---

### 6. Keyword Density Checker (New)

**Endpoint:** `POST /api/v1/tools/keyword-density`  
**Description:** Analyzes text word counts, top 1-gram single words, 2-gram/3-gram phrase frequencies (excluding stopwords), and exact target keyword density percentage with status classification (*Low*, *Optimal*, *Over-stuffed*).

#### Request Body Schema: `KeywordDensityRequest`
```json
{
  "text": "Python is a great programming language. Python is easy to learn and Python is powerful.",
  "target_keyword": "python"
}
```

#### Response Body Schema: `SuccessResponse[KeywordDensityResponse]`
```json
{
  "success": true,
  "data": {
    "total_words": 15,
    "total_characters": 88,
    "top_single_words": [
      {"keyword": "python", "count": 3, "density_percentage": 20.0},
      {"keyword": "programming", "count": 1, "density_percentage": 6.67}
    ],
    "top_phrases": [
      {"keyword": "great programming", "count": 1, "density_percentage": 6.67}
    ],
    "target_keyword_analysis": {
      "target_keyword": "python",
      "count": 3,
      "density_percentage": 20.0,
      "status": "Over-stuffed (above 2.5%)"
    }
  },
  "message": "Operation completed successfully"
}
```

---

### 7. Paragraph Rewriter (New)

**Endpoint:** `POST /api/v1/tools/paragraph-rewriter`  
**Description:** Rewrites paragraphs using LLM based on specified goal (*improve clarity, shorten, expand, make professional, simplify, more engaging*) and requested tone.

#### Request Body Schema: `ParagraphRewriterRequest`
```json
{
  "text": "Artificial intelligence is getting better every day and helping people create content faster.",
  "goal": "improve clarity",
  "tone": "Professional"
}
```

#### Response Body Schema: `SuccessResponse[ParagraphRewriterResponse]`
```json
{
  "success": true,
  "data": {
    "original_text": "Artificial intelligence is getting better every day and helping people create content faster.",
    "rewritten_text": "Advancements in artificial intelligence are continuously enhancing content generation efficiency.",
    "goal": "improve clarity",
    "tone": "Professional"
  },
  "message": "Operation completed successfully"
}
```

---

### 8. SERP Preview Tool (New)

**Endpoint:** `POST /api/v1/tools/serp-preview`  
**Description:** Calculates Google desktop search preview strings, character counts, desktop pixel width heuristic estimates (~9.5px/char), and truncation warnings (>60 chars title, >160 chars description).

#### Request Body Schema: `SERPPreviewRequest`
```json
{
  "title": "Best SEO Tools 2026 - Comprehensive Review & Buying Guide",
  "description": "Discover the top SEO tools for keyword research, rank tracking, and on-page optimization in 2026.",
  "url": "https://example.com/best-seo-tools"
}
```

#### Response Body Schema: `SuccessResponse[SERPPreviewResponse]`
```json
{
  "success": true,
  "data": {
    "title_preview": "Best SEO Tools 2026 - Comprehensive Review & Buying Guide",
    "title_length": 57,
    "title_truncated": false,
    "description_preview": "Discover the top SEO tools for keyword research, rank tracking, and on-page optimization in 2026.",
    "description_length": 98,
    "description_truncated": false,
    "url_preview": "https://example.com/best-seo-tools",
    "desktop_pixel_width_approx": 541,
    "warnings": []
  },
  "message": "Operation completed successfully"
}
```

---

### 9. Sitemap Generator (New)

**Endpoint:** `POST /api/v1/tools/sitemap-generator`  
**Description:** Generates valid, formatted `sitemap.xml` XML strings from URL lists with XML entity escaping (`&` -> `&amp;`), priority bounds checking (0.0 to 1.0), changefreq validation, and duplicate URL removal.

#### Request Body Schema: `SitemapGeneratorRequest`
```json
{
  "urls": [
    {
      "url": "https://example.com/",
      "priority": 1.0,
      "changefreq": "daily"
    },
    {
      "url": "https://example.com/blog?page=1&ref=home",
      "priority": 0.8,
      "changefreq": "weekly"
    }
  ]
}
```

#### Response Body Schema: `SuccessResponse[SitemapGeneratorResponse]`
```json
{
  "success": true,
  "data": {
    "sitemap_xml": "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n  <url>\n    <loc>https://example.com/</loc>\n    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>\n  <url>\n    <loc>https://example.com/blog?page=1&amp;ref=home</loc>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n</urlset>",
    "total_urls": 2
  },
  "message": "Operation completed successfully"
}
```

---

### 10. Word Counter / Text Metrics

**Endpoint:** `POST /api/v1/tools/count_metrics`

#### Request Body Schema: `TextInput`
```json
{
  "text": "Testing word count and metrics."
}
```

#### Response Body Schema: `SuccessResponse[TextMetricsOutput]`
```json
{
  "success": true,
  "data": {
    "words": 5,
    "characters": 31,
    "sentences": 1,
    "paragraphs": 1,
    "min_read": 1
  }
}
```

---

### 11. Meta Description Generator

**Endpoint:** `POST /api/v1/tools/meta-description/generate`

#### Request Body Schema: `MetaDescriptionRequest`
```json
{
  "page_title": "SEO Strategies for 2026",
  "target_keywords": ["seo", "content strategy"]
}
```

#### Response Body Schema: `SuccessResponse[MetaDescriptionResponse]`
```json
{
  "success": true,
  "data": {
    "meta_description": "Discover effective SEO strategies and content planning techniques for 2026 to boost organic search rankings.",
    "validation": {
      "length": 113,
      "is_optimal_length": false,
      "character_count": "113/160",
      "warnings": ["Length not in optimal range (120-160 characters)"]
    }
  }
}
```

---

### 12. Schema Generator

**Endpoint:** `POST /api/v1/tools/schema-generator`

#### Request Body Schema: `SchemaRequest`
```json
{
  "schema_type": "Article",
  "name": "Understanding Pydantic Validation",
  "description": "A guide on using Pydantic in FastAPI",
  "url": "https://example.com/pydantic-guide",
  "author_name": "Jane Doe"
}
```

#### Response Body Schema: `SuccessResponse[dict]`
```json
{
  "success": true,
  "data": {
    "@context": "https://schema.org",
    "@type": "Article",
    "name": "Understanding Pydantic Validation",
    "description": "A guide on using Pydantic in FastAPI",
    "url": "https://example.com/pydantic-guide",
    "author": {
      "@type": "Person",
      "name": "Jane Doe"
    }
  }
}
```

---

### 13. Readability Checker

**Endpoint:** `POST /api/v1/tools/readability-checker`

#### Request Body Schema: `ReadabilityRequest`
```json
{
  "content": "Python is an easy to learn programming language with clean syntax."
}
```

#### Response Body Schema: `SuccessResponse[ReadabilityResponse]`
```json
{
  "success": true,
  "data": {
    "readability_score": 78.2,
    "grade_level": 6.5,
    "sentence_complexity": 7.1,
    "word_count": 10,
    "sentence_count": 1,
    "reading_level": "Easy"
  }
}
```

---

### 14. Robots.txt Generator

**Endpoint:** `POST /api/v1/tools/robots-txt/generate`

#### Request Body Schema: `RobotsTxtRequest`
```json
{
  "user_agent": "*",
  "allow": ["/public"],
  "disallow": ["/admin", "/private"],
  "sitemap_url": "https://example.com/sitemap.xml"
}
```

#### Response Body Schema: `SuccessResponse[RobotsTxtResponse]`
```json
{
  "success": true,
  "data": {
    "robots_txt": "User-agent: *\nAllow: /public\nDisallow: /admin\nDisallow: /private\nSitemap: https://example.com/sitemap.xml"
  }
}
```

---

## Frontend Integration Tips & Best Practices

1. **Title Tag Display:**  
   Show a live character counter badge (`50–60 chars`). The API guarantees all generated titles satisfy `50 <= title.length <= 60`.
2. **Grammar Checker UI:**  
   Highlight `original_phrase` in the input text with underline/tooltip showing `suggested_correction` and `issue_type` badge (`grammar`, `spelling`, `punctuation`, `clarity`). Provide a "Click to apply correction" action that replaces `original_phrase` with `suggested_correction`.
3. **SERP Preview Widget:**  
   Render a mockup of Google Desktop Search Snippet showing blue title link (`title_preview`), green/grey URL (`url_preview`), and description snippet (`description_preview`). Highlight warnings if present.
4. **Sitemap Copy/Download:**  
   Provide a "Copy XML" button and "Download sitemap.xml" file option for `sitemap_xml`.
