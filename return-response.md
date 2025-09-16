# Return Response

## User-Friendly Topic Response Structure

This response structure is designed for **non-technical users** (marketers, content creators, small business owners). Technical RAG/AI settings are handled in the backend, while users see simplified, marketing-focused options.

### What Users See vs What's Hidden:

**✅ User-Friendly Fields (Show in UI):**
- Content goals, audience, tone
- Simple research toggles ("Include latest info", "Include examples")  
- Content structure and length options
- SEO keywords and content hooks
- Writing style preferences

**❌ Technical Fields (Hide from UI, use in backend):**
- RAG parameters (retrieval_K, similarity thresholds)
- AI model settings (temperature, top_P)  
- Vector search configurations
- API rate limiting settings
- Token management

```json
{{
    // Core topic information
    "id": "topic_001", // Unique identifier for the topic
    "title": "Building AI-Powered WordPress Chatbots: A Complete Guide", // Main headline for the content
    "angle": "Step-by-step tutorial for non-technical WordPress users to integrate AI chatbots using popular plugins", // Unique perspective or approach
    "description": "A comprehensive guide that walks WordPress site owners through the process of adding AI-powered chatbots to their websites without coding. Covers plugin selection, setup, customization, and optimization for better user engagement and lead generation.", // Detailed explanation of what the content will cover
    "channel_fit": ["blog", "social-media", "newsletter"], // Best platforms for this content. Options: blog, social-media, newsletter, youtube, podcast, webinar, email-series
    "audience_fit": ["wordpress-users", "small-business-owners", "bloggers"], // Target audience segments. Options: consumers, businesses, enterprises, students, professionals, seniors, teens, parents, developers, marketers, designers, entrepreneurs, freelancers
    "why_it_works": "AI chatbots are trending, WordPress users need practical guidance, and this fills the gap between technical documentation and beginner-friendly tutorials", // Justification for why this topic is valuable
    "tags": ["WordPress", "AI", "Chatbots", "Plugins", "Tutorial"], // Categorization tags
    
    // Comprehensive scoring from evaluation system (0.0 to 1.0)
    "scores": {{
      "relevance": 0.95, // How relevant to WordPress ecosystem (from existing evaluation)
      "seo_potential": 0.88, // SEO ranking potential (from existing evaluation)
      "trend_level": 0.92, // How trending/popular this topic is (from existing evaluation)
      "uniqueness": 0.75, // How original compared to existing content (from existing evaluation)
      "reader_interest": 0.90, // Engagement potential with readers (from existing evaluation)
      "actionable_potential": 0.95, // How suitable for how-to/tutorial content (from existing evaluation)
      "brand_alignment": 0.85, // How well it fits brand voice (from existing evaluation)
      "controversy": 0.15 // Potential for debate/polarization (lower = safer)
    }},

    // User-friendly defaults for content generation form (non-technical)
    "suggested_defaults": {{
      "platform": "Website", // Pre-filled platform choice. Options: Website, Social Media
      "industry": "Technology", // Pre-filled industry from topic generation input. Options: Technology, Healthcare, Finance, Education, E-commerce, Real Estate, Food & Beverage, Travel, Fashion, Automotive, Entertainment, Non-profit, Government, Consulting, Manufacturing, Other
      "audienceType": ["Small Businesses", "Professionals", "Consumers"], // Suggested audience types based on industry. Options: Consumers, Businesses, Enterprises, Students, Professionals, Seniors, Teens, Parents, Developers, Marketers, Designers, Entrepreneurs, Freelancers, Decision Makers, Investors
      "readingLevel": ["Beginner", "Intermediate"], // Complexity level suggestions. Options: Beginner, Intermediate, Advanced, Expert
      "goals": ["Educate", "Drive SEO", "Thought Leadership"], // Primary content goals this topic supports. Options: Educate, Entertain, Inspire, Persuade, Promote, Drive SEO, Thought Leadership, Generate Leads, Build Community, Announce News
      "tone": ["Friendly", "Professional"], // Recommended tone options. Options: Professional, Casual, Friendly, Humorous, Serious, Technical, Simple, Inspirational, Authoritative, Conversational, Formal, Playful, Urgent, Empathetic
      "region": "International", // Geographic focus suggestion. Options: International/Global, United States, Canada, United Kingdom, Australia, India, Germany, France, Spain, Italy, Japan, China, Brazil, Mexico, Other
      "contentLength": "Medium (2000-2500 words)", // User-friendly length description. Options: Short (500-1000 words), Medium (1000-2500 words), Long (2500-4000 words), Very Long (4000+ words), Custom
      "primaryKeywords": ["WordPress chatbot", "AI chatbot WordPress", "WordPress AI integration"], // Main SEO targets - array of suggested keywords
      "secondaryKeywords": ["chatbot plugins", "WordPress automation", "AI customer service"], // Supporting keywords - array of suggested keywords  
      "includeTOC": true, // Whether to include table of contents. Options: true, false
      "includeSummary": true, // Whether to include executive summary. Options: true, false
      "includeKeyTakeaways": true, // Whether to include key points section. Options: true, false
      "includeCTABlock": true, // Whether to include call-to-action. Options: true, false
      "contentStyle": "Step-by-step Tutorial" // User-friendly content type description. Options: Tutorial, How-to Guide, List Article, Comparison, Review, Case Study, Opinion Piece, News Article, Interview, Research Report, Infographic Script, Video Script
    }},

    // Shows which content goals this topic naturally supports
    "goal_alignment": {{
      "primary_goals": ["Educate", "Drive SEO"], // Goals this topic is perfect for. Available goals: Educate, Entertain, Inspire, Persuade, Promote, Drive SEO, Thought Leadership, Generate Leads, Build Community, Announce News
      "secondary_goals": ["Thought Leadership", "Promote"], // Goals this topic can support
      "goal_difficulty": {{ // How hard it is to achieve each goal with this topic. Levels: easy, medium, hard
        "Educate": "easy", // Very suitable for educational content
        "Drive SEO": "easy", // High search volume potential
        "Persuade": "medium", // Moderate persuasion potential
        "Entertain": "hard" // Not naturally entertaining
      }}
    }},

    // Content creation guidance and structure recommendations
    "content_guidance": {{
      "recommended_structure": "tutorial", // Best content format. Options: tutorial, guide, comparison, opinion, case-study, review, list-article, news, interview, research-report
      "research_complexity": "medium", // How much research needed. Options: easy, medium, hard
      "estimated_sections": [ // Suggested content outline - array of section titles
        "Introduction to AI Chatbots for WordPress",
        "Choosing the Right Chatbot Plugin",
        "Step-by-Step Installation Guide", 
        "Customization and Configuration",
        "Best Practices and Optimization",
        "Troubleshooting Common Issues"
      ],
      "content_hooks": {{ // Ready-to-use content elements
        "opening_angles": [ // Compelling ways to start the article - array of hook suggestions
          "Did you know 67% of consumers prefer chatbots for quick customer service?",
          "Transform your WordPress site into a 24/7 customer service powerhouse",
          "Stop losing leads while you sleep - here's how AI chatbots can help"
        ],
        "key_questions": [ // Important questions the content should answer - array of questions
          "Which chatbot plugin is best for beginners?",
          "How much does it cost to add AI chatbots to WordPress?",
          "Can I customize chatbot responses without coding?"
        ],
        "pain_points": [ // Reader frustrations this content addresses - array of pain points
          "Missing customer inquiries outside business hours",
          "Repetitive customer service questions eating up time",
          "Technical complexity of AI integration"
        ]
      }},
      "seo_opportunities": {{ // SEO optimization hints
        "featured_snippet_potential": "high", // Likelihood of ranking in featured snippets. Options: low, medium, high
        "long_tail_keywords": [ // Specific phrases to target - array of keyword suggestions
          "how to add chatbot to wordpress without coding",
          "best free wordpress chatbot plugins 2024",
          "wordpress ai customer service setup"
        ],
        "search_volume_estimate": "medium-high" // Expected search traffic potential. Options: low, medium, medium-high, high, very-high
      }}
    }},

    // Audience-specific adaptations for different reader types
    "audience_insights": {{
      "small_business_focus": {{ // For small business owners
        "tone_suggestions": ["Friendly", "Simple"], // More approachable tone. Tone options: Professional, Casual, Friendly, Humorous, Serious, Technical, Simple, Inspirational, Authoritative, Conversational, Formal, Playful, Urgent, Empathetic
        "content_style": "step-by-step guide", // Practical focus. Style options: step-by-step guide, comprehensive tutorial, quick overview, detailed analysis, case study, comparison guide
        "reading_level": "Beginner", // Simpler language. Levels: Beginner, Intermediate, Advanced, Expert
        "emphasis": "Cost-effectiveness and ease of use" // What to highlight for this audience
      }},
      "professional_focus": {{ // For technical professionals
        "tone_suggestions": ["Professional", "Technical"], // More formal approach. Tone options: Professional, Casual, Friendly, Humorous, Serious, Technical, Simple, Inspirational, Authoritative, Conversational, Formal, Playful, Urgent, Empathetic
        "content_style": "comprehensive tutorial", // In-depth coverage. Style options: step-by-step guide, comprehensive tutorial, quick overview, detailed analysis, case study, comparison guide
        "reading_level": "Intermediate", // More technical language. Levels: Beginner, Intermediate, Advanced, Expert
        "emphasis": "Advanced features and ROI" // What to highlight for this audience
      }}
    }},

    // Backend research configuration (hidden from users, used internally)
    "internal_research_config": {{
      "enableSimilarArticles": true, // Whether to fetch similar content (based on uniqueness score)
      "maxSimilarArticles": 4, // How many similar articles to analyze
      "researchDepth": "Comprehensive", // Basic/Comprehensive (based on topic complexity)
      "includeCompetitorAnalysis": true, // Whether to analyze competing content
      "searchQuerySeeds": ["WordPress chatbot tutorial", "AI chatbot plugins", "WordPress automation guide"], // Research query suggestions
      "dateRange": "6M", // How recent sources should be (6M/1Y/2Y based on trend level)
      "sourcesAllowed": ["Website", "Blog", "News"], // Types of sources to include
      "includeNews": true, // Whether to include recent news (trending topics = yes)
      "retrievalK": 10 // Number of sources to retrieve for context
    }},

    // Simple user settings (what users actually see and control)
    "user_settings": {{
      "research_level": "Comprehensive", // Simple choice. Options: Basic, Comprehensive, Expert
      "include_latest_info": true, // Simple toggle. Options: true, false
      "include_examples": true, // Simple toggle. Options: true, false  
      "fact_checking": "Standard", // Simple choice. Options: Basic, Standard, Strict
      "content_freshness": "Recent (6 months)", // User-friendly time description. Options: Very Recent (1 month), Recent (6 months), Moderate (1 year), Extended (2 years), All Time
      "include_statistics": true, // Simple toggle. Options: true, false
      "include_quotes": true, // Simple toggle. Options: true, false
      "competitor_analysis": true // Simple toggle. Options: true, false
    }}
  }}
```