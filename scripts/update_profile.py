#!/usr/bin/env python3
"""Generate dynamic, self-hosted GitHub profile SVG stats and sync README sections.

Designed to run via GitHub Actions on a daily schedule (zero third-party image
servers, 100% served from GitHub's own CDN).
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

USERNAME = "ipv1337"
ORG = "VitruvianSoftware"
BLOG_POSTS_URL = "https://ipv1337.dev/blog/posts.json"

REPO_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPO_ROOT / "README.md"
SVG_PATH = REPO_ROOT / "assets" / "github-stats.svg"

LANG_COLORS = {
    "Go": "#00ADD8",
    "Swift": "#F05138",
    "Rust": "#DEA584",
    "Python": "#3572A5",
    "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A",
    "Kotlin": "#A97BFF",
    "HCL": "#844FBA",
    "Shell": "#89E051",
    "Nix": "#7E7EFF",
    "HTML": "#E34C26",
    "Ruby": "#701516",
    "Starlark": "#76D275",
}


def github_get(endpoint: str) -> object:
    """Fetch JSON from GitHub REST API using GITHUB_TOKEN or `gh api`."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        url = f"https://api.github.com/{endpoint.lstrip('/')}"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "ipv1337-profile-updater",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # Local fallback via gh CLI
    out = subprocess.check_output(
        ["gh", "api", endpoint.lstrip("/")],
        text=True,
    )
    return json.loads(out)


def fetch_all_repos(prefix: str) -> list[dict]:
    """Paginate through all public repositories for a user or org."""
    repos: list[dict] = []
    page = 1
    while True:
        batch = github_get(f"{prefix}/repos?type=public&per_page=100&page={page}")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_blog_posts() -> list[dict]:
    """Fetch published blog posts from ipv1337.dev/blog/posts.json."""
    try:
        req = urllib.request.Request(
            BLOG_POSTS_URL,
            headers={"User-Agent": "ipv1337-profile-updater"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        # Fallback if running in a restricted local environment
        local_posts = REPO_ROOT.parent / "ipv1337.github.io" / "blog" / "posts.json"
        if local_posts.exists():
            return json.loads(local_posts.read_text(encoding="utf-8"))
        return []


def render_svg(
    public_repos: int,
    org_repos: int,
    total_stars: int,
    followers: int,
    top_langs: list[tuple[str, float]],
) -> str:
    """Render a crisp GitHub-dark SVG stats & top-languages card."""
    updated = datetime.now(timezone.utc).strftime("%b %d, %Y UTC")

    # Build stacked language bar (width 776px)
    bar_width = 776
    bar_x = 32
    bar_segments = []
    legend_items = []
    cursor_x = float(bar_x)
    for idx, (lang, pct) in enumerate(top_langs):
        color = LANG_COLORS.get(lang, "#8b949e")
        seg_w = max(4.0, bar_width * (pct / 100.0))
        if idx == len(top_langs) - 1:
            seg_w = max(0.0, (bar_x + bar_width) - cursor_x)
        bar_segments.append(
            f'<rect x="{cursor_x:.1f}" y="130" width="{seg_w:.1f}" height="10" fill="{color}"/>'
        )
        cursor_x += seg_w

        lx = 32 + idx * 155
        legend_items.append(
            f'<circle cx="{lx + 5}" cy="160" r="4.5" fill="{color}"/>'
            f'<text x="{lx + 15}" y="164" fill="#c9d1d9" font-size="12" font-family="\'Segoe UI\', Ubuntu, Sans-Serif">'
            f'{html.escape(lang)} <tspan fill="#8b949e">{pct:.1f}%</tspan></text>'
        )

    stats = [
        ("Public Repos", str(public_repos), "#58a6ff"),
        ("VitruvianSoftware", f"{org_repos} repos", "#a371f7"),
        ("Stars Earned", str(total_stars), "#e3b341"),
        ("Followers", str(followers), "#3fb950"),
    ]
    stat_cards = []
    for i, (label, val, accent) in enumerate(stats):
        x = 32 + i * 198
        stat_cards.append(
            f'<rect x="{x}" y="52" width="182" height="58" rx="8" fill="#161b22" stroke="#30363d" stroke-width="1"/>'
            f'<text x="{x + 14}" y="74" fill="#8b949e" font-size="11" font-weight="600" font-family="\'Segoe UI\', Ubuntu, Sans-Serif">{html.escape(label)}</text>'
            f'<text x="{x + 14}" y="98" fill="{accent}" font-size="20" font-weight="700" font-family="\'Segoe UI\', Ubuntu, Sans-Serif">{html.escape(val)}</text>'
        )

    return f"""<svg width="840" height="190" viewBox="0 0 840 190" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="James H. Nguyen GitHub Statistics">
  <defs>
    <clipPath id="bar-clip">
      <rect x="32" y="130" width="776" height="10" rx="5"/>
    </clipPath>
  </defs>
  <rect x="0.5" y="0.5" width="839" height="189" rx="12" fill="#0d1117" stroke="#30363d"/>
  <text x="32" y="34" fill="#f0f6fc" font-size="16" font-weight="700" font-family="'Segoe UI', Ubuntu, Sans-Serif">GitHub Overview — @{USERNAME}</text>
  <text x="808" y="34" text-anchor="end" fill="#8b949e" font-size="11" font-family="'Segoe UI', Ubuntu, Sans-Serif">Updated {html.escape(updated)}</text>
  {''.join(stat_cards)}
  <g clip-path="url(#bar-clip)">
    {''.join(bar_segments)}
  </g>
  {''.join(legend_items)}
</svg>
"""


def replace_section(content: str, marker: str, body: str) -> str:
    pattern = re.compile(
        rf"(<!-- {re.escape(marker)}:START -->)(.*?)(<!-- {re.escape(marker)}:END -->)",
        re.DOTALL,
    )
    return pattern.sub(rf"\1\n{body}\n\3", content)


def main() -> None:
    user = github_get(f"users/{USERNAME}")
    user_repos = fetch_all_repos(f"users/{USERNAME}")
    org_repos = fetch_all_repos(f"orgs/{ORG}")

    total_stars = sum(r.get("stargazers_count", 0) for r in user_repos) + sum(
        r.get("stargazers_count", 0) for r in org_repos
    )

    # Language distribution across non-fork user repos + non-template org repos
    lang_counts: Counter[str] = Counter()
    for r in user_repos:
        if not r.get("fork") and r.get("language"):
            lang_counts[r["language"]] += 1
    for r in org_repos:
        desc = r.get("description") or ""
        if not r.get("fork") and not desc.startswith("Aspect Workflows Template") and r.get("language"):
            lang_counts[r["language"]] += 1

    top_5 = lang_counts.most_common(5)
    total_lang = sum(c for _, c in top_5) or 1
    top_langs = [(lang, (count / total_lang) * 100.0) for lang, count in top_5]

    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(
        render_svg(
            public_repos=user.get("public_repos", len(user_repos)),
            org_repos=len(org_repos),
            total_stars=total_stars,
            followers=user.get("followers", 0),
            top_langs=top_langs,
        ),
        encoding="utf-8",
    )

    # Select flagship VitruvianSoftware repos (exclude template scaffolds & site repo)
    featured_org = [
        r
        for r in org_repos
        if not r.get("archived")
        and not (r.get("description") or "").startswith("Aspect Workflows Template")
        and r.get("name") not in {"site-vitruviansoftware-dev", "homebrew-tap"}
    ]
    featured_org.sort(
        key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at", "")),
        reverse=True,
    )

    repo_lines = [
        "| Project | Language | Description |",
        "|---------|----------|-------------|",
    ]
    for r in featured_org[:6]:
        name = r["name"]
        url = r["html_url"]
        lang = r.get("language") or "—"
        desc = (r.get("description") or "").replace("|", "\\|")
        repo_lines.append(f"| [**{ORG}/{name}**]({url}) | `{lang}` | {desc} |")

    posts = fetch_blog_posts()
    blog_lines = []
    for p in posts[:5]:
        title = p["title"]
        url = f"https://ipv1337.dev{p['url']}"
        date = p.get("date", "")
        blog_lines.append(f"- [{title}]({url}) — _{date}_")

    readme = README_PATH.read_text(encoding="utf-8")
    readme = replace_section(readme, "VITRUVIAN-REPOS", "\n".join(repo_lines))
    if blog_lines:
        readme = replace_section(readme, "BLOG-POSTS", "\n".join(blog_lines))
    README_PATH.write_text(readme, encoding="utf-8")
    print(f"✅ Updated {SVG_PATH.relative_to(REPO_ROOT)} and {README_PATH.name}")


if __name__ == "__main__":
    main()
