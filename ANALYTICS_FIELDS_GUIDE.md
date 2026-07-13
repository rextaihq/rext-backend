# Analytics Fields Guide — Dashboard, Inventory, Health, Opportunity & AI Diagnosis

Simple explanation of every field shown in the 5 analytics modules, where each value comes from, and what the Configuration screen does.
(Updated 2026-07-13 — tracking is now automatic; content selection is no longer required.)

---

## 0. Where the data comes from (the big picture)

All 5 modules read from **our own database tables**. No module calls Google directly when you open a page.
A background sync job (runs every 6 hours, or on-demand refresh) fetches data from Google and saves it into these tables:

| Table | Filled by | Contains |
|---|---|---|
| `ContentPerformanceMetric` (source=`search_console`) | Search Console API sync | Daily clicks, impressions, CTR, position **per article URL** |
| `ContentPerformanceMetric` (source=`analytics`) | GA4 API sync | Daily sessions, users, pageviews, engagement **per article URL** |
| `ContentQueryMetric` | Search Console API sync | Which search keywords drive each article (per query) |
| `ContentIndexStatus` | GSC URL Inspection sync | Is the article indexed by Google? (PASS / FAIL / NEUTRAL) |
| `ContentSEOData` | Our own SEO analysis (when article is created/edited) | SEO score, readability, focus keyword, meta title/description |
| `Content` | Our product | Title, status, word count, updated date, WordPress URL |
| `ContentPublishingResult` | WordPress publish flow | Published URL, publish status, tracking on/off per article |

**Important:** if the sync has not run, or Google itself has no traffic for the site (new/test site), all metric fields show **0 or empty**. That is not a bug — Google has nothing to report yet.

---

## 1. The Configuration screen (why you select a site there)

The Configuration option in the dashboard is the **one required setup step** after connecting Google OAuth. It exists because of a simple problem:

> Your Google account can have access to MANY Search Console sites and MANY GA4 properties (personal projects, client sites, old sites...). The system cannot guess which one belongs to which WordPress site.

So the Configuration screen asks you to make the link, per WordPress site:

```
WordPress site  →  which GSC property?   →  which GA4 property?
testwp.rext.ai  →  sc-domain:testwp.rext.ai  →  properties/544641621
```

**What happens when you save (POST /google/sites/select):**
1. The GA4 property is validated against Google (do you really have access?).
2. A `GoogleSiteMapping` row is saved — this tells the sync job *where* to fetch data from for this site.
3. **All published articles on that site are automatically enrolled in tracking** (`tracking_enabled=TRUE`). No second step needed.
4. From now on, every **new** article published to this site is tracked automatically too.

**Is this design correct? Yes.** One OAuth connection per workspace + one mapping per WordPress site is the right model:
- It supports multiple WordPress sites in one workspace, each mapped to different Google properties.
- Selecting the site in the dropdown is unavoidable — only you know which GSC/GA4 property reports on which WordPress site.
- After my 2026-07-13 change it is also the ONLY manual step: configure once, data flows forever.

The dropdowns themselves are filled by `GET /google/sites`, which returns your GSC sites and GA4 properties from a 15-minute cache (so we don't hammer Google's API on every page load).

> Note: `PUT /google/sites/{site_id}/tracked-content` still exists, but it is now an **opt-out** tool (untick specific articles you don't want tracked) — not a required setup step.

---

## 2. Dashboard (Module 1)

**File:** `src/services/dashboard_service.py`
It compares the **last 28 days** vs the **28 days before that**. All GSC numbers are the **summation of every published article's** synced rows (tracking is automatic, so "all tracked" = "all published").

### KPI cards

| Field | Simple meaning | Data source |
|---|---|---|
| `total_articles` | How many articles are **published** on the connected site(s). Pure DB count — needs no Google data, which is why it shows even when everything else is 0. | `ContentPublishingResult` where status = published |
| `indexed_pages` | How many of your pages Google has indexed (can appear in search results). | `ContentIndexStatus` rows with verdict = PASS |
| `organic_clicks` | Total times people clicked your articles in Google Search (last 28 days). Sum over all articles. | `ContentPerformanceMetric` (search_console) |
| `organic_impressions` | Total times your articles were **shown** in Google Search results. | same |
| `average_position` | Average ranking position in Google (1 = top result), weighted by impressions. | same |
| `ctr` | Click-through rate = clicks ÷ impressions. 0.05 = 5% of people who saw you clicked. | computed |
| `organic_traffic_trend` | % change in clicks vs the previous 28 days. `null` = no previous data to compare. | computed |
| `total_opportunity_score` | Sum of all articles' opportunity scores (untapped traffic potential of the whole workspace). | `ContentScoringService` (live computation from GSC data) |
| `articles_requiring_update` | Articles declining (clicks dropped 20%+ or position 3+ worse) that need a refresh. | `ContentScoringService` |
| `average_health_score` | Average of every article's health score (0–100). | `ContentHealthScoreService` |

### Trend charts (4 charts, daily points, last 28 days)

`click_trend`, `impression_trend`, `position_trend`, `ctr_trend` — all built from the same `ContentPerformanceMetric` (search_console) rows, summed per day across all articles.

**Multi-site note:** the dashboard is workspace-wide. If two WordPress sites are configured, the numbers are the blended sum of both sites' articles (no per-site filter yet).

---

## 3. Content Inventory (Module 2)

**File:** `src/services/content_inventory_service.py`
One row **per article**. Filterable, sortable, paginated.

| Field | Simple meaning | Data source |
|---|---|---|
| `content_id` | Article's internal ID | `Content` |
| `url` | The article's live WordPress URL | `Content.wordpress_url` |
| `title` | Article title | `Content` |
| `primary_keyword` | The focus keyword the article targets | `ContentSEOData.focus_keyphrase` |
| `status` | draft / published etc. | `Content.status` |
| `health_score` | This article's quality score 0–100 (Module 3) | `ContentHealthScoreService` |
| `opportunity_score` | Traffic potential if improved, 0–100 (Module 4 logic) | `ContentScoringService` from GSC data |
| `organic_clicks` | Clicks from Google Search, last 28 days, this article only | `ContentPerformanceMetric` (search_console) |
| `organic_impressions` | Times shown in Google Search, last 28 days | same |
| `ctr` | Clicks ÷ impressions for this article | computed |
| `average_position` | This article's average Google ranking | same |
| `last_updated` | When the article was last edited | `Content.updated_at` |
| `ai_recommendation` | Always empty for now — reserved for future expansion of Module 5 | not implemented |
| `trend` | `growing` / `declining` / `stable` / `new` / `no_data` — clicks vs previous 28 days | computed |
| `needs_update` | `true` if clicks dropped 20%+ or ranking got 3+ positions worse | computed |
| `low_ctr` | `true` if actual CTR is under half of what's expected for its position (weak title/meta) | computed |
| `is_indexed` | Is this page in Google's index? `null` = never checked yet | `ContentIndexStatus` |
| `is_cannibalized` | `true` if 2+ published articles target the **same keyword** (they compete with each other) | counted from `ContentSEOData` |

**Filters:** `published`, `growing`, `declining`, `needs_update`, `high_opportunity` (score ≥ 70), `low_ctr`, `not_indexed`, `cannibalized`.
**Sortable by:** title, status, opportunity_score, organic_clicks, organic_impressions, ctr, average_position, last_updated.

---

## 4. Content Health Score (Module 3)

**File:** `src/services/content_health_score_service.py`
One quality score 0–100 per article, made from 6 weighted parts:

| Component | Weight | Simple meaning | Data source |
|---|---|---|---|
| `technical_seo` | 20% | Is the page indexed? PASS=100, NEUTRAL=60, FAIL=20. **Hard rule:** confirmed NOT-indexed caps the whole score at 40 (a page nobody can find has no value). | `ContentIndexStatus` |
| `seo_optimization` | 25% | On-page SEO quality (meta title/description, keyword usage). | `ContentSEOData.seo_score` (fallback calculation if missing) |
| `content_quality` | 20% | Readability + trust of the writing. | `ContentSEOData.readability_score` + `trust_score` |
| `topical_coverage` | 15% | Topic depth: word count, headings, secondary keywords. | `Content` body structure |
| `freshness` | 10% | How recently updated. Full score within 90 days, decays to 20 after 2 years. | `Content.updated_at` |
| `user_engagement` | 10% | Engagement rate, bounce rate, session duration from GA4, last 28 days. | `ContentPerformanceMetric` (analytics/GA4) |

**Missing data rule:** components with no data are skipped and the other weights re-balance to 100%. But if less than 40% of total weight has real data, no overall score is shown (avoids fake "100/100" for a brand-new draft).

Response: `overall`, `components` (per-part scores), `capped_due_to_indexing`.

---

## 5. Opportunity Score (Module 4)

**File:** `src/services/opportunity_score_service.py`
Ranks articles by "how much traffic could I gain if I improve this?" — GSC data only.

### How the score is built

| Input | Weight | Simple meaning |
|---|---|---|
| CTR Gap | 35% | CTR lower than expected for your position → people see you but don't click → improve title/meta. Uses the article's **top keyword** when available. |
| Position / Strikability | 30% | Position 4–20 ("almost page 1") is the sweet spot — small effort, big gain. |
| Demand Volume | 25% (multiplier) | High impressions = a real audience exists. Scales the score 0.3x–1.0x. |
| Impression Trend | 10% (small nudge) | Rising interest = small boost (0.9x–1.1x). |
| Technical SEO gate | — | Confirmed NOT-indexed page → score capped at 40 (fix indexing first). |

### Response fields

| Field | Simple meaning | Data source |
|---|---|---|
| `score` | 0–100. Higher = more potential gain per effort | computed |
| `estimated_traffic_gain` | Extra clicks/month at a realistic target position (not a "#1 fantasy") | modeled from impressions + expected CTR |
| `estimated_ranking_gain` | Positions you could realistically climb | computed |
| `priority_level` | Critical / High / Medium / Low | derived from score |
| `estimated_time_to_improve` | Rough effort bucket (heuristic) | derived |
| `target_query` | The specific keyword the estimate is anchored to (highest-impression query) | `ContentQueryMetric` |
| `target_query_impressions` | How often that keyword showed your article | `ContentQueryMetric` |
| `current_position` / `target_position` | Where you rank now → where you could rank | GSC data |
| `current_impressions` | Article's impressions in the window | `ContentPerformanceMetric` |
| `capped_due_to_indexing` | `true` if the not-indexed cap was applied | `ContentIndexStatus` |

**Not included on purpose:** competitor comparison and content-gap analysis (need external SERP data — future modules).

---

## 6. AI Diagnosis (Module 5) — Ranking Diagnosis

**File:** `src/services/ranking_diagnosis_service.py`
**Endpoint:** `GET /google/content/{content_id}/ranking-diagnosis?days=28&generate_ai_summary=false`
Answers: *"why did this article's search performance change?"* Two layers:

### Layer 1 — Rule-based (always runs, free, no AI)

Compares last 28 days vs the previous 28 days of the article's GSC data and classifies the change:

| Classification | Meaning |
|---|---|
| `ranking_drop` | Average position got 3+ places worse |
| `ctr_collapse` | Position held steady but clicks fell 20%+ → classic signature of an AI Overview / SERP feature stealing clicks |
| `visibility_drop` | Clicks AND impressions both fell 20%+ → losing visibility overall |
| `improving` | Position improved 3+ places |
| `stable` | No significant change |
| `no_data` | Not enough synced data in both windows to compare |

For the negative classifications it also detects **signals** (possible causes), each with real numbers behind it:

| Signal key | Meaning |
|---|---|
| `serp_feature_suspected` | Position steady but clicks collapsed → AI Overview or other SERP feature likely displacing the result |
| `content_freshness_declined` | Freshness health component < 40 — article not updated recently |
| `weak_topical_coverage` | Topical coverage component < 40 — article may be too short/thin |
| `technical_seo_issue` | Technical SEO component < 40 — check indexing |
| `missing_faq_section` | No FAQ section / FAQPage schema found in the article |
| `weak_internal_linking` | No internal links recorded for the article |
| `outdated_statistics` | Newest year mentioned in the text is 2+ years old — stats may be stale |

### Layer 2 — Optional AI narration (`generate_ai_summary=true`)

- Costs **1 credit** (`ANALYSIS_STAGE_CREDITS["ranking_diagnosis"]`).
- The LLM receives ONLY the layer-1 facts and its only job is to narrate them in plain English.
- **Grounding check:** if the AI output mentions causes layer 1 never detected (competitors, search intent, algorithm updates), it is rejected and the rule-based template summary is used instead.
- If the AI fails, credits are insufficient, or output is ungrounded → the rule-based diagnosis is returned unchanged. The endpoint **never fails because of the AI** (`ai_generated=false`, `ai_unavailable_reason` says why).

### Response fields

`classification`, `window_days`, `position_current/previous/delta`, `clicks_current/previous/delta_pct`, `impressions_current/previous/delta_pct`, `top_query`, `top_query_position`, `signals[]` (key/label/detail), `summary`, `reasons[]`, `ai_generated`, `ai_unavailable_reason`.

**Dependency:** works only for articles with synced GSC data (`ContentPerformanceMetric`). New articles show `no_data` until 2 windows of data exist.

---

## 7. Quick troubleshooting: "why is everything 0 / empty?"

1. **Google not connected** → connect OAuth first.
2. **Site not configured** → select GSC property + GA4 property in the Configuration screen (`GoogleSiteMapping`).
3. **Tracking is automatic** (since 2026-07-13): configuring a site auto-enrolls all its published articles, and new publishes are tracked automatically. `PUT /google/sites/{site_id}/tracked-content` is only an opt-out.
4. **Sync hasn't run yet** → runs every 6 hours; or trigger on demand with `?refresh=true` on the content performance endpoint. Note: GSC finalizes data ~2–3 days late, so the newest days always lag.
5. **Google really has no data** → new/test sites have 0 impressions and 0 GA4 sessions. The APIs return 200 OK with zero/empty rows. Verified live 2026-07-10 for `testwp.rext.ai`: 0 clicks / 0 impressions in GSC, zero GA4 sessions — also check the GA4 tag is actually installed on the WordPress site.
