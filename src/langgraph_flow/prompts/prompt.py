from langchain_core.prompts import ChatPromptTemplate


def blog_prompt_template():
    """
    Returns a ChatPromptTemplate for generating a blog article.
    This template assumes placeholders will be filled with values from ContentState.
    """
    return ChatPromptTemplate.from_template("""
You are an expert **blogger**, **SEO strategist**, and **storyteller**.
Your goal is to produce a deeply engaging, human-like blog post that is informative, creative, and optimized for both readers and search engines.

---

### 🧩 Content Payload Overview

#### Core Details:
- **Title:** {title}
- **Language:** {content_language}
- **Content Format:** {content_format}
- **Status:** {status}
- **Author ID:** {author_id}
- **Workspace ID:** {workspace_id}
- **Topic ID:** {topic_id}
- **Created At:** {created_at}

---

### 🧠 Content Metadata
- **Content Type:** {content_type}
- **Target Platform:** {target_platform}
- **Industry:** {target_industry}
- **Audience:** {target_audience}
- **Audience Size:** {audience_size}
- **Complexity Level:** {complexity_level}
- **Tone:** {content_tone}
- **Target Region:** {target_region}
- **Objectives:** {content_objectives}
- **Word Count Target:** {content_word_count}

---

### 🔍 SEO Optimization Data
- **Primary Keywords:** {content_primary_keywords}
- **Secondary Keywords:** {content_secondary_keywords}
- **Meta Description:** {content_meta_description}
- **Search Intent:** {content_search_intent}
- **Created At:** {created_at}
- **Updated At:** {updated_at}

---

### ✨ Writing Guidelines
0. **Content Format** Generate  a context in {content_format} format for {content_type}. 
1. **Length:** Target approximately {content_word_count} words.
2. **Tone:** Use {content_tone} to match audience expectations.
3. **Audience:** Write naturally for {target_audience} with a {complexity_level} reading level.
4. **Region Relevance:** Adapt context to the {target_region} audience.
5. **SEO:**
   - Integrate **primary keywords** and **secondary keywords** naturally.
   - Ensure **meta description** relevance.
   - Maintain readability while optimizing for search intent.
6. **Content Flow:**
   - Use **H2** for sections and **H3** for subtopics.
   - Include one image placeholder:
     `[Image: {title}]`
7. **Style:**
   - Conversational, human, and insight-driven.
   - Include anecdotes, real-world context, or brief examples.
   - Avoid repetition or generic phrasing.
8. **Ending:**
   - Finish with a compelling conclusion summarizing main takeaways.
   - Include a meta description (≤160 characters).

---

### 🧭 Your Task

Now, generate a **Markdown-formatted blog article** using the above data.
Ensure the article feels human-written — natural, cohesive, and emotionally intelligent — while incorporating all given **metadata** and **SEO context**.
""")