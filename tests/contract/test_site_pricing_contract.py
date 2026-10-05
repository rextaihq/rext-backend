"""
The marketing site's pricing numbers equal the backend's.

The site (rext-site-v3) types its plans, trial, credit costs and launch offer in
`src/content/home/pricing.ts` and `src/content/campaign.ts`. This test reads
those files and compares them with the catalogue GET /api/v1/plans builds from
the seeded plans (scripts/seeds/seed_subscription_plans.py), the credit
manager's stage costs and the shared plan rules. A difference fails the test:
change the side that is wrong.

The site's checkout is found through REXT_SITE_DIR, else beside this
repository's folder; without it the test is skipped.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.seeds.seed_subscription_plans import PLANS
from src.config.plan_rules import OFFERS
from src.services.plan_catalog import build_plan_catalog
from src.utils.credit_manager import STAGE_CREDITS

REPO_ROOT = Path(__file__).resolve().parents[2]


def _site_dir():
    candidates = [os.environ.get("REXT_SITE_DIR"), REPO_ROOT.parent / "rext-site-v3"]
    for candidate in candidates:
        if candidate and (Path(candidate) / "src/content/home/pricing.ts").is_file():
            return Path(candidate)
    return None


SITE = _site_dir()
pytestmark = pytest.mark.skipif(
    SITE is None, reason="no rext-site-v3 checkout (set REXT_SITE_DIR to its folder)"
)


def _closing(text, start):
    """Index of the bracket closing the one at `start`, skipping strings and comments."""
    pairs = {"[": "]", "{": "}"}
    stack = [pairs[text[start]]]
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch in "\"'`":
            i = text.index(ch, i + 1)
            while text[i - 1] == "\\":
                i = text.index(ch, i + 1)
        elif text.startswith("//", i):
            i = text.index("\n", i)
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch == stack[-1]:
            stack.pop()
            if not stack:
                return i
        i += 1
    raise AssertionError(f"unbalanced bracket at {start}")


def _block(text, key):
    """The text of `key: {…}` or `key: […]`, the first one found."""
    match = re.search(rf"\b{key}:\s*([\[{{])", text)
    assert match, f"no `{key}:` block in the site's fixture; update this test's parser"
    start = match.start(1)
    return text[start : _closing(text, start) + 1]


def _objects(array_text):
    """The top-level `{…}` objects of an array literal."""
    objects, i = [], 1
    while (start := array_text.find("{", i)) != -1:
        end = _closing(array_text, start)
        objects.append(array_text[start : end + 1])
        i = end + 1
    return objects


def _fields(obj_text):
    """The `key: number` and `key: "string"` fields at the start of each line."""
    fields = {}
    for key, number, string in re.findall(
        r'^\s*(\w+):\s*(?:(-?\d+(?:\.\d+)?)|"([^"]*)"),?\s*$', obj_text, re.MULTILINE
    ):
        fields[key] = float(number) if number else string
    return fields


def _cap(value):
    return None if value == "unlimited" else int(value)


@pytest.fixture(scope="module")
def pricing_ts():
    return (SITE / "src/content/home/pricing.ts").read_text()


@pytest.fixture(scope="module")
def catalog():
    return build_plan_catalog([SimpleNamespace(**plan) for plan in PLANS], currency="USD")


def test_site_lists_the_plans_for_sale(pricing_ts, catalog):
    site_ids = [_fields(obj)["id"] for obj in _objects(_block(pricing_ts, "plans"))]

    assert site_ids == [plan["name"] for plan in catalog["plans"]]


def test_site_plan_numbers_equal_the_seeds(pricing_ts, catalog):
    backend = {plan["name"]: plan for plan in catalog["plans"]}

    for obj in _objects(_block(pricing_ts, "plans")):
        site = _fields(obj)
        plan = backend[site["id"]]
        assert site["name"] == plan["display_name"], site["id"]
        assert site["monthly"] == plan["price_monthly"], site["id"]
        assert site["yearly"] == plan["price_yearly"], site["id"]
        assert site["credits"] == plan["credits_per_month"], site["id"]
        assert _cap(site["workspaces"]) == plan["max_workspaces"], site["id"]
        assert _cap(site["members"]) == plan["max_members_per_workspace"], site["id"]
        assert _cap(site["knowledgeItems"]) == plan["max_knowledge_items"], site["id"]


def test_site_trial_equals_the_trial_rules(pricing_ts, catalog):
    site = _fields(_block(pricing_ts, "trial"))
    trial = catalog["trial"]

    assert site["days"] == trial["days"]
    assert site["credits"] == trial["credits"]
    assert site["workspaces"] == trial["max_workspaces"]
    assert site["members"] == trial["max_members_per_workspace"]


def test_site_credit_costs_equal_the_credit_manager(pricing_ts):
    rows = re.findall(
        r'credits:\s*(\d+),\s*source:\s*"credit_manager\.py:\d+ (\w+)"',
        _block(_block(pricing_ts, "whatACreditBuys"), "rows"),
    )

    assert [(key, int(credits)) for credits, key in rows] == list(STAGE_CREDITS.items())


def test_site_campaign_is_an_offer_the_backend_knows():
    campaign_ts = (SITE / "src/content/campaign.ts").read_text()
    match = re.search(r"export const campaign\b[^=]*=\s*(\{|null)", campaign_ts)
    assert match, "no `export const campaign` in the site's campaign.ts; update this test's parser"
    if match.group(1) == "null":
        pytest.skip("the site runs no campaign")

    start = match.start(1)
    site = _fields(campaign_ts[start : _closing(campaign_ts, start) + 1])
    offers = {offer.id: offer for offer in OFFERS}

    assert site["id"] in offers, "the site announces an offer the backend does not define"
    offer = offers[site["id"]]
    assert datetime.fromisoformat(site["start"].replace("Z", "+00:00")) == offer.starts_at
    assert datetime.fromisoformat(site["end"].replace("Z", "+00:00")) == offer.ends_at
