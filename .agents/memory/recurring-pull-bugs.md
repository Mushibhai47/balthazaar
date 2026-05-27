---
name: Recurring post-pull bugs
description: Known bug classes that keep re-appearing after the developer's GitHub merges into this Flask app. Check these every pull before declaring health green.
---

The developer works in a separate environment and merges via GitHub. Merges semi-regularly corrupt code in predictable ways. After every pull, run these checks before reporting health.

**Why:** these bugs have each appeared more than once and each one fully crashes either Flask boot, a route, or a template render. Catching them upfront is faster than waiting for the user to hit them.

**How to apply:** run all of these checks in parallel right after `git log` shows a new HEAD:

1. **Conflict markers anywhere** — recursive grep for `^<<<<<<<|^=======|^>>>>>>>` across `*.py` and `*.html`. Merges sometimes leave these in.

2. **`Report.query` regression in main.py / tasks.py** — must always be `db.session.query(Report)`. The bare `Report.query` form has been re-introduced by merge conflicts multiple times and crashes report routes.

3. **`import os` missing in main.py** — needed by `_get_links_config()`. Has been silently dropped by merges.

4. **`{{ s | tojson }}` on a SQLAlchemy model in glossary.html** — fails because SA models aren't JSON-serializable. Must operate on a dict/list, not the model itself.

5. **Half-completed multi-block refactors** — when the developer refactors two parallel blocks (e.g. `meta_ads` and `google_ads` manual-data sections in main.py), merges sometimes land one cleanly and leave the second with a stray opening `{` before its loop, producing `SyntaxError: '{' was never closed` at import time. If Flask fails to boot with a SyntaxError, look at the line and check whether a sibling block immediately above it has the same shape — the broken one usually mirrors it but with an extra dict-open line in the wrong place.

**After-pull workflow:**
- Scan for conflict markers
- Run the four recurring-bug greps
- Restart Celery only if `tasks.py`, `sources/*`, or `database/models.py` changed (Flask auto-reloads on its own; Celery does not)
- If `database/models.py` added columns, verify the idempotent ALTER TABLE migration in `main.py`'s `with app.app_context():` block actually ran against `instance/balthazaar.db` (the active DB — `balthazaar.db` in repo root is stale and ignored)
- Hit dashboard, settings, a report detail, a report print, client edit, admin — all should return 200 with `admin/balthazaar2024` login

**Known benign noise (do not chase):**
- `LegacyAPIWarning: Query.get()` on User — SQLAlchemy 2.0 deprecation, harmless
- Browser console `Unexpected end of input` — pre-existing, benign
- `cdn.tailwindcss.com should not be used in production` — known, low priority
- Ubersuggest 403 Turnstile errors — needs `UBERSUGGEST_BEARER_TOKEN` env var to fix; code path is correct
- YouTube quota exceeded — daily API limit, recovers next day
- TikTok JSON decode errors — TikTok rate-limit, not actionable
- Resend error 1010 — from-domain not verified; fallback to `onboarding@resend.dev` is wired but only kicks in when `smtp_from` is empty
