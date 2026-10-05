"""
The public plan catalogue: every number the dashboard and the site show about plans.

Built from the plan rows, the credit manager's stage costs and the shared plan
rules, so no price, credit amount or limit is typed twice. The functions here
are pure; `SubscriptionPlanService.get_catalog` reads the rows and caches the
result.

The derived figures use the marketing site's formulas: articles are the whole
articles a month's credits pay for, a price per article is that month's price
over those articles, rounded to the cent, and the yearly saving is against
twelve monthly payments, in whole percent.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Iterable, Optional

from src.config.plan_rules import TRIAL_DURATION_DAYS, PlanOffer
from src.utils.credit_manager import LOW_CREDITS_THRESHOLD, STAGE_CREDITS

CREDITS_PER_ARTICLE = sum(STAGE_CREDITS.values())

# The stages each billed button in the workflow runs, and so what it charges.
# Where each is charged: serp_seo in fetch_dataforseo_backlinks.py, title_generation
# in keyword_recomendation.py (again on every changed keyword), generate_outline in
# generation/outline.py, the four content stages in content_generation.py and
# eeat_optimization in eeat_trust.py.
RUN_STAGES: Dict[str, tuple] = {
    "analyze": ("serp_seo",),
    "change_keyword": ("serp_seo", "title_generation"),
    "regenerate_outline": ("generate_outline",),
    "generate": (
        "deep_research",
        "content_drafting",
        "featured_image",
        "humanization",
        "eeat_optimization",
    ),
}

# Part of the catalogue's cache key: raise it whenever the catalogue's shape
# changes, so a deploy never serves the previous shape from the cache.
CATALOG_VERSION = 1


def _limit(value: Optional[int]) -> Optional[int]:
    """A plan cap, with null for unlimited (stored as -1)."""
    return None if value is None or value < 0 else int(value)


def _round_half_up(amount: Decimal, step: str) -> Decimal:
    return amount.quantize(Decimal(step), rounding=ROUND_HALF_UP)


def _cents(amount: Decimal) -> float:
    return float(_round_half_up(amount, "0.01"))


def _articles(credits: Optional[int]) -> Optional[int]:
    return None if credits is None else credits // CREDITS_PER_ARTICLE


def _caps(plan: Any) -> Dict[str, Optional[int]]:
    # The caps the backend enforces; max_topics is stored but checked nowhere, so it is not shown.
    return {
        "max_workspaces": _limit(plan.max_workspaces),
        "max_members_per_workspace": _limit(plan.max_members_per_workspace),
        "max_knowledge_items": _limit(plan.max_knowledge_items),
    }


def plan_entry(plan: Any) -> Dict[str, Any]:
    """One purchasable plan with its prices, credits, caps and derived figures."""
    monthly = Decimal(str(plan.price_monthly or 0))
    yearly = Decimal(str(plan.price_yearly or 0))
    month_billed_yearly = yearly / 12
    articles = _articles(plan.credits_per_month)

    saving = None
    if monthly > 0:
        saving = int(_round_half_up((1 - yearly / (monthly * 12)) * 100, "1"))

    return {
        "name": plan.name,
        "display_name": plan.display_name,
        "description": plan.description,
        "price_monthly": float(monthly),
        "price_yearly": float(yearly),
        "price_monthly_billed_yearly": _cents(month_billed_yearly),
        "yearly_saving_percent": saving,
        "credits_per_month": plan.credits_per_month,
        "articles_per_month": articles,
        "price_per_article_monthly": _cents(monthly / articles) if articles else None,
        "price_per_article_yearly": _cents(month_billed_yearly / articles) if articles else None,
        **_caps(plan),
    }


def trial_entry(plan: Any) -> Dict[str, Any]:
    """The trial every new account starts on: its length, its one grant of credits, its caps."""
    return {
        "plan_name": plan.name,
        "days": TRIAL_DURATION_DAYS,
        "credits": plan.credits_per_month,
        "articles": _articles(plan.credits_per_month),
        # The trial's credits are granted once at signup and never reset.
        "credits_renew": False,
        # Signup asks for no payment method.
        "card_required": False,
        **_caps(plan),
    }


def credit_rules() -> Dict[str, Any]:
    """What an article costs, stage by stage, and the rules around the balance."""
    return {
        "per_article": CREDITS_PER_ARTICLE,
        "stages": [{"key": key, "credits": credits} for key, credits in STAGE_CREDITS.items()],
        # A new keyword or country runs the SERP stage again, and the keyword gate
        # charges title generation on every answer, the changed one included
        # (keyword_recomendation.py), so a change costs both. A new outline runs
        # the outline stage again.
        "keyword_change": _run_cost("change_keyword"),
        "outline_regeneration": _run_cost("regenerate_outline"),
        # A run is refused before its first billed stage below a whole article's cost.
        "minimum_to_start": CREDITS_PER_ARTICLE,
        "low_balance_threshold": LOW_CREDITS_THRESHOLD,
        # Each month the balance is reset to the plan's amount.
        "carry_over": False,
    }


def _run_cost(run: str) -> int:
    return sum(STAGE_CREDITS[stage] for stage in RUN_STAGES[run])


def run_costs(balance: int) -> Dict[str, Dict[str, Any]]:
    """What each billed button costs against a balance, so the dashboard computes nothing.

    A new run (Analyze) starts only with a whole article's credits in hand
    (library_router.py); every later button needs its own cost. balance_after is
    null when the button cannot run.
    """
    runs: Dict[str, Dict[str, Any]] = {}
    for run, stages in RUN_STAGES.items():
        cost = _run_cost(run)
        minimum = CREDITS_PER_ARTICLE if run == "analyze" else cost
        can_run = balance >= minimum
        runs[run] = {
            "cost": cost,
            "minimum_balance": minimum,
            "can_run": can_run,
            "balance_after": balance - cost if can_run else None,
            "stages": [{"key": stage, "credits": STAGE_CREDITS[stage]} for stage in stages],
        }
    return runs


def offer_entry(offer: Optional[PlanOffer]) -> Optional[Dict[str, Any]]:
    if offer is None:
        return None
    return {
        "id": offer.id,
        "kind": offer.kind,
        "credit_multiplier": offer.credit_multiplier,
        "starts_at": offer.starts_at.isoformat(),
        "ends_at": offer.ends_at.isoformat(),
    }


def _is_trial(plan: Any) -> bool:
    return bool(plan.is_trial_plan) or (plan.name or "").lower() == "trial"


def build_plan_catalog(plans: Iterable[Any], currency: str) -> Dict[str, Any]:
    """
    The catalogue from the active plan rows, without the offer (which depends on the time).

    Purchasable plans are the public, non-trial ones, cheapest first. The trial
    is the one signup assigns: a plan flagged as the trial, else one named
    "trial".
    """
    plans = list(plans)
    purchasable = sorted(
        (plan for plan in plans if plan.is_public and not _is_trial(plan)),
        key=lambda plan: Decimal(str(plan.price_monthly or 0)),
    )
    trials = sorted(
        (plan for plan in plans if _is_trial(plan)), key=lambda plan: not plan.is_trial_plan
    )

    return {
        "currency": currency,
        "plans": [plan_entry(plan) for plan in purchasable],
        "trial": trial_entry(trials[0]) if trials else None,
        "credits": credit_rules(),
    }
