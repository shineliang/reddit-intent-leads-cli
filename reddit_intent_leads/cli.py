from __future__ import annotations

import csv
import datetime as dt
import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .reddit import Lead, fetch_comments, search_posts
from .scoring import score_intent

app = typer.Typer(add_completion=False, help="Reddit Intent Lead Finder (CLI)")
console = Console()


@app.command()
def keywords(
    product: str = typer.Option("", "--product", "-p", help="Competitor/product name, e.g. 'HubSpot'"),
    category: str = typer.Option("", "--category", "-c", help="Category, e.g. 'crm', 'invoice software'"),
    out: Path | None = typer.Option(None, "--out", help="Optional output file path"),
):
    """Generate high-intent Reddit search queries for lead-finding."""

    product = (product or "").strip()
    category = (category or "").strip() or "your tool"

    templates = [
        "{category} alternative",
        "alternative to {product}",
        "{product} alternative",
        "{product} vs",
        "recommend {category}",
        "best {category}",
        "looking for {category}",
        "need a {category}",
        "{category} for small business",
        "cheap {category}",
        "open source {category}",
    ]

    queries: list[str] = []
    for t in templates:
        if "{product}" in t and not product:
            continue
        queries.append(t.format(product=product, category=category).strip())

    # de-dup while preserving order
    seen = set()
    deduped: list[str] = []
    for q in queries:
        if q.lower() in seen:
            continue
        seen.add(q.lower())
        deduped.append(q)

    text = "\n".join(deduped) + "\n"
    console.print(text)

    if out:
        out = out.expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        console.print(f"Wrote: {out}")


def _parse_subs(subs: str) -> list[str]:
    out: list[str] = []
    for s in (subs or "").split(","):
        s = s.strip().removeprefix("r/")
        if s:
            out.append(s)
    return out


@app.command()
def scan(
    query: str = typer.Option(..., "--query", "-q", help="Search query, e.g. 'crm alternative'"),
    subs: str = typer.Option(
        "SaaS,startups,Entrepreneur,smallbusiness",
        "--subs",
        help="Comma-separated subreddits (without r/)",
    ),
    days: int = typer.Option(14, "--days", help="Lookback window in days"),
    limit: int = typer.Option(80, "--limit", help="Max posts to fetch (best-effort)"),
    include_comments: bool = typer.Option(True, "--comments/--no-comments", help="Score comments too"),
    max_comments: int = typer.Option(50, "--max-comments", help="Max comments per post"),
    min_intent: float = typer.Option(2.0, "--min-intent", help="Filter threshold"),
    sleep_s: float = typer.Option(1.2, "--sleep", help="Polite delay between requests"),
    out: Path = typer.Option(Path("out"), "--out", help="Output directory"),
):
    """Scan Reddit for high-intent leads and export CSV/Markdown."""

    subs_list = _parse_subs(subs)
    if not subs_list:
        raise typer.BadParameter("--subs must not be empty")

    now = dt.datetime.now(dt.timezone.utc)
    after_utc = int((now - dt.timedelta(days=days)).timestamp())

    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = str(out / "cache")

    posts = search_posts(query=query, subs=subs_list, limit=limit, after_utc=after_utc, cache_dir=cache_dir, sleep_s=sleep_s)

    raw_path = out / "raw.jsonl"
    leads: list[Lead] = []

    with raw_path.open("w", encoding="utf-8") as f:
        for p in posts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    for p in posts:
        title = (p.get("title") or "").strip()
        selftext = (p.get("selftext") or "").strip()
        text = f"{title}\n\n{selftext}".strip()

        permalink = p.get("permalink") or ""
        url = f"https://www.reddit.com{permalink}" if permalink else (p.get("url") or "")
        subreddit = p.get("subreddit") or ""

        ir = score_intent(text)
        if ir.score >= min_intent:
            leads.append(
                Lead(
                    kind="post",
                    subreddit=subreddit,
                    title=title,
                    author=p.get("author") or "",
                    created_utc=int(p.get("created_utc") or 0),
                    score=int(p.get("score") or 0),
                    url=url,
                    text=text[:2000],
                    intent_score=ir.score,
                    signals=ir.signals,
                )
            )

        if include_comments and permalink:
            comments = fetch_comments(permalink, max_comments=max_comments, cache_dir=cache_dir, sleep_s=sleep_s)
            for c in comments:
                body = (c.get("body") or "").strip()
                if not body:
                    continue
                irc = score_intent(body)
                if irc.score < min_intent:
                    continue
                leads.append(
                    Lead(
                        kind="comment",
                        subreddit=subreddit,
                        title=title,
                        author=c.get("author") or "",
                        created_utc=int(c.get("created_utc") or 0),
                        score=int(c.get("score") or 0),
                        url=url,
                        text=body[:1500],
                        intent_score=irc.score,
                        signals=irc.signals,
                    )
                )

    leads.sort(key=lambda x: (x.intent_score, x.score), reverse=True)

    csv_path = out / "leads.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "kind",
                "subreddit",
                "intent_score",
                "score",
                "author",
                "created_utc",
                "title",
                "url",
                "signals",
                "text",
            ],
        )
        w.writeheader()
        for l in leads:
            w.writerow(
                {
                    "kind": l.kind,
                    "subreddit": l.subreddit,
                    "intent_score": f"{l.intent_score:.2f}",
                    "score": l.score,
                    "author": l.author,
                    "created_utc": l.created_utc,
                    "title": l.title,
                    "url": l.url,
                    "signals": ",".join(l.signals),
                    "text": l.text,
                }
            )

    md_path = out / "leads.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# Leads for: {query}\n\n")
        f.write(f"- generated_at: {now.isoformat()}\n")
        f.write(f"- subs: {', '.join('r/'+s for s in subs_list)}\n")
        f.write(f"- days: {days}\n- min_intent: {min_intent}\n\n")
        for i, l in enumerate(leads[:200], 1):
            f.write(f"## {i}. [{l.kind}] r/{l.subreddit} score={l.score} intent={l.intent_score:.2f}\n")
            f.write(f"- url: {l.url}\n")
            f.write(f"- signals: {', '.join(l.signals)}\n")
            if l.title:
                f.write(f"- title: {l.title}\n")
            f.write(f"\n> {l.text.replace('\n', '\n> ')}\n\n")

    table = Table(title=f"Top leads: {query}")
    table.add_column("#", justify="right")
    table.add_column("sub")
    table.add_column("kind")
    table.add_column("intent", justify="right")
    table.add_column("score", justify="right")
    table.add_column("url")

    for i, l in enumerate(leads[:10], 1):
        table.add_row(str(i), f"r/{l.subreddit}", l.kind, f"{l.intent_score:.2f}", str(l.score), l.url)

    console.print(table)
    console.print(f"\nWrote: {csv_path}")
    console.print(f"Wrote: {md_path}")
    console.print(f"Wrote: {raw_path}")


if __name__ == "__main__":
    app()
