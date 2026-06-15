"""
Cost & usage logger for Rext article generation pipeline.

Log every API call with token counts and estimated cost so we can compare
against actual billing. Call reset_article_session() at article start,
log_article_cost_summary() at article end.

Pricing constants — verify against current billing before trusting totals.
"""

import logging
from typing import Any

logger = logging.getLogger("rext.cost")

# ---------------------------------------------------------------------------
# Pricing (per unit). Update here when official pricing changes.
# ---------------------------------------------------------------------------
PRICING: dict[str, Any] = {
    "gpt-4o-mini": {
        "input_per_token": 0.15 / 1_000_000,     # $0.150 / 1M  ✓
        "output_per_token": 0.60 / 1_000_000,    # $0.600 / 1M  ✓
        # cached input is $0.075/1M
    },
    "gpt-5.2": {
        "input_per_token": 1.75 / 1_000_000,     # $1.75 / 1M  ✓
        "output_per_token": 14.00 / 1_000_000,   # $14.00 / 1M ✓
        # cached input is $0.175/1M
    },
    "gpt-image-2": {
        # Token-based, not flat-per-image.
        # text_input   $5.00 / 1M tokens
        # image_input  $8.00 / 1M tokens  ($2.00/1M cached — edit/reference only)
        # image_output $30.00 / 1M tokens
        "text_input_per_token":   5.00 / 1_000_000,
        "image_input_per_token":  8.00 / 1_000_000,
        "image_output_per_token": 30.00 / 1_000_000,
    },
    "dataforseo_serp": {
        "per_call": 0.002,   # Live organic SERP, page 1 / 10 results
        # +0.75x base per extra page; each optional param ×5
    },
    "dataforseo_keyword_overview": {
        "per_call": 0.0101,  # Labs: $0.01/task + $0.0001/keyword (single-kw call)
        # NOTE: Backlinks API is a separate product with separate pricing
    },
    "tavily": {
        "per_search": 0.008,  # 1 credit @ $0.008 (pay-as-you-go); advanced = 2 credits
    },
}

# Estimated image OUTPUT tokens by (size, quality).
# Derived from OpenAI pricing calculator: calculator_cost_usd / ($30/1M).
# These are outputs only; add text_input_per_token × prompt_tokens on top.
IMAGE_OUTPUT_TOKEN_ESTIMATES: dict[tuple[str, str], int] = {
    ("1024x1024",  "low"):    200,   # ~$0.006 output
    ("1024x1024",  "medium"): 1400,  # ~$0.042 output
    ("1024x1024",  "high"):   5567,  # ~$0.167 output
    ("1024x1792",  "low"):    387,   # ~$0.012 output
    ("1024x1792",  "medium"): 2700,  # ~$0.081 output
    ("1024x1792",  "high"):  10000,  # ~$0.300 output
    ("1792x1024",  "low"):    387,
    ("1792x1024",  "medium"): 2700,
    ("1792x1024",  "high"):  10000,
    ("1536x1024",  "low"):    310,
    ("1536x1024",  "medium"): 2100,
    ("1536x1024",  "high"):   8000,
    ("1024x1536",  "low"):    310,
    ("1024x1536",  "medium"): 2100,
    ("1024x1536",  "high"):   8000,
    ("auto",       "low"):    200,   # assume 1024x1024 when unknown
    ("auto",       "medium"): 1400,
    ("auto",       "high"):   5567,
}

# Module-level session accumulator. Not thread-safe across concurrent articles,
# but fine for local test runs (one article at a time).
_session: dict[str, Any] = {
    "llm_calls": [],
    "image_calls": [],   # list of {text_in, img_in, img_out, cost, actual}
    "dataforseo_serp": 0,
    "dataforseo_keyword": 0,
    "tavily": 0,
}


def reset_article_session() -> None:
    """Call at the start of each article generation run."""
    _session["llm_calls"].clear()
    _session["image_calls"].clear()
    _session["dataforseo_serp"] = 0
    _session["dataforseo_keyword"] = 0
    _session["tavily"] = 0
    logger.info("[COST] ── Article session reset ──────────────────────────────────────")


def _llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICING.get(model) or PRICING["gpt-4o-mini"]
    return (input_tokens * p["input_per_token"]) + (output_tokens * p["output_per_token"])


def log_llm_call(stage: str, model: str, input_tokens: int, output_tokens: int) -> None:
    cost = _llm_cost(model, input_tokens, output_tokens)
    _session["llm_calls"].append(
        {"stage": stage, "model": model, "input": input_tokens, "output": output_tokens, "cost": cost}
    )
    logger.info(
        "[COST|LLM] stage=%-28s model=%-12s  in=%6d  out=%6d  est=$%.5f",
        stage, model, input_tokens, output_tokens, cost,
    )


def dataforseo_serp_cost(pages: int = 1, extra_params: int = 0) -> float:
    """
    Compute DataForSEO Live Organic SERP cost.
    - pages=1 → $0.002 base (10 results, page 1)
    - Each additional page adds 0.75× base
    - Each optional parameter multiplies total by 5×
    """
    base = PRICING["dataforseo_serp"]["per_call"]
    page_cost = base + (pages - 1) * base * 0.75
    return page_cost * (5 ** extra_params)


def dataforseo_keyword_cost(keyword_count: int = 1) -> float:
    """
    Compute DataForSEO Keyword Overview (Labs) cost.
    $0.01/task + $0.0001/keyword item.
    """
    return 0.01 + 0.0001 * keyword_count


def log_dataforseo_serp(query: str, pages: int = 1, extra_params: int = 0) -> None:
    _session["dataforseo_serp"] += 1
    cost = dataforseo_serp_cost(pages, extra_params)
    logger.info(
        "[COST|DataForSEO] SERP call #%d  query=%r  pages=%d  extra_params=%d  est=$%.4f",
        _session["dataforseo_serp"], query[:80], pages, extra_params, cost,
    )


def log_dataforseo_keyword(keyword: str, keyword_count: int = 1) -> None:
    _session["dataforseo_keyword"] += 1
    cost = dataforseo_keyword_cost(keyword_count)
    logger.info(
        "[COST|DataForSEO] Keyword Overview call #%d  keyword=%r  count=%d  est=$%.4f",
        _session["dataforseo_keyword"], keyword[:80], keyword_count, cost,
    )


def log_tavily_search(query: str, call_num: int) -> None:
    _session["tavily"] += 1
    cost = PRICING["tavily"]["per_search"]
    logger.info(
        "[COST|Tavily] search #%d/6  query=%r  est=$%.4f",
        call_num, query[:80], cost,
    )


def _image_cost(text_input: int, image_output: int, image_input: int = 0) -> float:
    p = PRICING["gpt-image-2"]
    return (
        text_input  * p["text_input_per_token"]
        + image_input  * p["image_input_per_token"]
        + image_output * p["image_output_per_token"]
    )


def _prompt_tokens(prompt: str) -> int:
    """Rough token estimate: 4 chars per token (GPT average)."""
    return max(10, len(prompt) // 4)


def log_image_generation(prompt: str, model: str, size: str, quality: str = "low") -> None:
    """
    Log image generation at dispatch time using token estimates.
    If the API response later provides actual usage, call
    log_image_actual_tokens() to replace this estimate.
    """
    text_in = _prompt_tokens(prompt)
    img_out = IMAGE_OUTPUT_TOKEN_ESTIMATES.get((size, quality))
    if img_out is None:
        img_out = IMAGE_OUTPUT_TOKEN_ESTIMATES.get(("auto", quality), 200)
    cost = _image_cost(text_in, img_out)
    entry: dict[str, Any] = {
        "text_in": text_in, "img_in": 0, "img_out": img_out,
        "cost": cost, "actual": False,
    }
    _session["image_calls"].append(entry)
    logger.info(
        "[COST|Image] #%d  model=%s  size=%s  quality=%s  "
        "est_text_in=%d  est_img_out=%d  est=$%.5f  prompt=%r",
        len(_session["image_calls"]), model, size, quality,
        text_in, img_out, cost, prompt[:80],
    )


def log_image_actual_tokens(
    text_input: int,
    image_output: int,
    image_input: int = 0,
) -> None:
    """
    Replace the last image estimate with actual token counts from the API response.
    Call this after client.images.generate() returns, passing response.usage fields.
    """
    cost = _image_cost(text_input, image_output, image_input)
    if _session["image_calls"]:
        _session["image_calls"][-1] = {
            "text_in": text_input, "img_in": image_input,
            "img_out": image_output, "cost": cost, "actual": True,
        }
    logger.info(
        "[COST|Image] ACTUAL  text_in=%d  img_in=%d  img_out=%d  actual=$%.5f",
        text_input, image_input, image_output, cost,
    )


def log_article_cost_summary() -> None:
    """Log full cost breakdown. Call after article generation completes."""
    llm_cost = sum(c["cost"] for c in _session["llm_calls"])
    dfs_serp_cost = _session["dataforseo_serp"] * dataforseo_serp_cost()
    dfs_kw_cost = _session["dataforseo_keyword"] * dataforseo_keyword_cost()
    tavily_cost = _session["tavily"] * PRICING["tavily"]["per_search"]
    img_calls = _session["image_calls"]
    img_cost = sum(c["cost"] for c in img_calls)
    total = llm_cost + dfs_serp_cost + dfs_kw_cost + tavily_cost + img_cost

    bar = "=" * 74
    logger.info(bar)
    logger.info("[COST SUMMARY]  Article Generation — Estimated Cost Breakdown")
    logger.info(bar)

    total_in = total_out = 0
    for c in _session["llm_calls"]:
        total_in += c["input"]
        total_out += c["output"]
        logger.info(
            "  LLM  %-28s %-12s  in=%6d  out=%6d  $%.5f",
            c["stage"], c["model"], c["input"], c["output"], c["cost"],
        )
    if _session["llm_calls"]:
        logger.info(
            "  LLM  %-28s %-12s  in=%6d  out=%6d  $%.5f  ← LLM TOTAL",
            "ALL LLM STAGES", "", total_in, total_out, llm_cost,
        )

    logger.info(
        "  DataForSEO SERP          %2d call%s   est $%.4f",
        _session["dataforseo_serp"],
        "s" if _session["dataforseo_serp"] != 1 else " ",
        dfs_serp_cost,
    )
    logger.info(
        "  DataForSEO Keyword OV    %2d call%s   est $%.4f",
        _session["dataforseo_keyword"],
        "s" if _session["dataforseo_keyword"] != 1 else " ",
        dfs_kw_cost,
    )
    logger.info(
        "  Tavily Search            %2d search%s est $%.4f",
        _session["tavily"],
        "es" if _session["tavily"] != 1 else "  ",
        tavily_cost,
    )

    n_img = len(img_calls)
    n_actual = sum(1 for c in img_calls if c.get("actual"))
    actual_tag = f"  ({n_actual} actual, {n_img - n_actual} estimated)" if img_calls else ""
    logger.info(
        "  Image Generation         %2d image%s  $%.5f%s",
        n_img, "s" if n_img != 1 else " ", img_cost, actual_tag,
    )
    for i, c in enumerate(img_calls, 1):
        tag = "actual" if c.get("actual") else "est"
        logger.info(
            "    #%d  text_in=%d  img_in=%d  img_out=%d  $%.5f  [%s]",
            i, c["text_in"], c["img_in"], c["img_out"], c["cost"], tag,
        )

    logger.info(bar)
    logger.info("  TOTAL %s COST:   $%.4f",
                "ACTUAL+EST" if n_actual else "ESTIMATED", total)
    logger.info(bar)
    logger.info("  Pricing notes (verify against actual billing):")
    logger.info("    gpt-4o-mini   $0.150/1M in  | $0.600/1M out")
    logger.info("    gpt-5.2       $1.750/1M in  | $14.00/1M out  (cached: $0.175/1M)")
    logger.info("    gpt-image-2   text_in $5/1M | img_out $30/1M | img_in $8/1M")
    logger.info("    DataForSEO SERP  $0.002/page1 + 0.75x/extra page; 5x per optional param")
    logger.info("    DataForSEO KW OV $0.01/task + $0.0001/keyword")
    logger.info("    Tavily        $0.008/basic search  ($0.016/advanced)")
    logger.info(bar)
