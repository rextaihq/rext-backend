# src/flow/tracing/prompt_manager.py

from langchain_core.prompts import ChatPromptTemplate
from src.flow.langsmith.get_client import get_client


class PromptManager:
    """
    Centralized manager for creating and registering prompts in LangSmith.
    Handles prompt creation, LangSmith sync, and retrieval.
    """

    def __init__(self,auto_register=False):
        self.client = get_client()
        self.prompts = {}
        self.auto_register = auto_register

        # register only if auto register is true
        if self.auto_register:
            self.setup_default_prompts()

    
    # =====================================================
    # 🧠 PROMPT CREATION METHODS
    # =====================================================

    def create_topic_generation_prompt(self) -> ChatPromptTemplate:
        """
        Construct a LangChain ChatPromptTemplate for topic generation
        based on TopicGeneration input.
        """
        try:
            # 🧠 System message — defines role and tone
            system_message = """
            You are an expert **content strategist**, **SEO analyst**, and **creative blogger**.
            Your job is to brainstorm unique, high-impact blog post topics that are:
            - SEO-friendly,
            - aligned with target audience interests,
            - and relevant to the provided industry and keywords.

            Each topic should feel fresh, engaging, and click-worthy.
            """

            user_message = """
            You are an AI assistant that generates high-quality, creative, and relevant content topic ideas.

            ### Context:
            - Wizard Mode: {wizardMode}
            - Industry: {industry}
            - Industry (Other): {industry_other}
            - Subject: {subject}
            - Audience: {audience}
            - Purpose: {purpose}
            - Purpose (Other): {purpose_other}
            - Number of Topics Required: {num_topics}
            - Timestamp: {timestamp}

            ### Task:
            Generate {num_topics} creative and engaging topic ideas. 
            For each topic, provide:
            - **Title**: A catchy headline
            - **Angle**: The specific perspective or unique approach
            - **Description**: A short explanation of the topic
            - **Channel Fit**: Best platforms/channels (e.g. blog, social media, newsletter)
            - **Audience Fit**: Which audience segment will find this valuable
            - **Why It Works**: Explain briefly why this idea would succeed
            - **Tags**: Relevant categorization tags

            Format the output as **JSON array** of objects with this structure:
            [
            {{
                "title": "Example Title",
                "angle": "Unique angle",
                "description": "A comprehensive explanation of what this content will cover and why it's valuable",
                "channel_fit": ["blog", "social-media"],
                "audience_fit": ["developers", "tech enthusiasts"],
                "why_it_works": "Reason why this is a strong idea",
                "scores": {{
                    "relevance": 0.95,
                    "seo_potential": 0.88,
                    "trend_level": 0.92,
                    "uniqueness": 0.75,
                    "reader_interest": 0.90,
                    "actionable_potential": 0.95,
                    "brand_alignment": 0.85,
                    "controversy": 0.15
                }},
                "tags": ["AI", "Robotics", "Healthcare"]
            }}
            ]
            """
            return ChatPromptTemplate.from_messages([
                ("system", system_message.strip()),
                ("user", user_message.strip())
            ])
        except Exception as e:
            raise Exception(f"Error occurred while registering topics prompt: {str(e)}")

    def create_blog_generation_prompt(self) -> ChatPromptTemplate:
        """
        Returns a ChatPromptTemplate for generating a blog article.
        This template assumes placeholders will be filled with values from ContentState.
        """
        try:
            # define the system message
            system_message = """
            You are an expert **blogger**, **SEO strategist**, and **storyteller**.
            Your goal is to produce a deeply engaging, human-like blog post that is informative, creative, and optimized for both readers and search engines.
            """

            # user messages
            user_message = """
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
            0. **Content Format** Generate a context in {content_format} format for {content_type}. 
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

            Now, generate a **{content_format} blog article** using the above data.
            Ensure the article feels human-written — natural, cohesive, and emotionally intelligent — while incorporating all given **metadata** and **SEO context**.
            """
            return ChatPromptTemplate.from_messages([
                ("system", system_message.strip()),
                ("user", user_message.strip())
            ])
        except Exception as e:
            raise Exception(f"Error occurred while registering prompt: {str(e)}")

    # =====================================================
    # 🗂️ REGISTRATION METHODS
    # =====================================================

    def register_prompt(self, name: str, prompt: ChatPromptTemplate, description: str = "", is_public: bool = False):
        """Registers a prompt with LangSmith and stores it locally."""
        try:
            self.client.push_prompt(
                prompt_identifier=name,
                object=prompt,
                is_public=is_public,
                description=description,
            )
            self.prompts[name] = prompt
            print(f"✅ Registered prompt: {name}")
        except Exception as e:
            print(f"❌ Failed to register {name}: {str(e)}")

    # =====================================================
    # 🧭 UTILITY METHODS
    # =====================================================

    def setup_default_prompts(self):
        """Creates and registers all core prompts."""
        topic_prompt = self.create_topic_generation_prompt()
        self.register_prompt(
            "topic_generation_v1",
            topic_prompt,
            "Generates SEO-optimized blog topics.",
        )

        blog_prompt = self.create_blog_generation_prompt()
        self.register_prompt(
            "blog_generation_v1",
            blog_prompt,
            "Generates full blog articles from metadata.",
        )

    def get_prompt(self, name: str) -> ChatPromptTemplate:
        """Retrieve a prompt from memory."""
        try:
            prompt = self.client.pull_prompt(name, include_model=True)
            if prompt:
                return prompt
        except Exception as e:
            raise Exception(f"Error occurred while Loading {name} prompt: {str(e)}")