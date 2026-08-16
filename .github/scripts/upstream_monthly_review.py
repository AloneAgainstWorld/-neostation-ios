#!/usr/bin/env python3
"""Create a monthly GitHub issue summarizing upstream NeoStation changes.

This script is intentionally read-only with respect to source code. It reads the
public upstream repository and creates/updates a review issue in the iOS port.
No upstream commit is cherry-picked, merged, or applied automatically.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_ROOT = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN", "").strip()
TARGET_REPO = os.environ.get("TARGET_REPO", "").strip()
UPSTREAM_REPO = os.environ.get(
    "UPSTREAM_REPO", "misobadev/neostation-frontend"
).strip()
EVENT_NAME = os.environ.get("EVENT_NAME", "workflow_dispatch").strip()
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "31"))
RUN_URL = os.environ.get("RUN_URL", "").strip()
STEP_SUMMARY = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
MAX_COMMITS = int(os.environ.get("MAX_COMMITS", "120"))

UTC = dt.timezone.utc

CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "NeoSync / sync",
        (
            "neosync",
            "neo_sync",
            "neo sync",
            "lib/sync/",
            "sync_provider",
            "sync_adapter",
            "billing_service",
            "auth_service",
        ),
    ),
    (
        "ScreenScraper",
        (
            "screenscraper",
            "screen scraper",
            "scraper_",
            "scraper/",
            "scraping",
        ),
    ),
    (
        "Database / migrations",
        (
            "sqlite",
            "database",
            "migration",
            "schema",
            "db version",
            "databaseversion",
            "database_version",
        ),
    ),
    (
        "Library / launch / scan",
        (
            "game_launch",
            "game launch",
            "game_list",
            "library",
            "rom scan",
            "scan_system",
            "scansystems",
            "scanner",
            "file_provider",
            "rom_path",
        ),
    ),
    (
        "iOS / native",
        (
            "ios/",
            "iphone",
            "ipad",
            "cupertino",
            "url scheme",
            "deeplink",
            "deep link",
        ),
    ),
    (
        "Dependencies / build",
        (
            "pubspec.yaml",
            "pubspec.lock",
            ".github/workflows/",
            "podfile",
            "gradle",
            "dependency",
            "dependencies",
            "flutter version",
            "dart sdk",
        ),
    ),
    (
        "UI / localization",
        (
            "lib/screens/",
            "lib/widgets/",
            "lib/l10n/",
            "locale",
            "localization",
            "localisation",
            "translation",
            "theme",
            "settings",
            "dialog",
        ),
    ),
    (
        "RetroAchievements",
        (
            "retroachievement",
            "retroachievement",
            "retro_achievement",
            "ra_",
        ),
    ),
    (
        "Platform-specific desktop / Android",
        (
            "android/",
            "windows/",
            "linux/",
            "macos/",
            "steam deck",
            "secondary screen",
            "launcher",
            "gamepad",
        ),
    ),
]

RECOMMENDED_CATEGORIES = {
    "NeoSync / sync",
    "ScreenScraper",
    "Database / migrations",
    "Library / launch / scan",
    "iOS / native",
    "Dependencies / build",
}
POTENTIAL_CATEGORIES = {"UI / localization", "RetroAchievements"}
HIGH_RISK_CATEGORIES = {"Database / migrations", "Dependencies / build"}
MEDIUM_RISK_CATEGORIES = {
    "NeoSync / sync",
    "ScreenScraper",
    "Library / launch / scan",
    "iOS / native",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    allow_404: bool = False,
) -> Any:
    url = f"{API_ROOT}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "neostation-ios-upstream-review",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    payload = None
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            if not body:
                return None
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        detail = exc.read().decode("utf-8", errors="replace")
        fail(f"GitHub API {method} {path} returned HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        fail(f"GitHub API request failed for {method} {path}: {exc}")


def paginated(path: str, params: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    page = 1
    while True:
        page_params = dict(params)
        page_params.update({"per_page": 100, "page": page})
        batch = api_request("GET", path, params=page_params)
        if not isinstance(batch, list):
            fail(f"Expected a list from {path}, got {type(batch).__name__}")
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def iso(value: dt.datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def review_period() -> tuple[dt.datetime, dt.datetime, str, str]:
    now = dt.datetime.now(UTC)
    if EVENT_NAME == "schedule":
        current_month = dt.datetime(now.year, now.month, 1, tzinfo=UTC)
        if now.month == 1:
            previous_month = dt.datetime(now.year - 1, 12, 1, tzinfo=UTC)
        else:
            previous_month = dt.datetime(now.year, now.month - 1, 1, tzinfo=UTC)
        return (
            previous_month,
            current_month,
            previous_month.strftime("%Y-%m"),
            f"[Upstream] Monthly review {previous_month:%Y-%m}",
        )

    start = now - dt.timedelta(days=max(1, LOOKBACK_DAYS))
    label = f"{LOOKBACK_DAYS}-day review ending {now:%Y-%m-%d}"
    return (
        start,
        now,
        label,
        f"[Upstream] Review {now:%Y-%m-%d} ({LOOKBACK_DAYS} days)",
    )


def subject(message: str) -> str:
    first = (message or "").splitlines()[0].strip()
    return first if first else "(no commit subject)"


def classify(message: str, files: list[str]) -> list[str]:
    haystack = "\n".join([message, *files]).lower()
    categories: list[str] = []
    for category, needles in CATEGORY_RULES:
        if any(needle in haystack for needle in needles):
            categories.append(category)
    return categories


def platform_only(files: list[str], categories: list[str]) -> bool:
    if not files:
        return False
    prefixes = (
        "android/",
        "windows/",
        "linux/",
        "macos/",
        "packages/gamepads_android/",
        "packages/gamepads_windows/",
        "packages/gamepads_linux/",
        "packages/gamepads_darwin/",
    )
    only_platform_paths = all(path.lower().startswith(prefixes) for path in files)
    only_platform_category = bool(categories) and set(categories) <= {
        "Platform-specific desktop / Android"
    }
    return only_platform_paths or only_platform_category


def integration_risk(categories: list[str]) -> str:
    category_set = set(categories)
    if category_set & HIGH_RISK_CATEGORIES:
        return "high"
    if category_set & MEDIUM_RISK_CATEGORIES:
        return "medium"
    return "low"


def priority(
    categories: list[str], local_matches: list[str], files: list[str]
) -> str:
    category_set = set(categories)
    if platform_only(files, categories):
        return "Likely platform-specific"

    score = 0
    for category in category_set:
        if category in {
            "NeoSync / sync",
            "ScreenScraper",
            "Database / migrations",
            "iOS / native",
        }:
            score += 4
        elif category == "Library / launch / scan":
            score += 3
        elif category in {"Dependencies / build", "UI / localization", "RetroAchievements"}:
            score += 2

    score += min(3, len(local_matches))

    if category_set & RECOMMENDED_CATEGORIES and score >= 5:
        return "Review recommended"
    if category_set & (RECOMMENDED_CATEGORIES | POTENTIAL_CATEGORIES) or local_matches:
        return "Potentially useful"
    return "General upstream change"


def ensure_label() -> str | None:
    label_name = "upstream-review"
    encoded = urllib.parse.quote(label_name, safe="")
    existing = api_request(
        "GET",
        f"/repos/{TARGET_REPO}/labels/{encoded}",
        allow_404=True,
    )
    if existing:
        return label_name
    try:
        api_request(
            "POST",
            f"/repos/{TARGET_REPO}/labels",
            data={
                "name": label_name,
                "color": "0969da",
                "description": "Automated review of changes from official NeoStation upstream",
            },
        )
        return label_name
    except SystemExit:
        # A missing label must never prevent the surveillance report itself.
        return None


def find_issue_by_title(title: str) -> dict[str, Any] | None:
    issues = paginated(
        f"/repos/{TARGET_REPO}/issues",
        {"state": "all", "sort": "created", "direction": "desc"},
    )
    for issue in issues:
        if "pull_request" in issue:
            continue
        if issue.get("title") == title:
            return issue
    return None


def compact_files(files: list[str], local_matches: list[str]) -> str:
    if not files:
        return "No changed-file metadata available."
    shown = files[:6]
    rendered = ", ".join(f"`{path}`" for path in shown)
    if len(files) > len(shown):
        rendered += f", +{len(files) - len(shown)} more"
    if local_matches:
        rendered += f" — **{len(local_matches)} path(s) also exist in this iOS port**"
    return rendered


def build_report(
    *,
    start: dt.datetime,
    end: dt.datetime,
    period_label: str,
    commits: list[dict[str, Any]],
    truncated: int,
) -> str:
    groups: dict[str, list[dict[str, Any]]] = {
        "Review recommended": [],
        "Potentially useful": [],
        "Likely platform-specific": [],
        "General upstream change": [],
    }
    for commit in commits:
        groups[commit["priority"]].append(commit)

    lines = [
        "# NeoStation upstream surveillance",
        "",
        "> [!IMPORTANT]",
        "> This is a **review-only report**. No upstream commit has been merged,",
        "> cherry-picked, or applied automatically to `main`.",
        "",
        f"- **Upstream:** `{UPSTREAM_REPO}`",
        f"- **Review period:** {start:%Y-%m-%d %H:%M UTC} → {end:%Y-%m-%d %H:%M UTC}",
        f"- **Period label:** {period_label}",
        f"- **Commits found:** {len(commits) + truncated}",
        f"- **Detailed commits:** {len(commits)}",
        f"- **Generated:** {dt.datetime.now(UTC):%Y-%m-%d %H:%M UTC}",
    ]
    if RUN_URL:
        lines.append(f"- **Workflow run:** {RUN_URL}")
    if truncated:
        lines.append(
            f"- **Note:** {truncated} older commit(s) were omitted from detailed analysis "
            f"because the safety cap is {MAX_COMMITS} commits per run."
        )

    lines.extend(
        [
            "",
            "## Triage summary",
            "",
            "| Classification | Count |",
            "|---|---:|",
            f"| Review recommended | {len(groups['Review recommended'])} |",
            f"| Potentially useful | {len(groups['Potentially useful'])} |",
            f"| Likely platform-specific | {len(groups['Likely platform-specific'])} |",
            f"| General upstream change | {len(groups['General upstream change'])} |",
            "",
        ]
    )

    if not commits:
        lines.extend(
            [
                "No upstream commits were found in this period.",
                "",
                "## Safety",
                "",
                "`main` was not modified by this surveillance run.",
            ]
        )
        return "\n".join(lines)

    section_notes = {
        "Review recommended": (
            "These changes touch areas that are commonly shared with the iOS port. "
            "Review and adapt them selectively on a dedicated branch."
        ),
        "Potentially useful": (
            "These changes may be useful, but should be assessed against the current "
            "iOS implementation before any code is copied."
        ),
        "Likely platform-specific": (
            "These changes appear focused on Android/desktop-specific paths or behavior. "
            "They are listed for awareness and should normally not be imported directly."
        ),
        "General upstream change": (
            "These changes did not match the current automatic relevance rules. "
            "They remain listed so nothing upstream is silently ignored."
        ),
    }

    for group_name in (
        "Review recommended",
        "Potentially useful",
        "Likely platform-specific",
        "General upstream change",
    ):
        group = groups[group_name]
        if not group:
            continue
        lines.extend([f"## {group_name}", "", section_notes[group_name], ""])
        for item in group:
            categories = ", ".join(item["categories"]) or "Unclassified"
            lines.append(
                f"- [`{item['sha'][:7]}`]({item['url']}) **{item['subject']}**"
            )
            lines.append(
                f"  - Categories: {categories} · Integration risk: **{item['risk']}**"
            )
            lines.append(f"  - Files: {compact_files(item['files'], item['local_matches'])}")
        lines.append("")

    lines.extend(
        [
            "## Recommended integration policy",
            "",
            "1. Do not merge upstream wholesale into `main`.",
            "2. Select only changes that are useful to the iOS port.",
            "3. Adapt them on a dedicated branch.",
            "4. Run formatting, `flutter analyze`, the full Flutter test suite, and an iOS build.",
            "5. Merge only after the resulting IPA has been validated.",
            "",
            "## Safety",
            "",
            "This workflow only reads upstream metadata and writes this GitHub issue. "
            "It never modifies application source code, creates an integration branch, "
            "or merges anything into `main`.",
        ]
    )
    return "\n".join(lines)


def write_step_summary(issue_url: str, counts: dict[str, int]) -> None:
    if not STEP_SUMMARY:
        return
    path = Path(STEP_SUMMARY)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("## NeoStation upstream surveillance\n\n")
        handle.write(f"- Report: {issue_url}\n")
        for name, count in counts.items():
            handle.write(f"- {name}: {count}\n")


def main() -> None:
    if not TOKEN:
        fail("GH_TOKEN is required.")
    if not TARGET_REPO:
        fail("TARGET_REPO is required.")

    start, end, period_label, issue_title = review_period()
    upstream_commits = paginated(
        f"/repos/{UPSTREAM_REPO}/commits",
        {"since": iso(start), "until": iso(end)},
    )

    truncated = max(0, len(upstream_commits) - MAX_COMMITS)
    selected = upstream_commits[:MAX_COMMITS]

    analyzed: list[dict[str, Any]] = []
    root = Path.cwd().resolve()

    for item in selected:
        sha = item.get("sha", "")
        if not sha:
            continue
        detail = api_request("GET", f"/repos/{UPSTREAM_REPO}/commits/{sha}")
        files = [
            file_info.get("filename", "")
            for file_info in detail.get("files", [])
            if file_info.get("filename")
        ]
        message = detail.get("commit", {}).get("message", "")
        categories = classify(message, files)
        local_matches = [
            path
            for path in files
            if (root / Path(path)).exists()
        ]
        analyzed.append(
            {
                "sha": sha,
                "url": detail.get(
                    "html_url", f"https://github.com/{UPSTREAM_REPO}/commit/{sha}"
                ),
                "subject": subject(message),
                "files": files,
                "categories": categories,
                "local_matches": local_matches,
                "risk": integration_risk(categories),
                "priority": priority(categories, local_matches, files),
            }
        )

    priority_order = {
        "Review recommended": 0,
        "Potentially useful": 1,
        "Likely platform-specific": 2,
        "General upstream change": 3,
    }
    analyzed.sort(key=lambda item: (priority_order[item["priority"]], item["subject"].lower()))

    report = build_report(
        start=start,
        end=end,
        period_label=period_label,
        commits=analyzed,
        truncated=truncated,
    )

    label = ensure_label()
    existing = find_issue_by_title(issue_title)
    payload: dict[str, Any] = {"title": issue_title, "body": report}
    if label:
        payload["labels"] = [label]

    if existing:
        issue = api_request(
            "PATCH",
            f"/repos/{TARGET_REPO}/issues/{existing['number']}",
            data=payload,
        )
        action = "updated"
    else:
        issue = api_request("POST", f"/repos/{TARGET_REPO}/issues", data=payload)
        action = "created"

    issue_url = issue.get("html_url", "")
    print(f"Upstream review issue {action}: {issue_url}")

    counts = {
        name: sum(1 for item in analyzed if item["priority"] == name)
        for name in (
            "Review recommended",
            "Potentially useful",
            "Likely platform-specific",
            "General upstream change",
        )
    }
    write_step_summary(issue_url, counts)


if __name__ == "__main__":
    main()
