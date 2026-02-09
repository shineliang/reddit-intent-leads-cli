# Reddit Intent Lead Finder (CLI)

Find high-intent Reddit posts/comments ("looking for X", "any alternative to Y", "recommendation?", etc.) and export a lightweight lead list you can actually act on.

## What it does
- Search across subreddits for your keywords
- Score intent with simple, transparent heuristics
- Export:
  - `leads.csv` (for CRM / spreadsheet)
  - `leads.md` (for reviewing)
  - optional: outreach draft replies (BYO API key)

## Install

### Option A: pipx (recommended)
```bash
pipx install git+https://github.com/<YOUR_GITHUB>/reddit-intent-leads-cli
```

### Option B: pip
```bash
pip install git+https://github.com/<YOUR_GITHUB>/reddit-intent-leads-cli
```

## Usage

### 1) Scan for leads
```bash
rilf \
  --query "crm alternative" \
  --subs "SaaS,startups,Entrepreneur,smallbusiness" \
  --days 14 \
  --limit 80 \
  --out out
```

Outputs:
- `out/leads.csv`
- `out/leads.md`
- `out/raw.jsonl` (debug)

### 2) (Optional) Generate outreach drafts (BYO key)
```bash
export OPENAI_API_KEY=...   # optional provider; see below
rilf drafts --in out/leads.csv --out out/drafts.md
```

## Notes / constraints
- Uses Reddit's public JSON endpoints (no official API key).
- Rate limits happen. The CLI is polite (sleep + backoff), but big scans can still be throttled.
- Drafts are **optional** and should be reviewed before posting.

## License
MIT
