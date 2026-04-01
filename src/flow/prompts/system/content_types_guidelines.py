DEFAULT_GUIDELINE = """
**GENERAL SEO CONTENT:**
- Focus on clear, informative, and engaging content.
- Structure: Introduction -> Logical Main Sections -> Conclusion.
- Provide actionable value to the reader.
"""

CONTENT_TYPE_GUIDELINES = {
    # INFORMATIONAL
    "how_to_guide": """
**HOW-TO GUIDE:**
- Focus: Step-by-step instructions, clear prerequisites, and actionable outcomes.
- Structure: Introduction -> Prerequisites/Tools Needed -> Step-by-Step Instructions -> Troubleshooting -> Conclusion.
- Tone: Instructive, clear, and encouraging.
- Key Elements: Numbered lists, actionable verbs, and clear checkpoints for the user.
""",
    "tutorial": """
**TUTORIAL:**
- Focus: Educational, theory-to-practice flow.
- Structure: Concept Overview -> Real World Examples -> Step-by-step Walkthrough -> Summary.
- Tone: Educational and authoritative.
- Key Elements: Code snippets (if technical), visual placeholders, learning checkpoints.
""",
    "explanatory_article": """
**EXPLANATORY ARTICLE:**
- Focus: Deep dive into "what is" and "why it matters".
- Structure: Direct Definition -> Core Concepts -> Importance & Benefits -> Examples -> Summary.
- Tone: Objective and thoroughly informative.
- Key Elements: Analogies, clear definitions, comprehensive coverage of subtopics.
""",
    "definition_article": """
**DEFINITION ARTICLE:**
- Focus: Simple, concise, exact answers to "What is X?"
- Structure: Direct Definition (Snippet-ready) -> History/Origin -> How it Works -> Common Misconceptions -> Related Terms.
- Tone: Encyclopedic but accessible.
- Key Elements: Featured snippet optimization in the first paragraph.
""",
    "faq_page": """
**FAQ PAGE:**
- Focus: Quick, scannable answers to common questions.
- Structure: Categorized Questions (H2) -> Specific Questions (H3) with Short Answers.
- Tone: Direct and helpful.
- Key Elements: PAA (People Also Ask) integration, concise paragraphs, links to deeper resources.
""",
    "troubleshooting_guide": """
**TROUBLESHOOTING GUIDE:**
- Focus: Problem-solution oriented.
- Structure: Common Symptoms/Issues -> Diagnostic Steps -> Specific Fixes (1..N) -> Preventative Measures.
- Tone: Reassuring and highly prescriptive.
- Key Elements: Bolded symptoms, numbered fix steps, warnings/cautions.
""",
    "checklist": """
**CHECKLIST:**
- Focus: Action-oriented, itemized steps for completing a process.
- Structure: Preparation/Pre-requisites -> Phase 1 Checklist -> Phase 2 Checklist -> Final Verification.
- Tone: Punchy, actionable.
- Key Elements: Bullet points, short sentences, logical sequential grouping.
""",
    "best_practices": """
**BEST PRACTICES:**
- Focus: Industry standards, expert recommendations, and common pitfalls.
- Structure: Core Principles -> Do's -> Don'ts -> Case Examples -> Summary.
- Tone: Authoritative, experienced, and opinionated.
- Key Elements: Rule-of-thumb callouts, expert quotes or industry standards.
""",
    "case_study": """
**CASE STUDY:**
- Focus: Real-world results and proven methodologies.
- Structure: The Client/Challenge -> The Strategy/Solution -> The Implementation -> The Results/ROI.
- Tone: Professional, data-driven, narrative.
- Key Elements: Specific metrics (%, $), timeline, before/after comparison.
""",

    # COMMERCIAL
    "product_comparison": """
**PRODUCT COMPARISON:**
- Focus: Objective analysis of multiple products for buyers evaluating options.
- Structure: Overview of Space -> Key Features Comparison Matrix -> Deep Dive on Product A -> Deep Dive on Product B -> Pros & Cons -> Final Verdict/Recommendation.
- Tone: Unbiased, analytical.
- Key Elements: Feature comparisons, pricing breakdown, target audience specific recommendations.
""",
    "vs_article": """
**VS ARTICLE (Head-to-Head):**
- Focus: Direct head-to-head comparison between two specific entities.
- Structure: Introduction -> Shared Features -> Key Differences -> Winner by Category 1..N -> Pricing Comparison -> Final Verdict.
- Tone: Objective, evaluative.
- Key Elements: "Who should use X vs Y", feature-by-feature battle.
""",
    "best_of_list": """
**BEST-OF LIST (Listicle):**
- Focus: Curated ranking of multiple solutions.
- Structure: Quick Summary/Top Picks -> Detailed Review 1..N (Overview, Best For, Pros/Cons, Pricing) -> Buying Guide -> Conclusion.
- Tone: Expert reviewer, helpful guide.
- Key Elements: "Best overall", "Best for budget", clear ranking criteria.
""",
    "product_review": """
**PRODUCT REVIEW:**
- Focus: In-depth analysis of a single product.
- Structure: Overview & Final Rating -> Key Features Deep Dive -> Performance/Usability -> Pricing -> Pros & Cons -> Is it right for you?.
- Tone: Honest, thorough, critical.
- Key Elements: Hands-on experience claims, limitations, ideal user persona.
""",
    "alternatives_article": """
**ALTERNATIVES ARTICLE:**
- Focus: Helping users move away from a specific tool they are dissatisfied with.
- Structure: Why look for alternatives to [Tool]? -> Criteria for a good alternative -> Top Alternative 1..N -> Comparison Summary -> Conclusion.
- Tone: Empathetic to pain points, solution-oriented.
- Key Elements: Direct comparison against the incumbent, migration ease.
""",
    "pros_cons_article": """
**PROS & CONS ARTICLE:**
- Focus: Balanced view of a concept, strategy, or single product.
- Structure: Overview -> Detailed Pros (Advantages) -> Detailed Cons (Disadvantages) -> Mitigating the Cons -> Who is this for? -> Final Verdict.
- Tone: Balanced, objective.
- Key Elements: Bulleted lists, contextual trade-offs.
""",
    "tool_roundup": """
**TOOL ROUNDUP:**
- Focus: Categorized collection of tools for a specific industry or task.
- Structure: Intro -> Tool Category 1 (Tools 1..N) -> Tool Category 2 (Tools N..M) -> How to Choose -> Conclusion.
- Tone: Informative, organized.
- Key Elements: Brief descriptions, strong categorization, link-heavy.
""",
    "buying_guide": """
**BUYING GUIDE:**
- Focus: Educational, teaching the user *how* to evaluate before buying.
- Structure: What is [Product Category]? -> Key Features to Evaluate -> Red Flags to Avoid -> Price Ranges Explained -> Top Recommendations.
- Tone: Educational, advisory.
- Key Elements: Feature definitions, budget tier breakdowns.
""",
    "pricing_comparison": """
**PRICING COMPARISON:**
- Focus: Focus exclusively on value for money and plan differences.
- Structure: Pricing Overview -> Tier 1 Breakdown -> Tier 2 Breakdown -> Hidden Costs/Add-ons -> ROI Analysis -> Which plan is best for you?.
- Tone: Financial, logical.
- Key Elements: Cost-benefit analysis, value propositions per tier.
""",

    # NAVIGATIONAL
    "homepage": """
**HOMEPAGE:**
- Focus: Brand introduction, navigation hub, and primary value proposition.
- Structure: Hero Section (Value + CTA) -> Key Services/Features -> Social Proof/Logos -> How it Works -> Footer Navigation.
- Tone: Welcoming, authoritative, clear.
- Key Elements: High-conversion CTAs, value-driven headings, scannable sections.
""",
    "brand_page": """
**BRAND PAGE:**
- Focus: The company story, mission, and identity.
- Structure: Our Story -> Mission & Vision -> Core Values -> The Team -> Community/Impact.
- Tone: Authentic, inspiring, human.
- Key Elements: Narrative arc, employee highlights, cultural values.
""",
    "product_page": """
**PRODUCT PAGE:**
- Focus: Selling a singular product's value and features.
- Structure: Hero (Big Benefit + CTA) -> Problem/Solution -> Feature Walkthrough -> Social Proof/Testimonials -> Pricing/CTA.
- Tone: Persuasive, benefit-driven.
- Key Elements: Use cases, objection handling, strong CTAs.
""",
    "feature_page": """
**FEATURE PAGE:**
- Focus: Deep dive on a specific capability of a larger product.
- Structure: Feature Overview -> How it works (Step-by-step) -> Key Benefits -> Associated Use Cases -> CTA.
- Tone: Descriptive, practical.
- Key Elements: Technical specifics, outcome-focused benefits.
""",
    "documentation_page": """
**DOCUMENTATION PAGE:**
- Focus: Technical or user manual reference.
- Structure: Brief Intro -> Prerequisites -> Core Concepts -> Step-by-Step Implementation -> Common Errors/Troubleshooting.
- Tone: Highly technical, objective, dry.
- Key Elements: Code blocks, API references, exact parameters.
""",
    "support_page": """
**SUPPORT PAGE:**
- Focus: Help hub and resource routing.
- Structure: Search Prompt -> Popular Topics/Articles -> Categorized Help Sections -> Contact Support CTA.
- Tone: Helpful, empathetic.
- Key Elements: Easy navigation, prominent search focus.
""",
    "contact_page": """
**CONTACT PAGE:**
- Focus: Facilitating communication.
- Structure: Header -> Contact Options (Sales, Support, Press) -> Form Fields -> Office Locations/Map -> Response Time Expectation.
- Tone: Approachable, professional.
- Key Elements: Categorized routing, clear expectations.
""",
    "about_page": """
**ABOUT PAGE:**
- Focus: Humanizing the brand.
- Structure: The "Why" -> Company History -> Leadership Profiles -> Careers/Hiring CTA.
- Tone: Story-driven, personal.
- Key Elements: Timeline, faces behind the company.
""",
    "login_page": """
**LOGIN PAGE:**
- Focus: Secure access portal.
- Structure: Welcome Back Header -> Login Form -> SSO/Social Auth -> Forgot Password -> Sign Up Link.
- Tone: Secure, minimal.
- Key Elements: Frictionless, clear error states (in copy).
""",
    "signup_page": """
**SIGNUP PAGE:**
- Focus: Onboarding and account creation without friction.
- Structure: Value Proposition Reminder (Why join?) -> Sign Up Form -> Trust Badges/Security -> Social Auth -> Login Link.
- Tone: Encouraging, secure.
- Key Elements: Mini-testimonials, focus on ease/speed.
""",

    # TRANSACTIONAL
    "sales_page": """
**SALES PAGE:**
- Focus: High-conversion, long-form persuasion.
- Structure: Compelling Hook -> The Core Problem/Pain -> The Solution (Your Offer) -> Key Benefits -> Massive Social Proof -> Urgency/Bonuses -> Final Call to Action.
- Tone: Persuasive, urgent, empathetic to pain.
- Key Elements: Risk reversal (guarantees), scarcity, stacked value.
""",
    "landing_page": """
**LANDING PAGE:**
- Focus: Campaign specific lead capture.
- Structure: Clear Offer/Headline -> 3 Key Benefits -> Minimal Social Proof -> Lead Capture Form/Primary CTA -> (No escaping links).
- Tone: Direct, offer-focused.
- Key Elements: Elimination of standard navigation, hyper-focused form.
""",
    "pricing_page": """
**PRICING PAGE:**
- Focus: Conversion-oriented plan selection.
- Structure: Header -> Tier Options -> Feature Matrix Comparison -> FAQs -> Money Back Guarantee -> Final CTA.
- Tone: Transparent, reassuring.
- Key Elements: "Most Popular" highlight, clear differentiation between tiers.
""",
    "checkout_page": """
**CHECKOUT PAGE:**
- Focus: Frictionless purchasing.
- Structure: Order Summary -> Secure Payment Fields -> Trust/Security Badges -> Support Contact Info.
- Tone: Secure, professional, locked-down.
- Key Elements: Reassurance of security, summary of what they get.
""",
    "order_page": """
**ORDER PAGE:**
- Focus: Order configuration before checkout.
- Structure: Product Selection -> Customization Options -> Add-ons/Upsells -> Total Calculation -> Proceed to Checkout.
- Tone: Helpful, suggestive (for upsells).
- Key Elements: Dynamic updates (in concept), clear option breakdown.
""",
    "subscription_page": """
**SUBSCRIPTION PAGE:**
- Focus: Recurring revenue setup.
- Structure: Benefits of Subscribing vs One-Off -> Frequency Options -> Cancel Anytime Assurance -> Subscribe CTA.
- Tone: Flexible, value-driven.
- Key Elements: Savings highlight (e.g., "Save 20%"), commitment reassurance.
""",
    "demo_booking_page": """
**DEMO BOOKING PAGE:**
- Focus: Lead generation via meetings.
- Structure: What you'll learn in the demo -> Preparation/Requirements -> Calendar/Booking Widget -> Logos/Trust Elements.
- Tone: Professional, accommodating.
- Key Elements: Agenda preview, low commitment feel.
""",
    "quote_request_page": """
**QUOTE REQUEST PAGE:**
- Focus: Enterprise/Custom sales inquiry.
- Structure: Header -> B2B Form Fields (Volume, Timeline) -> What Happens Next -> Enterprise Value Proposition.
- Tone: Professional, capable.
- Key Elements: Clear next steps (e.g., "We will contact you within 24h").
""",
    "download_page": """
**DOWNLOAD PAGE:**
- Focus: Asset delivery (lead magnet).
- Structure: Resource Summary -> Sneak Peek/Preview -> Email Capture Form -> Privacy Reassurance -> Download CTA.
- Tone: Generous, valuable.
- Key Elements: High value perception, clear opt-in terms.
""",
    "offer_page": """
**OFFER PAGE:**
- Focus: Limited time promotions.
- Structure: The Big Deal/Discount -> Expiry Countdown -> Eligibility/Terms -> Claim Offer CTA -> Regular vs Discount Comparison.
- Tone: Urgent, exciting.
- Key Elements: Strikethrough pricing, prominent deadlines.
"""
}
