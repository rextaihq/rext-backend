import pytest


def _make_state(topic: str, content_type: str):
    return {
        "content": {"selected_topic": topic, "content_type": content_type},
        "serp_normalized": {
            "related_topics": ["related a", "related b"],
            "questions": ["What is X?", "How does X work?"],
        },
        "seo_result": {"serp_backlinks": {"main_intent": "informational"}},
        "competitors": [
            {
                "domain": "example.com",
                "intent_distribution": {"informational": 0.8, "commercial": 0.2},
            }
        ],
    }


def _blog_payload():
    return {
        "content_type": "blog",
        "title": "wireless earbuds: how to choose the right pair",
        "slug_suggestion": "wireless-earbuds-how-to-choose",
        "brief": "Help readers choose earbuds that match their budget, fit, and usage.",
        "focus_keyphrase": "wireless earbuds",
        "keywords_to_include": ["battery life", "ANC", "fit", "codecs"],
        "target_audience": ["First-time buyers", "Commuters"],
        "tone": "Professional",
        "target_word_count": 1400,
        "image_suggestions": [
            {
                "description": "Earbuds feature comparison infographic",
                "alt_text_template": "wireless earbuds features comparison",
                "section": "h2-2",
            }
        ],
        "link_suggestions": [
            {
                "anchor_text": "Earbud buying checklist",
                "link_type": "internal",
                "context": "Supports decision section",
                "section": "h2-3",
            },
            {
                "anchor_text": "Bluetooth audio basics",
                "link_type": "outbound",
                "context": "Codec reference",
                "section": "h2-2",
            },
        ],
        "intro": {
            "hook": "Buying earbuds is harder than it should be.",
            "context": "Too many specs.",
            "promise": "Pick confidently.",
        },
        "sections": [
            {
                "heading": "What to prioritize when buying wireless earbuds",
                "purpose": "Set the decision framework.",
                "key_points": ["Fit first", "ANC for commuting", "Mic quality for calls"],
                "snippet_opportunity": True,
                "suggested_word_count": 260,
            },
            {
                "heading": "Battery life, charging cases, and real-world expectations",
                "purpose": "Explain battery claims vs reality.",
                "key_points": ["Rated vs real", "Fast charge", "Case cycles"],
                "suggested_word_count": 260,
            },
            {
                "heading": "Sound quality and codecs: what actually matters",
                "purpose": "Clarify codec tradeoffs without fluff.",
                "key_points": ["AAC vs SBC", "Android vs iPhone", "EQ apps"],
                "suggested_word_count": 260,
            },
            {
                "heading": "A quick shortlist process: match features to your use case",
                "purpose": "Make it actionable with a repeatable method.",
                "key_points": ["Budget tiering", "Use-case mapping", "Return policy check"],
                "snippet_opportunity": True,
                "suggested_word_count": 280,
            },
        ],
        "conclusion": {
            "recap_points": [
                "Pick fit + comfort first",
                "Validate battery needs",
                "Choose for your phone",
            ],
            "cta": "Use this checklist before you buy.",
        },
        "schema_type": "Article",
        "table_of_contents": False,
        "faqs": ["Do codecs matter for Spotify?", "How much ANC is enough?"],
    }


def _how_to_payload():
    return {
        "content_type": "how-to-guide",
        "title": "wireless earbuds: how to pair them with your phone",
        "slug_suggestion": "wireless-earbuds-pair-phone",
        "brief": (
            "Walk the reader through pairing, verifying, and troubleshooting connection issues."
        ),
        "focus_keyphrase": "wireless earbuds",
        "keywords_to_include": ["Bluetooth pairing", "pairing mode", "connection issues"],
        "target_audience": ["Non-technical users"],
        "tone": "Conversational",
        "target_word_count": 1200,
        "image_suggestions": [
            {
                "description": "Phone Bluetooth settings screenshot",
                "alt_text_template": "wireless earbuds bluetooth pairing",
                "section": "steps",
            }
        ],
        "link_suggestions": [
            {
                "anchor_text": "Bluetooth troubleshooting guide",
                "link_type": "internal",
                "context": "More fixes",
                "section": "troubleshooting",
            },
            {
                "anchor_text": "Android Bluetooth help",
                "link_type": "outbound",
                "context": "Official help",
                "section": "steps",
            },
        ],
        "prerequisites": ["Charged earbuds", "Bluetooth enabled phone"],
        "tools_or_materials": ["Your earbuds case"],
        "steps": [
            {
                "step_number": 1,
                "title": "Put your earbuds into pairing mode",
                "goal": "Make them discoverable",
                "instructions": ["Open the case", "Hold the button until it flashes"],
            },
            {
                "step_number": 2,
                "title": "Open Bluetooth settings on your phone",
                "goal": "Find available devices",
                "instructions": ["Go to Settings", "Tap Bluetooth"],
            },
            {
                "step_number": 3,
                "title": "Select your earbuds from the device list",
                "goal": "Initiate pairing",
                "instructions": ["Tap the device name", "Confirm pairing if prompted"],
            },
            {
                "step_number": 4,
                "title": "Verify audio is routed to the earbuds",
                "goal": "Confirm success",
                "instructions": ["Play a song", "Check volume and audio output"],
            },
            {
                "step_number": 5,
                "title": "Save the connection and test a call",
                "goal": "Ensure mic works",
                "instructions": ["Place a call", "Confirm mic + speaker are correct"],
            },
        ],
        "common_mistakes": [
            "Trying to pair while earbuds are already connected to another device"
        ],
        "troubleshooting": [
            {
                "problem": "Earbuds don’t appear in the list",
                "fix": ["Reset earbuds", "Toggle Bluetooth off/on"],
            }
        ],
        "wrap_up": ["Your earbuds should now auto-connect", "If issues persist, reset and re-pair"],
        "schema_type": "HowTo",
        "faqs": ["Why do my earbuds keep disconnecting?"],
    }


def _comparison_payload():
    return {
        "content_type": "comparison",
        "title": "wireless earbuds: AirPods vs Galaxy Buds — which should you buy?",
        "slug_suggestion": "wireless-earbuds-airpods-vs-galaxy-buds",
        "brief": "Compare two popular options and recommend the best choice by scenario.",
        "focus_keyphrase": "wireless earbuds",
        "keywords_to_include": ["AirPods", "Galaxy Buds", "ANC", "microphone"],
        "target_audience": ["People choosing between two models"],
        "tone": "Professional",
        "target_word_count": 1700,
        "image_suggestions": [
            {
                "description": "Side-by-side spec table",
                "alt_text_template": "wireless earbuds comparison table",
                "section": "comparison_table",
            }
        ],
        "link_suggestions": [
            {
                "anchor_text": "How to choose earbuds",
                "link_type": "internal",
                "context": "Methodology",
                "section": "decision_guide",
            },
            {
                "anchor_text": "Official product specs",
                "link_type": "outbound",
                "context": "Verification",
                "section": "verdict",
            },
        ],
        "compared_entities": [
            {
                "name": "AirPods",
                "best_for": "iPhone users who want seamless switching",
                "key_strengths": ["Great iOS integration", "Strong mics"],
                "key_limitations": ["Less control on Android"],
            },
            {
                "name": "Galaxy Buds",
                "best_for": "Android users who want customization",
                "key_strengths": ["Good app EQ", "Solid ANC"],
                "key_limitations": ["Features vary by phone"],
            },
        ],
        "evaluation_criteria": [
            {
                "criterion": "Phone ecosystem",
                "why_it_matters": "Integration affects daily convenience.",
                "how_to_judge": "Check device switching, controls, and app support.",
            },
            {
                "criterion": "Microphone quality",
                "why_it_matters": "Calls are a primary use case.",
                "how_to_judge": "Look for noise handling and voice clarity.",
            },
            {
                "criterion": "ANC + transparency",
                "why_it_matters": "Commute and office use.",
                "how_to_judge": "Assess real-world reduction and natural passthrough.",
            },
        ],
        "comparison_table": [
            {
                "criterion": "Best ecosystem fit",
                "entity_notes": [
                    {"entity_name": "AirPods", "note": "Best on iOS"},
                    {"entity_name": "Galaxy Buds", "note": "Best on Android"},
                ],
            }
        ],
        "decision_guide": [
            "Choose based on your phone first",
            "Then prioritize mic vs ANC",
            "Check comfort + return policy",
        ],
        "recommendations": [
            {
                "scenario": "Best for iPhone users",
                "pick": "AirPods",
                "reasoning": ["Seamless pairing", "Better switching"],
            },
            {
                "scenario": "Best for Android customization",
                "pick": "Galaxy Buds",
                "reasoning": ["More controls", "App features"],
            },
        ],
        "verdict": "AirPods for iPhone-first convenience; Galaxy Buds for Android flexibility.",
        "schema_type": "Article",
        "faqs": ["Do they work with both iOS and Android?"],
    }


def _review_payload():
    return {
        "content_type": "in-depth-review",
        "title": "wireless earbuds: AirPods review (features, pros/cons, verdict)",
        "slug_suggestion": "wireless-earbuds-airpods-review",
        "brief": "Review AirPods with practical guidance on who should buy them.",
        "focus_keyphrase": "wireless earbuds",
        "keywords_to_include": ["AirPods", "battery life", "microphone"],
        "target_audience": ["People researching AirPods"],
        "tone": "Authoritative",
        "target_word_count": 1500,
        "image_suggestions": [
            {
                "description": "AirPods in-ear photo",
                "alt_text_template": "wireless earbuds AirPods fit",
                "section": "standout_features",
            }
        ],
        "link_suggestions": [
            {
                "anchor_text": "Earbuds comparison guide",
                "link_type": "internal",
                "context": "Other options",
                "section": "alternatives",
            },
            {
                "anchor_text": "Official AirPods specs",
                "link_type": "outbound",
                "context": "Verification",
                "section": "rating",
            },
        ],
        "product_or_service": "AirPods",
        "who_its_for": ["iPhone users", "People who take many calls"],
        "who_its_not_for": ["Android-only users who want deep controls"],
        "rating": 4.4,
        "standout_features": [
            {
                "name": "Fast pairing",
                "why_it_matters": "Saves time daily",
                "what_to_check": ["Initial setup", "Device switching"],
            },
            {
                "name": "Call clarity",
                "why_it_matters": "Better calls in noise",
                "what_to_check": ["Wind handling", "Voice pickup"],
            },
            {
                "name": "Comfort",
                "why_it_matters": "Long wear",
                "what_to_check": ["Seal", "Pressure points"],
            },
        ],
        "pros": ["Great iOS integration", "Strong microphone performance", "Easy daily use"],
        "cons": ["Fewer controls on Android", "Price premium"],
        "alternatives": ["Galaxy Buds", "Sony WF series"],
        "verdict": "A top pick for iPhone users who value convenience and call quality.",
        "schema_type": "Review",
        "faqs": ["Is ANC worth it on this model?"],
    }


class _DummyLLM:
    def __init__(self, payload_factory):
        self.payload_factory = payload_factory
        self.schema = None
        self.seen_messages = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    async def ainvoke(self, messages):
        self.seen_messages = messages
        payload = self.payload_factory(self.schema)
        return self.schema.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_content_type", "expected_content_type"),
    [
        ("article", "blog"),
        ("how to guide", "how-to-guide"),
        ("comparison", "comparison"),
        ("review", "in-depth-review"),
        ("unknown-type", "blog"),
    ],
)
async def test_generate_outline_executes_and_returns_schema(
    monkeypatch, raw_content_type, expected_content_type
):
    from src.flow.engines.content.generation import outline as outline_node

    def payload_factory(schema):
        slug = getattr(schema, "__content_type_slug__", "blog")
        if slug in {"how-to-guide", "tutorial", "documentation", "login-guide"}:
            payload = _how_to_payload()
            payload["content_type"] = slug
            return payload
        if slug in {
            "comparison",
            "best-tools",
            "alternatives",
            "pros-cons",
            "product-roundup",
            "buying-guide",
        }:
            payload = _comparison_payload()
            payload["content_type"] = slug
            return payload
        if slug == "in-depth-review":
            payload = _review_payload()
            payload["content_type"] = slug
            return payload

        payload = _blog_payload()
        payload["content_type"] = slug
        return payload

    dummy = _DummyLLM(payload_factory)
    monkeypatch.setattr(outline_node, "load_model", lambda **kwargs: dummy)

    state = _make_state(topic="Wireless earbuds", content_type=raw_content_type)
    result = await outline_node.generate_outline(state)

    content = result["content"]
    assert content["status"] == "planning"
    assert content["outline"]["status"] == "reviewing"
    assert content["outline"]["content_type"] == expected_content_type

    # Prompt contains schema name and content type (so LLM is guided correctly)
    assert dummy.seen_messages, "LLM should have been invoked with messages"
    human = [m for m in dummy.seen_messages if getattr(m, "type", "") == "human"][0]
    assert "Schema:" in human.content
    assert expected_content_type in human.content


@pytest.mark.asyncio
async def test_generate_outline_empty_topic_returns_error():
    from src.flow.engines.content.generation import outline as outline_node

    result = await outline_node.generate_outline(_make_state(topic="", content_type="blog"))
    assert result["content"]["error"] == "No topic found in state"


@pytest.mark.asyncio
async def test_generate_outline_auto_rejects_on_quality_failure(monkeypatch):
    from src.flow.engines.content.generation import outline as outline_node
    from src.flow.engines.content.review.outline import review_outline

    def payload_factory(schema):
        payload = _blog_payload()
        payload["sections"][0]["heading"] = "Introduction"  # banned by quality gate
        return payload

    dummy = _DummyLLM(payload_factory)
    monkeypatch.setattr(outline_node, "load_model", lambda **kwargs: dummy)

    state = _make_state(topic="Wireless earbuds", content_type="blog")
    result = await outline_node.generate_outline(state)

    outline = result["content"]["outline"]
    assert outline["status"] == "rejected"
    assert outline["auto_rejected"] is True
    assert outline["iteration_count"] == 1

    # Review node should not interrupt for auto-rejected outlines
    reviewed = review_outline({"content": result["content"]})
    assert reviewed["content"]["outline"]["auto_rejected"] is True


@pytest.mark.asyncio
async def test_generate_outline_postprocess_fixes_title_focus_keyphrase(monkeypatch):
    from src.flow.engines.content.generation import outline as outline_node

    def payload_factory(schema):
        slug = getattr(schema, "__content_type_slug__", "blog")
        payload = _comparison_payload()
        payload["content_type"] = slug
        payload["focus_keyphrase"] = "best seo tools"
        payload["title"] = "Beginner's guide to SEO tools for 2026"  # missing "best"
        return payload

    dummy = _DummyLLM(payload_factory)
    monkeypatch.setattr(outline_node, "load_model", lambda **kwargs: dummy)

    state = _make_state(
        topic="The Ultimate Beginner's Guide to SEO Tools: Choosing the Right Ones for 2026",
        content_type="buying-guide",
    )
    result = await outline_node.generate_outline(state)

    outline = result["content"]["outline"]
    assert outline["status"] == "reviewing"
    assert "best seo tools" in outline["title"].lower()
