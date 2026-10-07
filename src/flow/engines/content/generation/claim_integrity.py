"""Factual-claim integrity for generated content — one policy for all 34 content types.

Why this exists
---------------
Every other citation guard in the pipeline (check_facts_and_external_links_integration)
verifies the claims the writer chose to DECLARE in the `facts` field. A price, a
statistic, an invented "when I migrated a client..." story, a competitor weakness or
an absolute "X is the best CMS" verdict that the writer simply never lists in
`facts` passed every gate untouched — and the writer, outline and humanize prompts
all actively asked for concrete numbers, anecdotes and experience. This module reads
the PROSE instead, finds the claim shapes that are most often wrong or invented, and
checks each one against the only ground truth the pipeline actually holds:

* `source_documents`  — the real search_tool results captured during generation
                        (plus outline key facts whose source URL is one of them),
* `brand_documents`   — the user-approved brand About / selling-position text,
* `author_documents`  — the selected author persona's own profile,
* `entity_names`      — the non-brand products the approved outline names.

Nothing here is content-type specific. The claim shapes are universal (a price is a
price in a comparison, a pricing page or a tutorial), so the same rules apply to all
34 types; the per-type differences that DO matter — how prominently the brand is
promoted, how citations are placed — stay in brand_placement_policy.py and
evidence_placement_policy.py, untouched.

Deliberate limits
-----------------
Deterministic string matching, not semantic fact-checking. It catches the claim
shapes that cause real damage (prices, figures, versions/dates, fabricated
experience, unqualified superlatives, competitor weaknesses, unapproved brand
capabilities) and verifies them by exact number / term presence in evidence that is
about the same entity. It cannot tell that a qualitative sentence is subtly wrong,
and it will not see a claim phrased in a shape it does not model. Headings are not
scanned: they are owned by the subheading SEO pass, and "Best X for Y" headings are
normal SEO copy rather than a verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional, TypedDict


class ClaimEvidence(TypedDict, total=False):
    brand_name: str
    brand_documents: list[str]
    source_documents: list[dict]  # {"url": str, "text": str}
    author_documents: list[str]
    entity_names: list[str]


@dataclass(frozen=True)
class Claim:
    category: str
    sentence: str
    span: str


# What the repair model is told to do with each unsupported claim. Every entry
# removes or softens — none asks for a replacement value, because the value is
# exactly what we cannot verify.
CLAIM_REPAIR_GUIDANCE: dict[str, str] = {
    "pricing": (
        "remove the price figure; if pricing matters here, describe the pricing model without "
        "a number (e.g. 'offers a free tier and paid plans') — never substitute another figure"
    ),
    "statistic": (
        "remove the figure or make the point qualitatively; never substitute a different number"
    ),
    "version_or_date": (
        "drop the specific version/date or phrase it generically (e.g. 'a current LTS release')"
    ),
    "fabricated_experience": (
        "remove the invented first-person testing, client result or experience figure; keep the "
        "underlying advice as a general recommendation or clearly hypothetical example"
    ),
    "absolute_superlative": (
        "replace the absolute verdict with a qualified, fit-based recommendation (e.g. 'a strong "
        "fit for teams that need X') — keep the product positioned, just not as an unsupported absolute"
    ),
    "competitor_claim": (
        "remove the unverified competitor weakness, or restate it as a neutral trade-off only if "
        "the verified sources support it"
    ),
    "brand_capability": (
        "remove the capability/integration/technology the approved brand info does not state; "
        "describe the brand only with what that info says"
    ),
}

# ── text units ──────────────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_TABLE_ROW_RE = re.compile(r"^\s*\|")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]*-{3,}[\s:|-]*$")
# A sentence ends at . ! or ?, also when one or two closing quotes or brackets follow it
# ("not 'lab-tested.' Our picks…", "(It said “lab-tested.”) Our picks…"): without that,
# the next sentence's "Our" made the one before it read as a first-person testing claim.
_CLOSERS = "[\"'\u201d\u2019)\\]]"
_SENTENCE_SPLIT_RE = re.compile(
    rf"(?:(?<=[.!?])|(?<=[.!?]{_CLOSERS})|(?<=[.!?]{_CLOSERS}{_CLOSERS}))"
    r"\s+(?=[\"'(\[*_\u201c\u2018]?[A-Z0-9])"
)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
# A piece that is only a citation ("… CMS.” [Report](url)") is the sentence before it's source.
_CITATION_ONLY_RE = re.compile(r"(?:\[[^\]]*\]\(https?://[^)\s]+\)[\s,;.]*)+")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9.'+-]*")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

_STOPWORDS = frozenset(
    "the a an and or but of to in on for with is are was were this that it as by at be from "
    "your you we our will can has have not its their they them than then also more most very "
    "just only into over per each any all about how what when which who why if so do does".split()
)


@dataclass(frozen=True)
class _Unit:
    text: str  # link targets removed — what a reader sees
    cited_urls: tuple[str, ...]


def _units(text: str) -> list[_Unit]:
    """Sentences (and table rows) of prose, headings excluded."""
    cleaned = _HTML_COMMENT_RE.sub(" ", _IMAGE_RE.sub(" ", text or ""))
    units: list[_Unit] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped or _HEADING_RE.match(line) or _TABLE_SEPARATOR_RE.match(stripped):
            continue
        parts = [stripped] if _TABLE_ROW_RE.match(stripped) else _SENTENCE_SPLIT_RE.split(stripped)
        line_units: list[_Unit] = []
        for part in parts:
            urls = tuple(m.group(2) for m in _LINK_RE.finditer(part))
            if line_units and _CITATION_ONLY_RE.fullmatch(part.strip()):
                # Split off by the sentence boundary: the claim must keep its own source, or it
                # is weighed against every source and a number from another one can pass it.
                claim = line_units[-1]
                line_units[-1] = _Unit(claim.text, claim.cited_urls + urls)
                continue
            visible = _LINK_RE.sub(lambda m: m.group(1), part).strip()
            if visible:
                line_units.append(_Unit(visible, urls))
        units.extend(line_units)
    return units


def _tokens(text: str) -> set[str]:
    return {
        w.strip(".'+-")
        for w in _WORD_RE.findall((text or "").lower())
        if len(w.strip(".'+-")) > 2 and w.strip(".'+-") not in _STOPWORDS
    }


_NUMBER_WORDS = {
    word: str(value)
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}
_NUMBER_WORD_RE = re.compile(r"\b(?:" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def _numbers(text: str) -> set[str]:
    """Normalized numeric tokens: '1,200' -> '1200', '29.00' -> '29', 'eight' -> '8'."""
    found: set[str] = {_NUMBER_WORDS[w.lower()] for w in _NUMBER_WORD_RE.findall(text or "")}
    for raw in _NUMBER_RE.findall(text or ""):
        value = raw.replace(",", "")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        found.add(value)
    return found


def _contains_name(text: str, name: str) -> bool:
    return (
        bool(name)
        and re.search(
            rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text or "", re.IGNORECASE
        )
        is not None
    )


# ── claim shapes ────────────────────────────────────────────────────────────

_PRICE_RE = re.compile(
    r"(?:[$€£¥₹]\s?\d[\d,]*(?:\.\d+)?(?:\s?[kKmM]\b)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP|INR|AUD|CAD|dollars|euros|pounds)\b)"
)
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:%|percent\b)", re.IGNORECASE)
_MULTIPLIER_RE = re.compile(
    r"\b\d+(?:\.\d+)?x\s+(?:faster|slower|more|less|fewer|higher|lower|better|cheaper|quicker|"
    r"the|increase|improvement|growth|boost|return|roi)\b",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(
    r"\b(\d[\d,]*(?:\.\d+)?)\s?(\+|k\+?|m\+?|\s(?:million|billion|thousand))?\s+"
    r"(?:(?:active|paying|monthly|happy|global|enterprise|registered)\s+)?"
    r"(?:users|customers|clients|companies|businesses|brands|organizations|organisations|teams|"
    r"developers|installs|installations|downloads|websites|sites|stores|integrations|plugins|"
    r"extensions|templates|themes|apps|countries|languages|stars|reviews|employees|projects|"
    r"agencies|enterprises|members|contributors)\b",
    re.IGNORECASE,
)
_VERSION_RE = re.compile(r"\b(?:version|v)\s?\d+(?:\.\d+){1,2}\b|\bversion\s\d+\b", re.IGNORECASE)
_DATED_EVENT_RE = re.compile(
    r"\b(?:released|launched|introduced|deprecated|announced|acquired|founded|discontinued|"
    r"sunset|retired|rebranded)\b[^.!?]{0,40}?\b(?:19|20)\d{2}\b"
    r"|\b(?:since|as of|in)\s+(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?"
    r"(?:19|20)\d{2}\b[^.!?]{0,30}?\b(?:released|launched|introduced|deprecated|added|removed|"
    r"changed|raised|lowered|increased|cut)\b",
    re.IGNORECASE,
)

_FIRST_PERSON_RE = re.compile(
    r"(?:\bI\b|\bI['’](?:ve|m|d)\b|\b(?:[Mm]y|[Ww]e|[Ww]e['’](?:ve|re)|[Oo]ur)\b)"
)
_TESTING_RE = re.compile(
    r"\b(?:tested|benchmarked|trialed|trialled|stress-tested|put\s+(?:\w+\s+){1,3}through"
    r"|hands-on\s+(?:testing|tests|review|evaluation)"
    r"|in\s+(?:my|our)\s+(?:own\s+)?(?:tests?|testing|benchmarks?|trials?))\b",
    re.IGNORECASE,
)
# A testing word that the negation right before it denies ("not lab-tested", "we haven't
# tested", "we have not personally benchmarked") discloses that no test was run: it isn't
# a testing claim. Only words that belong inside such a denial may stand between the two,
# with no comma, semicolon or full stop, so "we never guessed; we tested" and "without
# hesitation, we tested" are still claims. "Without" is no denial here: "we never rank
# products without hands-on testing" asserts the test. Nor is a word that grades the
# testing: "we haven't fully tested every integration" says some testing was done.
_DENIAL_FILLERS = "been|be|being|yet|ever|personally|independently|actually|really|directly|lab"
_NEGATION_BEFORE_RE = re.compile(
    r"(?:\b(?:not|never)\b|n['\u2019]t\b)"
    rf"(?:[\s'\"\u2018\u201c-]+(?:{_DENIAL_FILLERS})\b)*[\s'\"\u2018\u201c-]*$",
    re.IGNORECASE,
)
_CLIENT_OUTCOME_RE = re.compile(
    r"\b(?:my|our|a|one)\s+(?:(?:former|recent|past|previous|long-time|ecommerce|e-commerce|saas|b2b|"
    r"agency|enterprise)\s+)?(?:clients?|customers?)\b[^.!?]{0,120}?\b(?:saw|increased|reduced|cut|"
    r"grew|dropped|doubled|tripled|boosted|improved|went from|jumped|fell|saved|halved)\b",
    re.IGNORECASE,
)
_YEARS_EXPERIENCE_RE = re.compile(
    r"\b(?:\d+\+?|over a|more than a|nearly a|almost a|a|two|three|four|five|six|seven|eight|nine|"
    r"ten|fifteen|twenty)\s+(?:years?|decades?)\b[^.!?]{0,40}?\b(?:experience|working|building|running|"
    r"doing|in (?:the )?(?:field|industry|business|trenches)|as an?|career)\b"
    r"|\b(?:spent|after|over)\s+(?:\d+\+?|a decade|two decades)\s+(?:years?\s+)?"
    r"(?:working|building|running|doing|in)\b",
    re.IGNORECASE,
)
_QUANTIFIED_WORK_RE = re.compile(
    r"\b(?:migrated|built|launched|shipped|managed|audited|reviewed|worked with|helped|onboarded|"
    r"consulted for|deployed|handled|set up|trained|scaled|analyzed|analysed)\b[^.!?]{0,60}?"
    r"\b\d[\d,]*\+?\b",
    re.IGNORECASE,
)

_SUPERLATIVE_RES = (
    re.compile(
        r"\b(?:is|are|remains|stands out as|emerges as|comes out as)\s+"
        r"(?:(?:clearly|easily|simply|by far|undoubtedly|hands down|arguably)\s+)?"
        r"(?:the\s+)?(?:best|#1|no\.\s?1|number one|top(?!\s+of\b)|fastest|most popular|"
        r"most powerful|most secure|most flexible|most scalable|most affordable|cheapest|easiest)"
        r"(?![-\w])(?!\s+(?:way|method|route|path|place|time)\b)"
        r"(?![^.!?|]{0,50}\b(?:for|if|when|among|in this|on this|option for|choice for|fit for)\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:leads|dominates|tops|rules)\s+(?:the\s+)?(?:market|industry|pack|category|field|"
        r"competition|space)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:clear|overall|undisputed|outright|obvious|ultimate)\s+winner\b", re.IGNORECASE
    ),
    re.compile(r"\bthe\s+winner\b(?![^.!?|]{0,40}\b(?:for|if|when|depends)\b)", re.IGNORECASE),
    re.compile(r"\b(?:market|industry|category)[- ]leader\b", re.IGNORECASE),
    re.compile(
        r"\b(?:industry[- ]leading|best[- ]in[- ]class|unmatched|unbeatable|unrivall?ed|"
        r"second to none|nothing (?:else )?comes close)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bthe only (?:cms|tool|platform|solution|product|option|service|software|framework|"
        r"app|vendor|agency)\b",
        re.IGNORECASE,
    ),
)

_NEGATIVE_CAPABILITY_RE = re.compile(
    r"\b(?:doesn['’]t|does not|don['’]t|do not|can['’]t|cannot|can not|won['’]t|lacks?|lacking|"
    r"has no|have no|offers no|provides no|no (?:built-in|native|real|official)|"
    r"without (?:any )?(?:built-in|native)|falls short|struggles? (?:with|to)|only supports|"
    r"locks? you in|forces? you|expensive|overpriced|slow|slower|outdated|clunky|bloated|buggy|"
    r"insecure|unreliable)\b",
    re.IGNORECASE,
)

_PERSON_SUBJECT_RE = re.compile(
    r"\b(?:you|you['’]ll|i|we|they|teams?|users?|developers?|editors?|people)\s+$", re.IGNORECASE
)

_CLAUSE_BOUNDARY_RE = re.compile(r"[,;:]|\s—\s|\s(?:so|but|which|while|because|and so)\s")

_CAPABILITY_RE = re.compile(
    r"\b(?:integrates? (?:natively )?with|native integrations? (?:with|for)|integrations? with|"
    r"supports?|compatible with|built on|built with|powered by|connects? (?:to|with)|plugs? into|"
    r"syncs? with|works with|certified|compliant with|runs on)\b",
    re.IGNORECASE,
)
# A "named term" in a capability object: something with a capital letter or a
# dotted tech name (Next.js, GraphQL, SOC 2, Shopify) — generic lowercase words
# ("teams", "content") are descriptions, not verifiable specifics.
_NAMED_TERM_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+\b|\b[A-Z][A-Za-z0-9]*[A-Za-z0-9]\b"
)
_GENERIC_CAPITALIZED = frozenset(
    "I A An The It Its This That These Those And Or But For With Our Your You We They Their "
    "API APIs CMS UI UX URL URLs SEO Web".split()
)


# ── evidence ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Doc:
    kind: str  # "source" | "brand" | "author"
    text: str
    url: str
    tokens: frozenset[str]
    numbers: frozenset[str]


def _doc(kind: str, text: str, url: str = "") -> Optional[_Doc]:
    text = (text or "").strip()
    if not text:
        return None
    return _Doc(kind, text, url, frozenset(_tokens(text)), frozenset(_numbers(text)))


_ENTITY_NAME_KEYS = frozenset(
    {"name", "product_name", "tool_name", "competitor_name", "option_name", "brand_name"}
)
_ENTITY_LIST_KEYS = frozenset({"tools", "products", "competitors"})


def outline_entity_names(outline: Any, brand_name: str = "") -> list[str]:
    """Product/tool/competitor names the approved outline names, for any schema.

    Generic by design: every commercial outline (comparison `products[].name`,
    best-tools `ranked_tools[].name`, alternatives `competitor_name`, roundup
    `products`, ...) spells its entities under one of a handful of keys, so a
    recursive walk covers all of them without a per-type table.
    """
    found: dict[str, str] = {}

    def _add(value: Any) -> None:
        if not isinstance(value, str):
            return
        name = value.strip()
        if not name or len(name) > 40 or len(name.split()) > 4 or not re.search(r"[A-Z]", name):
            return
        if brand_name and name.lower() == brand_name.strip().lower():
            return
        found.setdefault(name.lower(), name)

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "brand_voice_promotion":
                    continue
                if key in _ENTITY_NAME_KEYS:
                    _add(value)
                elif key in _ENTITY_LIST_KEYS and isinstance(value, list):
                    for item in value:
                        _add(item) if isinstance(item, str) else _walk(item)
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(outline or {})
    return list(found.values())


def build_claim_evidence(
    *,
    outline: Optional[dict],
    brand_context: Optional[dict],
    generation_meta: Optional[dict],
) -> ClaimEvidence:
    """Everything a factual claim in the article may legitimately rest on."""
    meta = generation_meta or {}
    searched = [r for r in (meta.get("searched_results") or []) if isinstance(r, dict)]
    searched_urls = {(r.get("url") or "").strip() for r in searched if r.get("url")}

    # An official-source record names the product it belongs to (entity_research):
    # a vendor's own plan table rarely repeats the product name, yet it is
    # evidence about exactly that product.
    sources: list[dict] = [
        {
            "url": (r.get("url") or "").strip(),
            "text": f"{r.get('entity') or ''}\n{r.get('title') or ''}\n{r.get('snippet') or ''}",
        }
        for r in searched
    ]
    # Outline key facts count only when they cite a source this run actually
    # retrieved — the outline stage has no search tool, so an unsourced "fact"
    # there is exactly the kind of guessed value this module exists to stop.
    for fact in (outline or {}).get("key_facts") or []:
        if isinstance(fact, dict):
            url = (fact.get("source_url") or "").strip()
            if url and url in searched_urls and fact.get("text"):
                sources.append({"url": url, "text": str(fact["text"])})

    brand = brand_context or {}
    author_profile = meta.get("author_profile") or ""
    return ClaimEvidence(
        brand_name=(brand.get("brand_name") or "").strip(),
        brand_documents=[
            t for t in (brand.get("about") or "", brand.get("selling_position") or "") if t.strip()
        ],
        source_documents=sources,
        author_documents=[author_profile] if author_profile.strip() else [],
        entity_names=outline_entity_names(outline, brand.get("brand_name") or ""),
    )


class _EvidenceIndex:
    def __init__(self, evidence: ClaimEvidence):
        self.brand_name = (evidence.get("brand_name") or "").strip()
        self.entities = [n for n in evidence.get("entity_names") or [] if n]
        self.sources = [
            d
            for d in (
                _doc("source", s.get("text", ""), s.get("url", ""))
                for s in evidence.get("source_documents") or []
            )
            if d
        ]
        self.brand = [
            d for d in (_doc("brand", t) for t in evidence.get("brand_documents") or []) if d
        ]
        self.author = [
            d for d in (_doc("author", t) for t in evidence.get("author_documents") or []) if d
        ]

    def named_in(self, sentence: str) -> list[str]:
        names = [self.brand_name] if _contains_name(sentence, self.brand_name) else []
        return names + [n for n in self.entities if _contains_name(sentence, n)]

    def candidates(self, unit: _Unit, *, kinds: Iterable[str]) -> list[_Doc]:
        """Evidence that could back a claim in this sentence.

        A sentence that cites a retrieved URL is held to THAT source. A sentence
        naming a product is held to evidence about that product: the approved
        brand info for the brand, a search result mentioning it otherwise — a
        price found on a page about a different product proves nothing.
        """
        kinds = set(kinds)
        pool: list[_Doc] = []
        if "source" in kinds:
            cited = [d for d in self.sources if d.url and d.url in unit.cited_urls]
            pool.extend(cited or self.sources)
        if "brand" in kinds:
            pool.extend(self.brand)
        if "author" in kinds:
            pool.extend(self.author)

        named = self.named_in(unit.text)
        if not named:
            return pool
        return [
            d
            for d in pool
            if d.kind == "author"
            or (d.kind == "brand" and self.brand_name in named)
            or any(_contains_name(d.text, n) for n in named)
        ]


def _overlap(sentence_tokens: set[str], doc: _Doc) -> float:
    if not sentence_tokens:
        return 0.0
    return len(sentence_tokens & doc.tokens) / len(sentence_tokens)


def _numbers_supported(
    unit: _Unit, spans: list[str], docs: list[_Doc], *, min_overlap: float
) -> bool:
    wanted = set().union(*(_numbers(s) for s in spans)) if spans else set()
    if not wanted:
        return False
    sentence_tokens = _tokens(unit.text)
    for doc in docs:
        if wanted <= doc.numbers and (
            doc.kind != "source" or _overlap(sentence_tokens, doc) >= min_overlap
        ):
            return True
    return False


# ── detection ───────────────────────────────────────────────────────────────


def _numeric_claim_spans(text: str) -> dict[str, list[str]]:
    spans: dict[str, list[str]] = {}
    prices = [m.group(0) for m in _PRICE_RE.finditer(text)]
    if prices:
        spans["pricing"] = prices
    stats = [m.group(0) for m in _PERCENT_RE.finditer(text)]
    stats += [m.group(0) for m in _MULTIPLIER_RE.finditer(text)]
    for m in _COUNT_RE.finditer(text):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        # Small counts ("3 plugins you need", "5 templates") are list sizes, not
        # market claims. A "+" / k / million suffix or a three-digit figure is.
        if m.group(2) or value >= 100:
            stats.append(m.group(0))
    if stats:
        spans["statistic"] = stats
    versions = [m.group(0) for m in _VERSION_RE.finditer(text)]
    versions += [m.group(0) for m in _DATED_EVENT_RE.finditer(text)]
    if versions:
        spans["version_or_date"] = versions
    return spans


def _fabricated_experience(unit: _Unit, index: _EvidenceIndex) -> Optional[str]:
    text = unit.text
    if not _FIRST_PERSON_RE.search(text):
        return None
    # The first testing word the sentence doesn't deny ("we haven't tested every product,
    # but we tested the top five" is still a claim).
    testing = next(
        (
            m
            for m in _TESTING_RE.finditer(text)
            if not _NEGATION_BEFORE_RE.search(text[: m.start()])
        ),
        None,
    )
    if testing:
        # The pipeline never runs hands-on tests, so a first-person testing claim
        # is invented unless a retrieved source describes that exact test.
        if not any(
            _overlap(_tokens(text), d) >= 0.6 for d in index.candidates(unit, kinds=("source",))
        ):
            return testing.group(0)
    for pattern in (_YEARS_EXPERIENCE_RE, _QUANTIFIED_WORK_RE):
        match = pattern.search(text)
        if not match:
            continue
        span = match.group(0)
        span_numbers = {n for n in _numbers(span) if not _YEAR_RE.fullmatch(n)}
        if pattern is _QUANTIFIED_WORK_RE and not span_numbers:
            continue  # "we reviewed the 2026 pricing pages" — a year, not a tally
        profile_docs = index.author + index.brand
        if span_numbers:
            if not any(span_numbers <= d.numbers for d in profile_docs):
                return span
        elif not any(
            _contains_name(d.text, word)
            for d in profile_docs
            for word in re.findall(r"decades?|years?", span, re.IGNORECASE)
        ):
            return span
    outcome = _CLIENT_OUTCOME_RE.search(text)
    if outcome:
        numbers = _numbers(text)
        supported = any(
            (numbers <= d.numbers if numbers else _overlap(_tokens(text), d) >= 0.5)
            and (d.kind != "source" or _overlap(_tokens(text), d) >= 0.5)
            for d in index.candidates(unit, kinds=("source", "brand"))
        )
        if not supported:
            return outcome.group(0)
    return None


_SUPERLATIVE_LEAD_RE = re.compile(
    r"^(?:is|are|remains|stands out as|emerges as|comes out as)\s+"
    r"(?:(?:clearly|easily|simply|by far|undoubtedly|hands down|arguably)\s+)?(?:the\s+)?",
    re.IGNORECASE,
)


def _superlative(unit: _Unit, index: _EvidenceIndex) -> Optional[str]:
    """Unqualified absolute verdicts ("is the best", "leads the market", "clear winner").

    Qualified, fit-based positioning ("the best fit for agencies", "our pick for
    small teams") is not matched — that is how a brand is legitimately promoted.
    An absolute stands only when a retrieved source about the same product
    states that exact superlative (e.g. a market-share report).
    """
    for pattern in _SUPERLATIVE_RES:
        match = pattern.search(unit.text)
        if not match:
            continue
        phrase = " ".join(_SUPERLATIVE_LEAD_RE.sub("", match.group(0)).lower().split())
        docs = index.candidates(unit, kinds=("source",))
        if phrase and any(phrase in " ".join(d.text.lower().split()) for d in docs):
            continue
        return match.group(0)
    return None


def _competitor_claim(unit: _Unit, index: _EvidenceIndex) -> Optional[str]:
    """A limitation or pejorative attributed to a named non-brand product."""
    text = unit.text
    if not index.entities:
        return None
    names = ([index.brand_name] if index.brand_name else []) + index.entities
    for negative in _NEGATIVE_CAPABILITY_RE.finditer(text):
        # "with WordPress you don't need a plugin" is advice to the reader, not a
        # claim about the product.
        if _PERSON_SUBJECT_RE.search(text[max(0, negative.start() - 16) : negative.start()]):
            continue
        # Attribute the negative to the nearest product named BEFORE it: "Nextly
        # lacks WordPress's plugin catalogue" is the brand's own honest con, not a
        # claim about WordPress.
        subject, subject_pos = None, -1
        for name in names:
            for m in re.finditer(
                rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text, re.IGNORECASE
            ):
                if subject_pos < m.start() < negative.start():
                    subject, subject_pos = name, m.start()
        if subject is None or (index.brand_name and subject.lower() == index.brand_name.lower()):
            continue
        # Grade only the clause that makes the claim ("Strapi does not support
        # visual editing"), not the consequence the writer attached to it.
        clause_end = _CLAUSE_BOUNDARY_RE.search(text, negative.end())
        clause = text[subject_pos : clause_end.start() if clause_end else len(text)]
        claim_tokens = _tokens(clause) - _tokens(subject) - _tokens(index.brand_name)
        if any(
            _contains_name(doc.text, subject) and _overlap(claim_tokens, doc) >= 0.6
            for doc in index.sources
        ):
            continue
        return f"{subject}: {negative.group(0)}"
    return None


def _brand_capability(unit: _Unit, index: _EvidenceIndex) -> Optional[str]:
    if not index.brand_name or not _contains_name(unit.text, index.brand_name):
        return None
    match = _CAPABILITY_RE.search(unit.text)
    if not match:
        return None
    obj = re.split(r"[.;!?]|\s—\s|\s-\s|\bbut\b|\bwhile\b", unit.text[match.end() :], maxsplit=1)[0]
    brand_tokens = {t.lower() for t in index.brand_name.split()}
    terms = [
        t
        for t in _NAMED_TERM_RE.findall(obj)
        if t not in _GENERIC_CAPITALIZED and t.lower() not in brand_tokens
    ]
    if not terms:
        return None
    backing = [d.text for d in index.brand] + [
        d.text for d in index.sources if _contains_name(d.text, index.brand_name)
    ]
    missing = [t for t in terms if not any(_contains_name(text, t) for text in backing)]
    if not missing:
        return None
    return f"{match.group(0)} {', '.join(dict.fromkeys(missing))}"


def find_unsupported_claims(text: str, evidence: ClaimEvidence) -> list[Claim]:
    """Every claim in `text` that no available evidence supports, in reading order."""
    index = _EvidenceIndex(evidence or {})
    claims: list[Claim] = []
    for unit in _units(text):
        sentence = unit.text

        for category, spans in _numeric_claim_spans(sentence).items():
            named = index.named_in(sentence)
            is_brand_sentence = bool(index.brand_name) and index.brand_name in named
            first_person = bool(_FIRST_PERSON_RE.search(sentence))
            kinds = ["source"]
            if is_brand_sentence or not named:
                kinds.append("brand")
            if first_person and not named:
                kinds.append("author")
            docs = index.candidates(unit, kinds=kinds)
            if not _numbers_supported(unit, spans, docs, min_overlap=0.25):
                claims.append(Claim(category, sentence, ", ".join(dict.fromkeys(spans))))

        for category, detector in (
            ("fabricated_experience", _fabricated_experience),
            ("absolute_superlative", _superlative),
            ("competitor_claim", _competitor_claim),
            ("brand_capability", _brand_capability),
        ):
            span = detector(unit, index)
            if span:
                claims.append(Claim(category, sentence, span))
    return claims


def describe_unsupported_claims(claims: list[Claim], limit: int = 10) -> str:
    """Repair-ready detail: each offending sentence plus what to do with it."""
    lines = [
        f"{len(claims)} factual claim(s) are not supported by the verified search sources, the "
        "approved brand info or the author profile. Fix each one in place — remove or soften it, "
        "never replace it with a guessed value, and do not add a generic disclaimer:"
    ]
    for claim in claims[:limit]:
        sentence = claim.sentence if len(claim.sentence) <= 220 else claim.sentence[:217] + "..."
        lines.append(
            f'- [{claim.category}] "{sentence}" (unsupported: {claim.span}) -> '
            f"{CLAIM_REPAIR_GUIDANCE[claim.category]}"
        )
    if len(claims) > limit:
        lines.append(
            f"- ...and {len(claims) - limit} more of the same kinds; apply the same rules."
        )
    return "\n".join(lines)
