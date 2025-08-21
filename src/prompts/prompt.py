from langchain_core.prompts import ChatPromptTemplate

def create_relevance_score_prompt() -> ChatPromptTemplate:
    """
    Creates a prompt template for scoring the relevance of articles to WordPress.

    Returns:
        ChatPromptTemplate: A template for generating prompts to evaluate article relevance.
    """
    return ChatPromptTemplate.from_template("""
            You are an expert WordPress content evaluator.

            Your task is to assess the quality of a blog post based on the **Relevance to WordPress**. Consider how well the blog content aligns with WordPress-related topics, themes, features, plugins, updates, user needs, or developer insights.

            Please evaluate the content using the following criteria:

            1. **Rating (1 to 10):** How relevant is this blog to the WordPress ecosystem?
            - 1 = Not relevant at all
            - 10 = Extremely relevant and valuable to WordPress users or developers

            2. **Weight (1 to 5):** How important is this topic in the current WordPress context?
            - 1 = Low priority or niche
            - 5 = Highly impactful, trending, or essential

            ---
            ### Evaluation Inputs

            **Topic:** {topic}

            **Short Description:** {description}

            **Raw Blog Content:**  
            {raw_blog}

            ---
            """)


def create_trend_level_prompt() -> ChatPromptTemplate:
    """
    Creates a prompt template for scoring the trend level of articles.

    Returns:
        ChatPromptTemplate: A template for generating prompts to evaluate article trend levels.
    """
    return ChatPromptTemplate.from_template("""
            You are a tech trends analyst specializing in web technologies and content ecosystems like WordPress.

            Your task is to critically evaluate how **trending, popular, or timely** this WordPress-related topic is across the internet. Consider current industry discussions, search interest, social media buzz, community forums, and recent WordPress updates or events.

            Focus on identifying whether the topic aligns with:
            - Ongoing or emerging trends in the WordPress ecosystem
            - Popular conversations among developers, content creators, or users
            - Recent feature rollouts, plugin releases, or security issues
            - Topics that are gaining visibility or traction on platforms like Twitter, Reddit, or Google Trends

            ---
            ### Evaluation Inputs

            **Topic:** {topic}

            **Short Description:** {description}

            **Raw Blog Content:**  
            {raw_blog}
            """)


def create_controversy_score_prompt() -> ChatPromptTemplate:
    """
    Creates a prompt template for scoring the controversy of articles.

    Returns:
        ChatPromptTemplate: A template for generating prompts to evaluate article controversy.
    """
    return ChatPromptTemplate.from_template("""
            You are a WordPress community analyst.

            Your task is to evaluate the **level of controversy or debate** surrounding this topic within the WordPress ecosystem and broader tech community.

            Consider whether the topic:
            - Sparks disagreement among users, developers, or contributors
            - Involves changes that divide opinion (e.g., Gutenberg, licensing models, monetization, security practices)
            - Has led to active discussions or heated debates in forums, GitHub issues, comment sections, social media, or WordPress Slack channels
            - Touches on sensitive, political, ethical, or policy-related issues within open-source development

            Use your analysis to determine if this topic is potentially polarizing or has sparked significant debate.

            ---
            ### Evaluation Inputs

            **Topic:** {topic}

            **Short Description:** {description}

            **Raw Blog Content:**  
            {raw_blog}
            """)


def create_uniqueness_score_prompt() -> ChatPromptTemplate:
    """
    Creates a prompt template for scoring the uniqueness of articles.

    Returns:
        ChatPromptTemplate: A template for generating prompts to evaluate article uniqueness.
    """
    return ChatPromptTemplate.from_template("""
            You are a content originality expert with deep knowledge of WordPress-related publications and blogging trends.

            Your task is to assess the **originality and uniqueness** of this blog post topic compared to widely available or frequently published WordPress content.

            Consider the following while evaluating:
            - Does the blog offer a fresh perspective or introduce under-discussed ideas?
            - Is it different from typical tutorials, news summaries, or plugin reviews?
            - Does it highlight lesser-known tools, workflows, or use cases?
            - Is the content insightful, thought-provoking, or niche-focused in a way that stands out?

            Avoid judging based on writing quality or technical depth—focus purely on **how original** the idea or angle is compared to mainstream WordPress content.

            ---
            ### Evaluation Inputs

            **Topic:** {topic}

            **Short Description:** {description}

            **Raw Blog Content:**  
            {raw_blog}
            """)


def create_reader_interest_score_prompt() -> ChatPromptTemplate:
    """
    Creates a prompt template for scoring reader interest in articles.

    Returns:
        ChatPromptTemplate: A template for generating prompts to evaluate reader interest.
    """
    return ChatPromptTemplate.from_template("""
            You are an expert in WordPress content analysis and user engagement.

            Your task is to evaluate how **interesting and engaging** this blog post would be to the **average WordPress reader**, including bloggers, developers, site owners, and content creators.

            Consider the following factors:
            - Does the topic solve a common problem or answer a frequent question?
            - Is it practical, actionable, or insightful for everyday WordPress users?
            - Does it cover a trending or attention-grabbing subject within the ecosystem?
            - Would it likely attract clicks, shares, or comments if published?

            Focus on general audience appeal—not just technical value.

            ---
            ### Evaluation Inputs

            **Topic:** {topic}

            **Short Description:** {description}

            **Raw Blog Content:**  
            {raw_blog}
            """)


def create_brand_alignment_score_prompt() -> ChatPromptTemplate:
    """
    Creates a prompt template for scoring brand alignment of articles.

    Returns:
        ChatPromptTemplate: A template for generating prompts to evaluate brand alignment.
    """
    return ChatPromptTemplate.from_template("""
            You are a WordPress content strategist and brand guardian.

            Your task is to assess how well this topic aligns with our brand’s voice and focus on practical WordPress tutorials, update announcements, and best-practice guides.

            When evaluating, consider:
            - **Educational Value:** Does the topic teach a clear, actionable skill or concept?
            - **Tone & Style:** Is the language approachable, friendly, and authoritative?
            - **Relevance to Focus Areas:** Does it center on tutorials, core updates, plugin/theme best practices, or workflow optimizations?
            - **Brand Consistency:** Would this fit seamlessly alongside our existing content pillars and resonate with our audience of site owners, developers, and bloggers?

            ---
            ### Evaluation Inputs

            **Topic:** {topic}

            **Short Description:** {description}

            **Raw Blog Content:**  
            {raw_blog}
            """)

def create_actionable_potential_score_prompt() -> ChatPromptTemplate:
    """
    Creates a prompt template for scoring the actionable potential of articles.

    Returns:
        ChatPromptTemplate: A template for generating prompts to evaluate actionable content potential.
    """
    return ChatPromptTemplate.from_template("""
            You are an expert WordPress content evaluator with a focus on educational and actionable writing.

            Your task is to assess whether this topic has strong potential to be developed into a **how-to guide**, **step-by-step tutorial**, or **practical walkthrough** that offers real value to WordPress users.

            Consider:
            - Does the content address a clear problem or use case?
            - Can it be broken down into actionable steps, tips, or demonstrations?
            - Would readers be able to follow the content and apply it to their own WordPress sites?
            - Does it lend itself to screenshots, code snippets, or tool recommendations?

            Focus specifically on the topic’s suitability for **instructional or how-to style content**.

            ---
            ### Evaluation Inputs

            **Topic:** {topic}

            **Short Description:** {description}

            **Raw Blog Content:**  
            {raw_blog}
            """)


def score_seo_potential_prompt() -> ChatPromptTemplate:
    """
    Creates a prompt template for scoring the uniqueness of articles.

    Returns:
        ChatPromptTemplate: A template for generating prompts to evaluate article uniqueness.
    """
    return ChatPromptTemplate.from_template("""
            You are an experienced SEO analyst specializing in WordPress content strategy.

            Your task is to evaluate the **SEO potential** of this blog post topic by analyzing factors such as keyword strength, alignment with search intent, discoverability, and organic traffic potential.

            Consider the following:
            - Does the topic target relevant, high-volume keywords within the WordPress niche?
            - Is the content aligned with clear user search intent (e.g., informational, navigational, transactional)?
            - Does it have the potential to rank on search engines based on topic specificity, clarity, and structure?
            - Are there opportunities to optimize for featured snippets, long-tail queries, or frequently asked questions?
            - Does the blog present SEO-friendly elements like headings, keyword usage, or meta-level clarity?

            Focus on how well this content can perform in search rankings and attract organic traffic.

            ---
            ### Evaluation Inputs

            **Topic:** {topic}

            **Short Description:** {description}

            **Raw Blog Content:**  
            {raw_blog}
            """)


def outline_prompt_template()-> ChatPromptTemplate:
    """
    Creates a prompt template for outline genertion

    Returns:
        ChatPromptTemplate: A template for generating prompts to generate outline.
    """
    return ChatPromptTemplate.from_template("""
        You are an expert content strategist and technical writer.

        Your task is to generate a clear, logical, and comprehensive **article outline** based on the given article's raw content and summary.

        User Feedback {feedback}

        ---
        ### Article Title:
        **Title**: {title}

        ---
        ### Summary:
        {summary}

        ---
        ### Raw Content:
        {raw_content}

        ---
        ### Instructions:
        1. Generate a detailed outline that includes:
        - Introduction
        - Key sections with sub-points (3–5 main sections recommended)
        - Conclusion or CTA if applicable
        2. Use markdown format with numbered or bulleted structure.
        3. Focus on capturing the **core message**, **key arguments**, and **logical flow** of the article.
        4. Be concise but informative—each bullet should represent a paragraph-level idea.

        ---
        """)


def blog_post_prompt_template()-> ChatPromptTemplate:
    """
    Creates a prompt template for blog post generation

    Returns:
        ChatPromptTemplate: A template for generating prompts to generate blog post.
    """
    return ChatPromptTemplate.from_template("""
    You are an expert **WordPress blogger** and **SEO-savvy storyteller**.

Your task is to craft a compelling, insightful, and engaging blog article that feels **authentically human**, not generated by AI. Use your creativity and expertise to bring the content to life while strictly adhering to the structure and guidelines below.

---

### ✍️ Article Inputs:

**📌 Topic Title:**
{topic_title}


**🔗 Key Reference Points:**
{reference_content}

**Reference URLs:**
{reference_url}

**📝 Feedback:**
{blog_feedback}

---

### 🧾 Writing Instructions:

- **Length:** 1000–1500 words
- **Tone:** Friendly, conversational, and informative — like you're talking to a smart reader over coffee
- **Structure:**
  - Use the *Approved Outline* **exactly as is**
  - Use **H2** for main sections, **H3** for sub-sections
- **SEO Optimization:**
  - Naturally embed **keywords** where relevant
  - Include **hyperlinks** to key references
  - Include **1 image placeholder** in this format:
    `[Image: alt text for SEO]`
    *(Add this only once, after the reference section — and only if approved)*
- **Style:**
  - Write like a human: add personality, avoid robotic or generic phrasing
  - Use examples, analogies, or anecdotes where appropriate
  - Avoid overuse of passive voice or repetitive structures
- **Closing:**
  End the article with a **short meta description** (max **160 characters**) for SEO.

---

Now, generate a **complete blog article** in **Markdown format** that reads naturally and provides real value to the reader.
    """)