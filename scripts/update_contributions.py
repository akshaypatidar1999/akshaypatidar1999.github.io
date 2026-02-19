#!/usr/bin/env python3
"""Fetch merged PRs from GitHub and update the contributions section in index.html."""

import os
import sys
import time
from collections import OrderedDict, defaultdict
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

GITHUB_USERNAME = "akshaypatidar1999"
INDEX_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")

# Repos to exclude from the contributions list
EXCLUDED_REPOS = {
    "dream11/odin",
    "dream11/homebrew-tools",
}

START_MARKER = "<!-- BEGIN CONTRIBUTIONS -->"
END_MARKER = "<!-- END CONTRIBUTIONS -->"

CHEVRON_SVG = (
    '<svg class="repo-chevron" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2">'
    '<polyline points="9 18 15 12 9 6"/></svg>'
)

# Categories in display order. First matching rule wins. Unmatched repos go to "Other".
CATEGORIES = [
    {
        "name": "Odin",
        "link_text": "dream-horizon-org.github.io/odin",
        "link_url": "https://dream-horizon-org.github.io/odin/",
        "match": lambda repo: "odin" in repo,
    },
    {
        "name": "Vert.x",
        "link_text": "vertx.io",
        "link_url": "https://vertx.io/",
        "match": lambda repo: "vertx" in repo,
    },
]

OTHER_CATEGORY = {"name": "Other", "link_text": None, "link_url": None}


def github_request(url, headers):
    """Make a GET request to the GitHub API with retry on rate limit."""
    req = Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code in (403, 429):
                retry_after = int(e.headers.get("Retry-After", "60"))
                print(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            print(f"Error: GitHub API returned {e.code}")
            print(e.read().decode("utf-8"))
            sys.exit(1)
    print("Error: Exceeded retry attempts")
    sys.exit(1)


def fetch_merged_prs():
    """Fetch all merged PRs authored by the user via unauthenticated GitHub Search API.

    Using unauthenticated requests ensures only public repo PRs are returned.
    """
    headers = {"Accept": "application/vnd.github+json"}

    all_prs = []
    page = 1
    per_page = 100

    while True:
        params = urlencode({
            "q": f"type:pr author:{GITHUB_USERNAME} is:merged",
            "per_page": per_page,
            "page": page,
            "sort": "created",
            "order": "desc",
        })
        url = f"https://api.github.com/search/issues?{params}"
        data = github_request(url, headers)
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            html_url = item["html_url"]
            parts = html_url.split("/")
            owner, repo, pr_number = parts[3], parts[4], int(parts[6])
            full_repo = f"{owner}/{repo}"
            if full_repo in EXCLUDED_REPOS:
                continue
            all_prs.append({
                "repo": full_repo,
                "pr_number": pr_number,
                "title": item["title"],
                "url": html_url,
            })

        total_count = data.get("total_count", 0)
        if page * per_page >= total_count or page * per_page >= 1000:
            break
        page += 1

    repos = set(pr["repo"] for pr in all_prs)
    print(f"Fetched {len(all_prs)} merged PRs across {len(repos)} repos")
    return all_prs


def categorize_prs(prs):
    """Group PRs by category then by repo. Repos sorted by PR count desc."""
    repos = defaultdict(list)
    for pr in prs:
        repos[pr["repo"]].append(pr)

    categorized = defaultdict(lambda: defaultdict(list))
    for repo_name, repo_prs in repos.items():
        category = OTHER_CATEGORY
        for cat in CATEGORIES:
            if cat["match"](repo_name):
                category = cat
                break
        categorized[category["name"]][repo_name] = sorted(
            repo_prs, key=lambda p: p["pr_number"], reverse=True
        )

    result = OrderedDict()
    for cat in CATEGORIES:
        if cat["name"] in categorized:
            sorted_repos = OrderedDict(
                sorted(categorized[cat["name"]].items(), key=lambda x: len(x[1]), reverse=True)
            )
            result[cat["name"]] = {"config": cat, "repos": sorted_repos}

    if OTHER_CATEGORY["name"] in categorized:
        sorted_repos = OrderedDict(
            sorted(categorized[OTHER_CATEGORY["name"]].items(), key=lambda x: len(x[1]), reverse=True)
        )
        result[OTHER_CATEGORY["name"]] = {"config": OTHER_CATEGORY, "repos": sorted_repos}

    return result


def html_escape(text):
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def generate_contributions_html(categorized):
    """Generate the full contributions div HTML matching the existing structure."""
    lines = []
    lines.append("      <!-- BEGIN CONTRIBUTIONS -->")
    lines.append('      <div class="contributions">')
    lines.append("        <h2>Open Source Contributions</h2>")
    lines.append("")

    for cat_name, cat_data in categorized.items():
        config = cat_data["config"]
        repos = cat_data["repos"]

        lines.append(f"        <!-- {cat_name} -->")
        lines.append('        <div class="org-section">')

        if config.get("link_url"):
            lines.append(
                f'          <div class="org-label">{config["name"]} '
                f'<a href="{config["link_url"]}" target="_blank" '
                f'rel="noopener">{config["link_text"]}</a></div>'
            )
        else:
            lines.append(f'          <div class="org-label">{config["name"]}</div>')

        lines.append('          <div class="repo-list">')
        lines.append("")

        for repo_name, prs in repos.items():
            pr_count = len(prs)
            count_label = f"{pr_count} PR" if pr_count == 1 else f"{pr_count} PRs"

            pr_links = ""
            for pr in prs:
                escaped_title = html_escape(pr["title"])
                pr_links += (
                    f'<a class="pr-item" href="{pr["url"]}" '
                    f'target="_blank" rel="noopener">'
                    f'<span class="pr-badge">merged</span>'
                    f"{escaped_title}</a>"
                )

            lines.append(
                f"            <details class=\"repo-item\">"
                f"<summary>{CHEVRON_SVG}"
                f'<span class="repo-name">{repo_name}</span>'
                f'<span class="repo-count">{count_label}</span>'
                f"</summary>"
                f'<div class="pr-list">{pr_links}</div></details>'
            )
            lines.append("")

        lines.append("          </div>")
        lines.append("        </div>")
        lines.append("")

    lines.append("      </div>")
    lines.append("      <!-- END CONTRIBUTIONS -->")
    return "\n".join(lines)


def update_index_html(new_html):
    """Replace the contributions section in index.html between the markers."""
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    start = content.find(START_MARKER)
    end = content.find(END_MARKER)
    if start == -1 or end == -1:
        print("Error: Could not find contribution markers in index.html")
        sys.exit(1)

    # Include leading whitespace on the marker line
    line_start = content.rfind("\n", 0, start)
    if line_start != -1:
        start = line_start + 1

    end += len(END_MARKER)
    new_content = content[:start] + new_html + content[end:]

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Updated {INDEX_PATH}")


def main():
    prs = fetch_merged_prs()
    if not prs:
        print("Warning: No merged PRs found. Skipping update.")
        sys.exit(0)

    categorized = categorize_prs(prs)

    total_prs = sum(len(pl) for c in categorized.values() for pl in c["repos"].values())
    total_repos = sum(len(c["repos"]) for c in categorized.values())
    print(f"Categorized {total_prs} PRs across {total_repos} repos into {len(categorized)} sections")

    html = generate_contributions_html(categorized)
    update_index_html(html)


if __name__ == "__main__":
    main()
