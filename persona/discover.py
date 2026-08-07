#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
discover.py — built directly on your Rankunat.ipynb notebook flow.

YOUR NOTEBOOK, STEP FOR STEP:
    adv.crawl('https://nextlyhq.com/', 'nextly.jl', follow_links=True)
    crawl_df = pd.read_json('nextly.jl', lines=True)
    -> Company Profile section  (title, meta_desc, body_text, jsonld_@graph)
    -> Schema Markup section    (og:image, jsonld_@context, jsonld_@graph, ...)

This file keeps all three of those exactly as you wrote them, then adds the
persona layer on top using ONLY the default crawl columns.

The crawl call is unchanged from your notebook:
    adv.crawl(url, jl, follow_links=True)

OPTIONAL (off by default, your call): pass deep=True to add ONE xpath
selector for mailto: links. Scrapy's default link extractor drops mailto:,
so that is the only way to read <a href="mailto:...">. Without it, emails are
still found when written as plain text in the page body.

USAGE
    python discover.py --url https://nextlyhq.com/
    python discover.py --url https://nextlyhq.com/ --deep      # + emails
    python discover.py --jl nextly.jl                          # reuse a crawl

IMPORT
    from discover import discover_personas_from_url   # -> list of personas
    from discover import discover_full_profile        # -> company + schema + personas
"""

import os
import re
import json
import argparse
from urllib.parse import urlparse, urljoin

import pandas as pd

SEP = "@@"          # advertools joins repeated values with this
BREAK = " ¶ "  # element boundary: no name regex may match across it

# ============================================================================
# REGEX FILTERS  (the "filter the .jl with pandas regex" layer)
# ============================================================================

RE_AUTHOR_URL = re.compile(
    r"/(author|authors|writer|writers|contributor|contributors|editor|editors"
    r"|profile|profiles|member|members|people)/[^/?#]+/?$", re.I)

RE_TEAM_URL = re.compile(
    r"/(our-team|the-team|team|teams|our-people|people|staff|leadership|management"
    r"|founders|meet-the-team|meet-our-team|who-we-are|about-us|about|company)/?$", re.I)

RE_ARTICLE_URL = re.compile(
    r"/(blog|news|article|articles|insight|insights|resource|resources|post|posts"
    r"|story|stories|press|update|updates|journal|magazine|guide|guides|learn)/", re.I)

RE_EXCLUDE_URL = re.compile(
    r"/(category|categories|tag|tags|page|feed|amp|wp-json|wp-content|wp-admin"
    r"|search|cart|checkout|login|signup|privacy|terms|sitemap)(/|$)"
    r"|\.(jpg|jpeg|png|gif|svg|webp|pdf|css|js|xml|zip|ico|mp4|woff2?)(\?|$)", re.I)

_TOK = (r"(?:[A-Z][a-zA-Z'\u2019\-]{1,19}|[A-Z]\.|van|von|de|del|der|da|di"
        r"|bin|binte|al|el|Mc|Mac)")
RE_NAME = re.compile(rf"^{_TOK}(?:\s+{_TOK}){{1,3}}$")

# Ranks, honorifics and titles are NOT names. "SP Investigation Mr" came from
# a byline swallowing a police rank plus a trailing honorific.
HONORIFICS = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "professor", "sir", "madam", "mx",
    "sp", "dsp", "sho", "ig", "dig", "asp", "capt", "captain", "col", "colonel",
    "sgt", "sergeant", "lt", "maj", "gen", "hon", "rev", "engr", "adv", "ch",
    "ceo", "cto", "coo", "cfo", "md", "phd", "esq", "jr", "sr",
}

# Abstract nouns that appear as title-case section headings on about/team
# pages and are structurally indistinguishable from a two-word human name.
ABSTRACT_HEADINGS = {
    "satisfaction", "quality", "growth", "success", "excellence", "innovation",
    "integrity", "transparency", "commitment", "support", "results", "trust",
    "passion", "teamwork", "vision", "mission", "values", "culture", "impact",
    "expertise", "experience", "dedication", "reliability", "creativity",
    "strategy", "solutions", "performance", "delivery", "communication",
    "ownership", "accountability", "collaboration", "star", "north",
}

# Tokens that never appear inside a human name but are extremely common in
# Title Case headings and article titles. A single one of these anywhere in a
# candidate is disqualifying. "will", "can" and "may" are deliberately absent —
# they are real given names.
NON_NAME_TOKENS = {
    # interrogatives, determiners, pronouns
    "what", "why", "how", "when", "where", "who", "whom", "whose", "which",
    "this", "that", "these", "those", "you", "your", "yours", "we", "our",
    "ours", "us", "my", "mine", "me", "it", "its", "their", "them", "they",
    # auxiliaries and copulas
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does",
    "did", "done", "should", "would", "could", "shall", "must", "have", "has",
    # function words
    "the", "and", "but", "for", "with", "from", "into", "onto", "upon",
    "about", "after", "before", "during", "while", "because", "than", "then",
    "else", "also", "too", "very", "just", "only", "not", "never", "always",
    "here", "there", "now", "today", "yet", "still", "each", "every", "both",
    "few", "many", "much", "most", "least", "other", "another", "such",
    "same", "own", "any", "some", "none", "of", "in", "on", "at", "to", "or",
    "as", "if", "so", "up", "out", "off", "over", "under",
    # listicle / how-to scaffolding — where "RankingGrow What" came from
    "step", "steps", "guide", "guides", "tips", "tip", "ways", "way", "post",
    "reasons", "reason", "things", "list", "top", "best", "new", "free",
    "easy", "quick", "simple", "ultimate", "complete", "final", "full",
    # call-to-action verbs — where "Hire Virtual Assistant" came from
    "hire", "buy", "sell", "order", "join", "meet", "find", "see", "view",
    "download", "subscribe", "discover", "explore", "follow", "share",
    "click", "try", "use", "make", "need", "want", "know", "learn", "start",
    "stop", "fix", "check", "create", "build", "grow", "boost", "increase",
    "improve", "choose", "pick", "compare",
    # business nouns that render as Title Case section headings
    "marketing", "sales", "seo", "sem", "ppc", "design", "designs",
    "development", "engineering", "agency", "virtual", "assistant", "expert",
    "experts", "specialist", "consultant", "manager", "director", "officer",
    "head", "lead", "client", "clients", "customer", "customers", "partner",
    "partners", "work", "works", "working", "portfolio", "testimonial",
    "testimonials", "pricing", "plan", "plans", "package", "packages",
    "case", "study", "studies", "project", "projects", "process", "approach",
    "solution", "solutions",
}

RE_NAME_BLOCK = re.compile(
    r"\b(blog|news|team|about|contact|home|service|services|product|products|company"
    r"|career|careers|privacy|terms|search|menu|read|more|view|all|posts|article"
    r"|category|admin|editorial|staff|guest|newsletter|subscribe|login|sign|get"
    r"|started|demo|pricing|support|faq|help|copyright|reserved|policy|cookie|book"
    r"|january|february|march|april|may|june|july|august|september|october"
    r"|november|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I)

# Explicit authorship phrases. Safe to run anywhere on the page.
RE_BYLINE_STRICT = re.compile(
    r"\b(?:written\s+by|posted\s+by|published\s+by|reviewed\s+by|words\s+by"
    r"|story\s+by|author[:\s])\s*[:\-\u2013]?\s*"
    rf"({_TOK}(?:\s+{_TOK}){{0,3}})", re.I)

# Bare "by". Only ever safe immediately under the article title \u2014 anywhere
# else it is ordinary prose ("used by Google Analytics to collect data",
# "sorted by Relevance"), which is exactly how product names became authors.
RE_BYLINE_LOOSE = re.compile(
    r"\bby\s*[:\-\u2013]?\s*"
    rf"({_TOK}(?:\s+{_TOK}){{0,3}})", re.I)

BYLINE_LOOSE_WINDOW = 400   # chars from the start of the body


def name_from_byline(captured):
    """
    The byline capture is greedy: "By Mobeen Abdullah on January 12" grabs
    "Mobeen Abdullah on January". Trim tokens off the RIGHT until a clean
    name emerges, longest first, so the real name survives the trailing date
    / "Share this" / "Updated" noise instead of being thrown away.
    """
    if not captured:
        return None
    toks = captured.split()
    for end in range(len(toks), 1, -1):          # 4 tokens -> 3 -> 2
        n = clean_name(" ".join(toks[:end]))
        if n:
            return n
    return None


def byline_text(row):
    """
    Where bylines actually live.

    body_text is <p>/<span>/<li> ONLY, so a byline inside a <div> is invisible
    there. The author name is also very often a LINK ("By <a>Mobeen</a>"), which
    lands in links_text, not body_text. Search all three.

    Headings and anchors are separate elements and MUST be joined with a
    barrier the name regex cannot cross. Joining them with a plain space lets
    "...written by RankingGrow" + "What Is The Future Of..." fuse into the
    single fake byline "RankingGrow What Is The".
    """
    body = " ".join(_list(_get(row, "body_text")))
    heads = BREAK.join(_list(_get(row, "h1")) + _list(_get(row, "h2"))
                       + _list(_get(row, "h3")) + _list(_get(row, "h4")))
    anchors = BREAK.join(t for t in _list_aligned(_get(row, "links_text")) if t)
    return body, heads, anchors

RE_ORG_BYLINE = re.compile(
    r"^([A-Z][A-Za-z0-9.\-]{1,25}(?:\s+[A-Z][A-Za-z0-9.\-]{1,25}){0,2}\s+"
    r"(?:Team|Staff|Editors|Editorial|Newsroom|Desk|Contributors))$")


def is_org_byline(v):
    """
    "Nextly Team" is a byline. "Meet The Team" is a page heading — same shape,
    so RE_ORG_BYLINE matches both. A real org byline is a BRAND name plus the
    suffix, so every word before the suffix must be a proper noun, not a verb
    or an article.
    """
    toks = v.split()
    return len(toks) >= 2 and not any(
        t.strip(".,").lower() in NON_NAME_TOKENS for t in toks[:-1])


RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

SOCIAL_DOMAINS = {
    "linkedin":  r"linkedin\.com/(in|pub)/",
    "twitter":   r"(twitter\.com|x\.com)/(?!share|intent|home)",
    "github":    r"github\.com/",
    "instagram": r"instagram\.com/",
    "facebook":  r"facebook\.com/(?!sharer|share)",
    "medium":    r"medium\.com/@",
    "youtube":   r"youtube\.com/(@|c/|channel/)",
    "dribbble":  r"dribbble\.com/",
    "behance":   r"behance\.net/",
}

RE_ROLE = re.compile(
    r"\b(Co[- ]?Founder|Founder|CEO|CTO|COO|CMO|CFO|CPO|Chief\s+[A-Za-z]+\s+Officer"
    r"|President|Vice\s+President|VP\s+[Oo]f\s+[A-Za-z]+|Head\s+[Oo]f\s+[A-Za-z ]{2,25}"
    r"|Editor[- ][Ii]n[- ]Chief|Managing\s+Editor|Senior\s+[A-Za-z]+|Lead\s+[A-Za-z]+"
    r"|Director\s+[Oo]f\s+[A-Za-z ]{2,25}|Director|Manager|Engineer|Developer|Designer"
    r"|Editor|Writer|Author|Journalist|Copywriter|Consultant|Analyst|Specialist"
    r"|Strategist|Architect|Scientist|Researcher|Coordinator|Executive|Partner"
    r"|Owner|Principal|Marketing\s+[A-Za-z]+|Content\s+[A-Za-z]+)\b")

# Function words only — used to trim the greedy tail off a matched job title.
ROLE_TRAIL_STOP = {
    "for", "of", "and", "the", "a", "an", "to", "in", "on", "at", "with",
    "from", "by", "or", "as", "is", "are", "was", "were", "our", "your",
    "their", "his", "her", "we", "you", "they", "this", "that", "who",
    "award", "awards", "please", "feel", "reach", "contact", "email",
}

# The ONLY optional addition to your notebook's crawl call. Off by default.
DEEP_XPATH = {"x_mailto": '//a[starts-with(@href,"mailto:")]/@href'}


# ============================================================================
# HELPERS
# ============================================================================

def _list(val):
    """advertools packs repeated values into one '@@'-joined string."""
    if val is None:
        return []
    if isinstance(val, float) and pd.isna(val):
        return []
    if isinstance(val, (list, tuple)):
        out = []
        for v in val:
            out.extend(_list(v))
        return out
    if isinstance(val, dict):
        return [val]
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", "<na>"}:
        return []
    return [p.strip() for p in s.split(SEP) if p.strip()]


def _list_aligned(val):
    """
    Same as _list() but KEEPS empty slots.

    links_url and links_text are PARALLEL arrays. advertools emits a link with
    no anchor text as an empty slot ("a@@@@c"). Dropping empties shifts every
    later index and pairs names with the wrong URL. Never strip when zipping.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    if isinstance(val, (list, tuple)):
        return [("" if v is None else str(v).strip()) for v in val]
    s = str(val)
    if not s.strip() or s.strip().lower() in {"nan", "none", "<na>"}:
        return []
    return [p.strip() for p in s.split(SEP)]


def zip_links(row):
    """Yield (anchor_text, absolute_url) pairs, nav/header/footer links removed."""
    base = row["url"]
    urls = _list_aligned(_get(row, "links_url"))
    texts = _list_aligned(_get(row, "links_text"))

    # Boilerplate: nav, header and footer links are site chrome, not people.
    chrome = set()
    for c in ("nav_links_url", "header_links_url", "footer_links_url"):
        chrome.update(_list(_get(row, c)))
    chrome = {urljoin(base, u) for u in chrome if u}

    out = []
    for i, u in enumerate(urls):
        if not u:
            continue
        absu = urljoin(base, u)
        if absu in chrome:
            continue
        t = texts[i] if i < len(texts) else ""
        out.append((t, absu))
    return out


def _get(row, col):
    try:
        return row[col]
    except (KeyError, IndexError):
        return None


def clean_name(raw):
    if not raw:
        return None
    s = re.sub(r"\s+", " ", str(raw)).strip(" \t\n\r-\u2013\u2014\u2022|,:")
    s = re.sub(r"^(by|written by|posted by|author)[:\s]+", "", s, flags=re.I).strip()
    if not (2 <= len(s) <= 60):
        return None
    if any(ch.isdigit() for ch in s):
        return None
    if RE_NAME_BLOCK.search(s):
        return None
    # Strip LEADING honorifics ("Dr Ali Raza" -> "Ali Raza") rather than
    # discarding a real person. A honorific in any other position means the
    # match ran into surrounding prose ("SP Investigation Mr") -> reject.
    toks = s.split()
    while toks and toks[0].strip(".,").lower() in HONORIFICS:
        toks = toks[1:]
    if len(toks) < 2:
        return None
    if any(t.strip(".,").lower() in HONORIFICS for t in toks):
        return None
    s = " ".join(toks)
    if not RE_NAME.match(s):
        return None
    low = [t.strip(".").lower() for t in toks]
    if any(t in ABSTRACT_HEADINGS for t in low):
        return None
    # Reject on any non-name token, checking hyphen parts too so that
    # "Step-by-Step" is caught the same way a bare "Step" would be.
    for t in low:
        if t in NON_NAME_TOKENS:
            return None
        if any(part in NON_NAME_TOKENS for part in t.split("-") if part):
            return None
    # all-caps abbreviations are ranks/acronyms, not given names
    if any(len(t) <= 4 and t.isalpha() and t.isupper() for t in toks):
        return None
    return s if s[0].isupper() else None


def norm_key(name):
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def classify_url(url):
    if not isinstance(url, str):
        return "other"
    path = urlparse(url).path or "/"
    if RE_EXCLUDE_URL.search(path):
        return "excluded"
    if RE_AUTHOR_URL.search(path):
        return "author_page"
    if RE_TEAM_URL.search(path):
        return "team_page"
    if RE_ARTICLE_URL.search(path) and len(path.rstrip("/").split("/")) >= 3:
        return "article"
    return "other"


def extract_socials(urls, base=""):
    found = {}
    for u in urls:
        if not u:
            continue
        u = u.strip()
        if u.startswith("/"):
            u = urljoin(base, u)
        for key, pat in SOCIAL_DOMAINS.items():
            if re.search(pat, u, re.I):
                found.setdefault(key, u)
    return found


def extract_emails(*chunks):
    out = set()
    for c in chunks:
        for item in _list(c):
            for m in RE_EMAIL.findall(item.replace("mailto:", "")):
                if not re.search(r"\.(png|jpe?g|gif|webp|svg)$", m, re.I):
                    out.add(m.lower())
    return sorted(out)


def tidy_role(raw):
    """
    "Head Of Marketing For award nomination" -> "Head Of Marketing".

    The role patterns end in a greedy [A-Za-z ] run, so they swallow whatever
    prose follows the title. Trim tokens off the right while they are function
    words or clearly not part of a job title. NON_NAME_TOKENS is NOT usable
    here — it contains "marketing", "head", "director", which are exactly the
    words a job title is made of.
    """
    if not raw:
        return None
    toks = re.sub(r"\s+", " ", raw).strip().split()
    while len(toks) > 1 and toks[-1].strip(".,").lower() in ROLE_TRAIL_STOP:
        toks.pop()
    return " ".join(toks) or None


def role_near(text, name):
    if not text or not name:
        return None
    for m in re.finditer(re.escape(name), text):
        r = RE_ROLE.search(text[m.end(): m.end() + 120])
        if r:
            return tidy_role(r.group(0))
    return None


def bio_near(text, name, n=400, others=None):
    """Text after the name, CUT at the next person's name so bios don't bleed."""
    if not text or not name:
        return None
    m = re.search(re.escape(name), text)
    if not m:
        return None
    chunk = text[m.end(): m.end() + n]
    for other in (others or []):
        if other == name:
            continue
        cut = chunk.find(other)
        if cut > 0:
            chunk = chunk[:cut]
    # also stop at obvious section breaks
    for stop in ("Values", "What we believe", "Our values", "Contact",
                 "Join us", "Careers", "FAQ"):
        cut = chunk.find(stop)
        if cut > 20:
            chunk = chunk[:cut]
    return re.sub(r"\s+", " ", chunk).strip(" -\u2013\u2014|\u2022,:") or None


def page_text(row):
    """body_text is <p>, <span>, <li> ONLY. Headings live in h1..h6, so join them."""
    parts = _list(_get(row, "body_text"))
    for h in ("h1", "h2", "h3", "h4", "h5", "h6"):
        parts += _list(_get(row, h))
    return " ".join(parts)


# ============================================================================
# STEP 1 + 2 — YOUR NOTEBOOK, VERBATIM
# ============================================================================

def crawl_site(url, out_jl, deep=False):
    """Your notebook's call: adv.crawl(url, 'nextly.jl', follow_links=True)"""
    import advertools as adv
    if os.path.exists(out_jl):
        os.remove(out_jl)
    if deep:
        adv.crawl(url, out_jl, follow_links=True, xpath_selectors=DEEP_XPATH)
    else:
        adv.crawl(url, out_jl, follow_links=True)
    return out_jl


def load_crawl(jl_path):
    """Your notebook: pd.read_json('nextly.jl', lines=True)"""
    df = pd.read_json(jl_path, lines=True)
    if "status" in df.columns:
        df = df[df["status"] == 200]
    return df[df["url"].notna()].drop_duplicates(subset=["url"]).reset_index(drop=True)


# ============================================================================
# YOUR NOTEBOOK SECTION: "Company Profile"   (brand-voice input)
# ============================================================================

def company_profile(crawl_df):
    """crawl_df[['title','meta_desc','body_text','jsonld_@graph']].iloc[0]"""
    cols = [c for c in ("title", "meta_desc", "body_text", "jsonld_@graph")
            if c in crawl_df.columns]
    if not len(crawl_df) or not cols:
        return {}
    return crawl_df[cols].iloc[0].to_dict()


# ============================================================================
# YOUR NOTEBOOK SECTION: "Schema Markup"
# ============================================================================

def schema_markup(crawl_df, target_url=None):
    """crawl_df[['og:image','jsonld_@context','jsonld_@graph',
                 'jsonld_1_@context','jsonld_1_@graph']].iloc[0]"""
    cols = [c for c in ("og:image", "jsonld_@context", "jsonld_@graph",
                        "jsonld_1_@context", "jsonld_1_@graph")
            if c in crawl_df.columns]
    if not len(crawl_df) or not cols:
        return {}
    sub = crawl_df
    if target_url:
        hit = crawl_df[crawl_df["url"] == target_url]
        if len(hit):
            sub = hit
    return sub[cols].iloc[0].to_dict()


# ============================================================================
# PERSONA LAYER — default crawl columns only
# ============================================================================

def is_person_profile_href(href):
    return bool(re.search(r"/(author|authors|team|people|staff|member|members"
                          r"|profile|about/[a-z\-]+)/[^/?#]+/?$", href or "", re.I))


def extract_team_members(df_team):
    members = {}
    for _, row in df_team.iterrows():
        page_url = row["url"]
        text = page_text(row)
        pairs = zip_links(row)                      # aligned + chrome removed

        cands = []
        tag_of = {}          # name -> heading tag it came from (h2/h3/...)
        # a) headings — team cards put the person's name in h2/h3/h4.
        #    This is the STRONGEST signal, so it goes first.
        for h in ("h2", "h3", "h4", "h5"):
            for t in _list(_get(row, h)):
                n = clean_name(t)
                if n:
                    cands.append((n, None, "heading"))
                    tag_of.setdefault(n, h)

        # b) anchor text, but ONLY when the href actually looks like a person
        #    profile. Nav items like "For Developers" point at feature pages
        #    and are rejected here.
        for t, u in pairs:
            n = clean_name(t)
            if n and is_person_profile_href(u):
                cands.append((n, u, "profile_link"))

        # A real team member is written about in the page copy. A nav label is
        # not. Requiring the name to appear in the body text kills the rest.
        cands = [c for c in cands if c[2] == "profile_link" or c[0] in text]

        # CORROBORATION for heading-derived names. A section heading like
        # "Client Satisfaction" is structurally identical to a two-word human
        # name, so a heading alone is not enough. Require one of:
        #   - a job title detected right after the name, or
        #   - a link to a person profile, or
        #   - a matching image alt (team cards put the headshot alt = the name)
        img_alts = " . ".join(_list(_get(row, "img_alt")))
        corroborated = []
        for name, profile, src in cands:
            if src == "profile_link":
                corroborated.append((name, profile, src))
                continue
            if role_near(text, name):
                corroborated.append((name, profile, "heading+role"))
                continue
            if re.search(r"\b" + re.escape(name) + r"\b", img_alts):
                corroborated.append((name, profile, "heading+photo"))
                continue

        # THIRD ROUTE: repeated card structure. A team grid emits every member
        # at the same heading level. If two or more names at that level are
        # already corroborated, the level IS a person list, so accept the rest.
        # Without this, a member whose title is misspelt ("Cheif Technology
        # Officer") or simply not in RE_ROLE is silently dropped.
        strong_tags = {}
        for name, _p, _s in corroborated:
            t = tag_of.get(name)
            if t:
                strong_tags[t] = strong_tags.get(t, 0) + 1
        person_tags = {t for t, c in strong_tags.items() if c >= 2}
        have = {c[0] for c in corroborated}
        for name, profile, src in cands:
            if name in have or src != "heading":
                continue
            if tag_of.get(name) in person_tags:
                corroborated.append((name, profile, "heading+siblings"))
                have.add(name)
        cands = corroborated

        names_on_page = sorted({c[0] for c in cands}, key=lambda x: -len(x))
        socials = extract_socials([u for _, u in pairs], page_url)
        emails = extract_emails(_get(row, "x_mailto"), text)

        for name, profile, _src in cands:
            m = members.setdefault(norm_key(name), {
                "name": name, "role": None, "profile_url": None, "bio": None,
                "emails": [], "socials": {}, "found_on": []})
            m["profile_url"] = m["profile_url"] or profile
            m["role"] = m["role"] or role_near(text, name)
            m["bio"] = m["bio"] or bio_near(text, name, others=names_on_page)
            if page_url not in m["found_on"]:
                m["found_on"].append(page_url)
            if len(names_on_page) == 1:   # single-person page -> these are theirs
                m["socials"].update(socials)
                m["emails"] = sorted(set(m["emails"]) | set(emails))
    return members


def extract_authors_from_articles(df_articles, known_people=None):
    """known_people: {norm_key: name} of people already found on team pages.
    A bare name in a heading/anchor on an article is only trusted when that
    person is already known to exist on this site - never invented."""
    known_people = known_people or {}
    rows = []
    for _, row in df_articles.iterrows():
        url = row["url"]
        found = []

        # a) JSON-LD — any column mentioning author
        for col in row.index:
            if re.search(r"jsonld.*author", str(col), re.I):
                for v in _list(row[col]):
                    if isinstance(v, dict):
                        v = v.get("name") or ""
                    n = clean_name(v)
                    if n:
                        found.append((n, "jsonld"))

        # b) jsonld_@graph Person nodes — the exact structure your notebook printed
        for col in ("jsonld_@graph", "jsonld_1_@graph"):
            if col in row.index and isinstance(row[col], list):
                for node in row[col]:
                    if not isinstance(node, dict):
                        continue
                    t = node.get("@type")
                    if t == "Person" or (isinstance(t, list) and "Person" in t):
                        n = clean_name(node.get("name"))
                        if n:
                            found.append((n, "jsonld_graph"))
                    a = node.get("author")
                    for av in (a if isinstance(a, list) else [a]):
                        if isinstance(av, dict):
                            n = clean_name(av.get("name"))
                            if n:
                                found.append((n, "jsonld_author"))

        # c) meta author, if the site emits one
        for col in ("author", "article:author", "og:article:author"):
            if col in row.index:
                for v in _list(row[col]):
                    n = clean_name(v)
                    if n:
                        found.append((n, "meta_author"))

        # d) BYLINE — "By X" / "Written by X" at the START and END of the
        #    article, which is where sites put it. Searched across body text,
        #    headings and anchor text, since a byline is often a <div> or a
        #    link and therefore absent from body_text.
        body, heads, anchors = byline_text(row)
        head_slice = re.sub(r"\S*$", "", body[:1500])
        tail_slice = re.sub(r"^\S*", "", body[-1500:])
        top_slice = re.sub(r"\S*$", "", body[:BYLINE_LOOSE_WINDOW])
        zones = ((head_slice, "byline_top", RE_BYLINE_STRICT),
                 (tail_slice, "byline_bottom", RE_BYLINE_STRICT),
                 (heads, "byline_heading", RE_BYLINE_STRICT),
                 (anchors, "byline_link", RE_BYLINE_STRICT),
                 (top_slice, "byline_top_bare", RE_BYLINE_LOOSE))
        for zone, label, rx in zones:
            for m in rx.finditer(zone):
                n = name_from_byline(m.group(1))
                if n:
                    found.append((n, label))

        # e) a bare author link with no "by" keyword at all
        for t, u in zip_links(row):
            n = clean_name(t)
            if n and is_person_profile_href(u):
                found.append((n, "author_link"))

        # f) bare name (no "by" keyword) that matches a KNOWN team member.
        #    Catches bylines rendered in a <div> with no prefix.
        #    Scoped to where bylines actually sit: headings, and the first /
        #    last 600 chars of the article. links_text and meta_desc are NOT
        #    scanned - a footer or nav name is on EVERY page, so including it
        #    credited one team member with the entire blog.
        if known_people:
            zones = []
            for col in ("h2", "h3", "h4", "h5", "h6"):
                zones += _list(_get(row, col))[:20]
            zones.append(body[:600])
            zones.append(body[-600:])
            for z in zones:
                for k, full in known_people.items():
                    if re.search(r"\b" + re.escape(full) + r"\b", z):
                        found.append((full, "known_person_match"))
                        break

        links = {norm_key(clean_name(t)): u for t, u in zip_links(row)
                 if clean_name(t) and is_person_profile_href(u)}

        # ORG BYLINE: "Nextly Team", "Editorial Staff" - a real published
        # byline but NOT a person. Recorded separately, flagged is_person=False,
        # never mixed into the human personas.
        for col in ("article:author", "og:article:author", "author", "links_text",
                    "h1", "h2", "h3"):
            for v in _list(_get(row, col)):
                v = re.sub(r"\s+", " ", str(v)).strip()
                v = re.sub(r"^[A-Z]\s+(?=[A-Z])", "", v)   # drop avatar initial
                if RE_ORG_BYLINE.match(v) and is_org_byline(v):
                    found.append((v, "org_byline"))
                    break

        seen = {}
        for n, src in found:
            seen.setdefault(norm_key(n), {"name": n, "sources": set()})["sources"].add(src)

        for k, v in seen.items():
            rows.append({
                "author_key": k, "author_name": v["name"], "article_url": url,
                "article_title": _get(row, "title"), "sources": sorted(v["sources"]),
                "profile_url": links.get(k), "body_text": body,
            })
    return pd.DataFrame(rows)


def enrich_from_author_pages(df_pages):
    profiles = {}
    for _, row in df_pages.iterrows():
        url = row["url"]
        text = page_text(row)
        name = None
        for col in ("h1", "title", "og:title"):
            for v in _list(_get(row, col)):
                name = clean_name(re.split(r"[|\-\u2013\u2014]", v)[0])
                if name:
                    break
            if name:
                break
        if not name:
            slug = urlparse(url).path.rstrip("/").split("/")[-1]
            name = clean_name(slug.replace("-", " ").title())
        if not name:
            continue
        r = RE_ROLE.search(text)
        profiles[norm_key(name)] = {
            "name": name,
            "profile_url": url,
            "role": role_near(text, name) or (r.group(0) if r else None),
            "bio": " ".join(_list(_get(row, "body_text")))[:600],
            "emails": extract_emails(_get(row, "x_mailto"), text),
            "socials": extract_socials(_list(_get(row, "links_url")), url),
        }
    return profiles


# ============================================================================
# MAIN
# ============================================================================

def discover_full_profile(target_url=None, jl_path=None, out_dir=None,
                          deep=False, samples_per_author=3, sample_chars=3000,
                          keep_article_text=False):
    out_dir = out_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "persona_out")
    os.makedirs(out_dir, exist_ok=True)

    if jl_path is None:
        if not target_url:
            raise ValueError("pass target_url= or jl_path=")
        jl_path = os.path.join(out_dir, "crawl.jl")
        print(f"[1/6] adv.crawl('{target_url}', follow_links=True)"
              + ("  [+mailto selector]" if deep else ""))
        crawl_site(target_url, jl_path, deep=deep)
    else:
        print(f"[1/6] using existing crawl: {jl_path}")

    print("[2/6] pd.read_json(lines=True)")
    df = load_crawl(jl_path)
    base = target_url or (df["url"].iloc[0] if len(df) else "")
    print(f"      {len(df)} pages, {len(df.columns)} columns")

    print("[3/6] regex-classifying URLs")
    df["page_type"] = df["url"].apply(classify_url)
    counts = df["page_type"].value_counts().to_dict()
    print(f"      {counts}")

    df_team = df[df["page_type"] == "team_page"]
    df_auth = df[df["page_type"] == "author_page"]
    df_arts = df[df["page_type"] == "article"]

    print(f"[4/6] team members from {len(df_team)} team page(s)")
    team = extract_team_members(df_team)
    print(f"      {len(team)} found")

    print(f"[5/6] authors from {len(df_arts)} article(s)")
    known = {k: v["name"] for k, v in team.items()}
    adf = extract_authors_from_articles(df_arts, known_people=known)
    aprof = enrich_from_author_pages(df_auth)
    print(f"      {adf['author_key'].nunique() if len(adf) else 0} unique author(s), "
          f"{len(aprof)} author page(s)")

    print("[6/6] cross-checking author <-> team member")
    personas = {}

    def touch(k, name):
        return personas.setdefault(k, {
            "name": name, "title_role": None, "is_team_member": False,
            "is_author": False, "profile_url": None, "bio": None, "expertise": [],
            "email": None, "all_emails": [], "socials": {}, "article_count": 0,
            "article_urls": [], "sample_articles": [], "evidence": []})

    for k, m in team.items():
        p = touch(k, m["name"])
        p["is_team_member"] = True
        p["title_role"] = p["title_role"] or m["role"]
        p["profile_url"] = p["profile_url"] or m["profile_url"]
        p["bio"] = p["bio"] or m["bio"]
        p["all_emails"] = sorted(set(p["all_emails"]) | set(m["emails"]))
        p["socials"].update(m["socials"])
        p["evidence"] += [f"team_page:{u}" for u in m["found_on"]]

    if len(adf):
        for k, grp in adf.groupby("author_key"):
            p = touch(k, grp["author_name"].iloc[0])
            p["is_author"] = True
            urls = grp["article_url"].drop_duplicates().tolist()
            p["article_count"] = len(urls)
            p["article_urls"] = urls
            # pandas NaN is TRUTHY, so a bare `if x` picks NaN over a real URL.
            p["profile_url"] = p["profile_url"] or next(
                (x for x in grp["profile_url"].tolist()
                 if isinstance(x, str) and x.strip()), None)
            p["evidence"].append("author_signals:" + ",".join(
                sorted({s for r in grp["sources"] for s in r})))
            for _, r in grp.head(samples_per_author).iterrows():
                p["sample_articles"].append({
                    "url": r["article_url"], "title": r["article_title"],
                    "text": (r["body_text"] or "")[:sample_chars]})
            p["expertise"] = [t for t in grp["article_title"].tolist()
                              if isinstance(t, str)][:5]

    for k, pr in aprof.items():
        p = touch(k, pr["name"])
        p["profile_url"] = p["profile_url"] or pr["profile_url"]
        p["title_role"] = p["title_role"] or pr["role"]
        p["bio"] = p["bio"] or pr["bio"]
        p["all_emails"] = sorted(set(p["all_emails"]) | set(pr["emails"]))
        p["socials"].update(pr["socials"])
        p["evidence"].append(f"author_page:{pr['profile_url']}")

    # collapse truncated name variants into the fullest form
    keys = sorted(personas, key=len, reverse=True)
    for short in list(personas):
        for long in keys:
            if short == long or short not in personas:
                continue
            if long.startswith(short + " "):
                a, b = personas[long], personas[short]
                a["is_team_member"] |= b["is_team_member"]
                a["is_author"] |= b["is_author"]
                a["title_role"] = a["title_role"] or b["title_role"]
                a["profile_url"] = a["profile_url"] or b["profile_url"]
                a["bio"] = a["bio"] or b["bio"]
                a["all_emails"] = sorted(set(a["all_emails"]) | set(b["all_emails"]))
                a["socials"].update(b["socials"])
                merged = dict.fromkeys(a["article_urls"] + b["article_urls"])
                a["article_urls"] = list(merged)
                a["article_count"] = len(merged)
                seen_u = {s["url"] for s in a["sample_articles"]}
                a["sample_articles"] += [s for s in b["sample_articles"]
                                         if s["url"] not in seen_u]
                a["sample_articles"] = a["sample_articles"][:samples_per_author]
                a["evidence"] += b["evidence"]
                del personas[short]
                break

    def _clean(v):
        """pandas NaN is not valid JSON. Scrub it everywhere before output."""
        if isinstance(v, float) and pd.isna(v):
            return None
        if isinstance(v, dict):
            return {k: _clean(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_clean(x) for x in v]
        if v is pd.NA or v is pd.NaT:
            return None
        return v

    for p in personas.values():
        for k in list(p):
            p[k] = _clean(p[k])
        p["is_person"] = not (bool(RE_ORG_BYLINE.match(p["name"]))
                              and is_org_byline(p["name"]))
        p["email"] = p["all_emails"][0] if p["all_emails"] else None
        p["cross_check"] = ("organizational_byline" if not p["is_person"] else
                            "team_member_and_author"
                            if p["is_team_member"] and p["is_author"]
                            else "team_member_only" if p["is_team_member"]
                            else "author_only")
        p["confidence"] = round(min(1.0,
            0.35 * p["is_team_member"] + 0.35 * p["is_author"]
            + 0.10 * bool(p["profile_url"]) + 0.10 * bool(p["socials"])
            + 0.10 * bool(p["email"])), 2)
        if not keep_article_text:
            for s in p["sample_articles"]:
                s.pop("text", None)

    out = sorted(personas.values(),
                 key=lambda x: (-x["confidence"], -x["article_count"], x["name"]))

    result = {
        "target": base,
        "pages_crawled": len(df),
        "page_types": counts,
        "company_profile": company_profile(df),     # your notebook section
        "schema_markup": schema_markup(df, base),   # your notebook section
        "personas": out,
    }

    df.to_csv(os.path.join(out_dir, "pages_classified.csv"), index=False)
    with open(os.path.join(out_dir, "personas.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n[OK] {len(out)} persona(s) -> {out_dir}/personas.json")
    for p in out:
        print(f"   - {p['name']:<26} {str(p['title_role'] or '-'):<24} "
              f"{p['cross_check']:<22} articles={p['article_count']:<3} "
              f"conf={p['confidence']}")
    return result


# ============================================================================
# WRITING STYLE + EXPERTISE  (the LLM step — 2-3 articles per author)
# ============================================================================

STYLE_PROMPT = """You are analysing a writer's voice from samples of their published work.

Return ONLY a JSON object, no preamble, no markdown fences, with these keys:
  "expertise": array of 3-6 topic areas this writer covers
  "tone": 3-5 adjectives describing their tone
  "writing_style": 2-3 sentences describing sentence length, structure, and voice
  "vocabulary": "technical" | "conversational" | "academic" | "mixed"
  "person": "first" | "second" | "third" | "mixed"
  "signature_traits": array of 2-4 specific habits (e.g. "opens with a question")

Base every field only on the text given. If the samples are too short or too
few to judge a field, set that field to null rather than guessing.

WRITER: {name}
SAMPLES:
{samples}"""


def analyze_writing_style(persona, model=None, max_chars=6000):
    """
    Analyse one persona's voice from their sample_articles, via OpenAI.

    Needs OPENAI_API_KEY in the env and `pip install openai`.
    Model comes from OPENAI_MODEL, default "gpt-4o-mini". Override per call
    with model=... if your account uses something else.

    Returns a dict, or {"error": ...}. It never raises and never fabricates:
    if the samples are too thin the model is told to return null, not guess.
    """
    samples = [s for s in persona.get("sample_articles", []) if s.get("text")]
    if len(samples) < 2:
        return {"error": f"only {len(samples)} sample(s) with text; need 2+"}

    blob = "\n\n---\n\n".join(
        f"[{s.get('title') or 'untitled'}]\n{s['text'][:max_chars // len(samples)]}"
        for s in samples[:3]
    )

    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "pip install openai"}
    if not os.getenv("OPENAI_API_KEY"):
        return {"error": "OPENAI_API_KEY not set"}

    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        client = OpenAI()   # reads OPENAI_API_KEY (and OPENAI_BASE_URL if set)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=800,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system",
                 "content": "You output only valid JSON. No prose, no markdown fences."},
                {"role": "user",
                 "content": STYLE_PROMPT.format(name=persona["name"], samples=blob)},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
        return json.loads(raw)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def add_writing_styles(result, min_articles=2, model=None):
    """Fill persona['writing_style_analysis'] for everyone with 2+ articles."""
    for p in result["personas"]:
        if p["article_count"] >= min_articles:
            print(f"      analysing voice: {p['name']}")
            a = analyze_writing_style(p, model=model)
            p["writing_style_analysis"] = a
            if isinstance(a, dict) and a.get("expertise"):
                p["expertise"] = a["expertise"]     # real topics, not headlines
        else:
            p["writing_style_analysis"] = {
                "error": f"{p['article_count']} article(s); need {min_articles}+"}
    return result


def discover_personas_from_url(target_url, deep=False, out_dir=None,
                               keep_article_text=False):
    """URL in -> LIST of personas out. len(result) == number of people."""
    return discover_full_profile(target_url=target_url, deep=deep, out_dir=out_dir,
                                 keep_article_text=keep_article_text)["personas"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Persona discovery (notebook flow)")
    ap.add_argument("--url")
    ap.add_argument("--jl", help="existing .jl (skips crawling)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--deep", action="store_true",
                    help="add mailto xpath selector to capture emails")
    ap.add_argument("--style", action="store_true",
                    help="LLM voice analysis (needs ANTHROPIC_API_KEY)")
    a = ap.parse_args()
    if not a.url and not a.jl:
        ap.error("pass --url or --jl")

    res = discover_full_profile(target_url=a.url, jl_path=a.jl, out_dir=a.out,
                                deep=a.deep, keep_article_text=a.style)
    if a.style:
        print("\n[+] writing style analysis")
        add_writing_styles(res)
        for p in res["personas"]:
            for s in p.get("sample_articles", []):
                s.pop("text", None)
        out_dir = a.out or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "persona_out")
        with open(os.path.join(out_dir, "personas.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False, default=str)
        print(f"[OK] updated {out_dir}/personas.json")