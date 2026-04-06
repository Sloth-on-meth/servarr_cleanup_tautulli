#!/usr/bin/env python3
"""
Sonarr Cleanup

Checks your Sonarr library against Tautulli watch history and interactively
prompts you to delete series that haven't been watched recently.
"""

import os
import sys
import json
import time
import datetime
import asyncio
import aiohttp
import argparse
from typing import Dict, List, Any, Optional
from configparser import ConfigParser


class SonarrCleanup:
    def __init__(
        self,
        config_file: str,
        verbose: bool = False,
        debug: bool = False,
    ):
        self.verbose = verbose
        self.debug = debug
        self.session = None

        if not os.path.exists(config_file):
            print(f"Error: Config file {config_file} not found.")
            sys.exit(1)

        config = ConfigParser()
        config.read(config_file)

        self.sonarr_url = config.get("sonarr", "url")
        self.sonarr_api_key = config.get("sonarr", "api_key")
        self.tautulli_url = config.get("tautulli", "url")
        self.tautulli_api_key = config.get("tautulli", "api_key")
        self.tautulli_library_name = config.get(
            "tautulli", "tv_library_name", fallback="TV Shows"
        )
        self.report_path = config.get("report", "path", fallback="./reports")
        os.makedirs(self.report_path, exist_ok=True)

    async def setup_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(
                headers={"Accept-Encoding": "gzip, deflate"}
            )

    async def close_session(self):
        if self.session is not None:
            await self.session.close()
            self.session = None

    def _debug(self, name: str, url: str, params: dict, status: int, data: Any):
        if not self.debug:
            return
        print(f"\n==== DEBUG: {name} ====")
        print(f"URL: {url}")
        print(f"Params: {json.dumps(params, indent=2)}")
        print(f"Status: {status}")
        try:
            print(f"Response: {json.dumps(data, indent=2)}")
        except Exception:
            print(f"Response (text): {str(data)[:500]}...")
        print("==== END DEBUG ====\n")

    async def get_series(self) -> List[Dict[str, Any]]:
        """Fetch all series from Sonarr."""
        await self.setup_session()
        url = f"{self.sonarr_url}/api/v3/series"
        try:
            async with self.session.get(
                url, headers={"X-Api-Key": self.sonarr_api_key}
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            print(f"Error connecting to Sonarr: {e}")
            sys.exit(1)

    async def delete_series(self, series_id: int) -> bool:
        """Delete a series and its files from Sonarr."""
        await self.setup_session()
        url = f"{self.sonarr_url}/api/v3/series/{series_id}"
        try:
            async with self.session.delete(
                url,
                headers={"X-Api-Key": self.sonarr_api_key},
                params={"deleteFiles": "true"},
            ) as response:
                if response.status == 200:
                    return True
                print(f"Error deleting series: HTTP {response.status}")
                return False
        except aiohttp.ClientError as e:
            print(f"Error deleting series: {e}")
            return False

    async def get_series_by_size(self, limit: int = None) -> List[Dict[str, Any]]:
        """Return all series sorted by disk size descending, optionally capped at limit."""
        series = await self.get_series()
        for s in series:
            s["sizeOnDisk"] = s.get("statistics", {}).get("sizeOnDisk", 0)
        sorted_series = sorted(series, key=lambda x: x["sizeOnDisk"], reverse=True)
        return sorted_series[:limit] if limit is not None else sorted_series

    async def fetch_recently_watched(self, months: int = 2) -> set:
        """
        Fetch all show titles watched in the past N months from Tautulli.
        Returns a set of lowercase titles.
        """
        await self.setup_session()
        unix_timestamp = int(
            time.mktime(
                (
                    datetime.datetime.now() - datetime.timedelta(days=30 * months)
                ).timetuple()
            )
        )

        # Get library sections
        try:
            async with self.session.get(
                f"{self.tautulli_url}/api/v2",
                params={"apikey": self.tautulli_api_key, "cmd": "get_libraries"},
            ) as response:
                response.raise_for_status()
                data = await response.json()
        except Exception as e:
            print(f"Error getting Tautulli libraries: {e}")
            return set()

        sections = data.get("response", {}).get("data", [])
        target_section = next(
            (
                s for s in sections
                if s.get("section_type") == "show"
                and s.get("section_name") == self.tautulli_library_name
            ),
            None,
        )
        if not target_section:
            if self.verbose or self.debug:
                print(
                    f"Warning: library '{self.tautulli_library_name}' not found, "
                    f"falling back to first show library"
                )
            target_section = next(
                (s for s in sections if s.get("section_type") == "show"), None
            )
        if not target_section:
            print("Error: could not find a TV show library in Tautulli.")
            return set()

        section_id = target_section["section_id"]
        if self.verbose:
            print(
                f"Using Tautulli library: {target_section['section_name']} (ID: {section_id})"
            )

        # Fetch history
        params = {
            "apikey": self.tautulli_api_key,
            "cmd": "get_history",
            "section_id": section_id,
            "length": 10000,
            "order_column": "date",
            "order_dir": "desc",
            "after": unix_timestamp,
        }
        try:
            async with self.session.get(
                f"{self.tautulli_url}/api/v2", params=params
            ) as response:
                response.raise_for_status()
                data = await response.json()
                self._debug(
                    f"Tautulli history after {datetime.datetime.fromtimestamp(unix_timestamp)}",
                    f"{self.tautulli_url}/api/v2",
                    params,
                    response.status,
                    data,
                )
        except aiohttp.ClientError as e:
            print(f"Error fetching Tautulli watch history: {e}")
            return set()

        if data.get("response", {}).get("result") != "success":
            print(f"Tautulli error: {data.get('response', {}).get('message')}")
            return set()

        watched = set()
        watch_counts: Dict[str, int] = {}
        for item in data.get("response", {}).get("data", {}).get("data", []):
            title = item.get("grandparent_title")
            if title:
                t = title.lower()
                watched.add(t)
                watch_counts[t] = watch_counts.get(t, 0) + 1

        if self.verbose or self.debug:
            print(f"Found {len(watched)} shows watched in the past {months} months")
            if watched:
                top = sorted(watch_counts.items(), key=lambda x: x[1], reverse=True)
                print("Top 10 most watched:")
                for name, count in top[:10]:
                    print(f"  - '{name}': {count} plays")
                if self.debug:
                    for name in sorted(watched):
                        print(f"  - '{name}'")
            print()

        return watched

    def _was_watched(self, title: str, watched: set) -> bool:
        t = title.lower()
        if t in watched:
            if self.verbose:
                print(f"'{title}' watched (exact match)")
            return True
        for w in watched:
            if t in w or w in t:
                if self.verbose:
                    print(f"'{title}' watched via match '{w}'")
                return True
        if self.verbose:
            print(f"'{title}' NOT watched")
        return False

    async def get_unwatched(self, limit: int = None, months: int = 2) -> List[Dict]:
        """Return all series not watched in the past N months, sorted by size."""
        scope = f"top {limit}" if limit is not None else "all"
        print(
            f"Checking {scope} series for watch activity in the past {months} months..."
        )

        series_list, watched = await asyncio.gather(
            self.get_series_by_size(limit),
            self.fetch_recently_watched(months),
        )

        unwatched = []
        for idx, s in enumerate(series_list):
            was_watched = self._was_watched(s["title"], watched)
            status = "watched" if was_watched else "NOT watched"
            print(f"[{idx + 1}/{len(series_list)}] {s['title']} — {status}")
            if not was_watched:
                unwatched.append(
                    {
                        "id": s["id"],
                        "title": s["title"],
                        "size": s["sizeOnDisk"],
                        "size_human": self.human_readable_size(s["sizeOnDisk"]),
                        "path": s.get("path", "Unknown"),
                    }
                )
        return unwatched

    async def interactive_cleanup(self, limit: int = None, months: int = 2) -> None:
        """Show unwatched series and interactively prompt to delete each one."""
        unwatched = await self.get_unwatched(limit, months)

        if not unwatched:
            print("\nNo unwatched series found!")
            return

        total_size = sum(s["size"] for s in unwatched)
        print(f"\n{'─' * 60}")
        print(f"  {len(unwatched)} series not watched in the past {months} months")
        print(f"  Reclaimable space: {self.human_readable_size(total_size)}")
        print(f"{'─' * 60}")
        for idx, s in enumerate(unwatched, 1):
            print(f"  {idx:>3}. {s['title']}  ({s['size_human']})")
        print(f"{'─' * 60}\n")

        print("You will now be asked about each one. Files will be permanently deleted.")
        print("Press Enter to start, or Ctrl+C to abort...")
        input()

        deleted_count = 0
        freed_space = 0

        for idx, s in enumerate(unwatched, 1):
            print(f"\n[{idx}/{len(unwatched)}] {s['title']}")
            print(f"  Size: {s['size_human']}")
            print(f"  Path: {s['path']}")

            while True:
                answer = input("  Delete this series? [yes/no]: ").strip().lower()
                if answer in ("yes", "y"):
                    print(f"  Deleting {s['title']}...")
                    if await self.delete_series(s["id"]):
                        print("  Deleted.")
                        deleted_count += 1
                        freed_space += s["size"]
                    else:
                        print(f"  Failed to delete {s['title']}.")
                    break
                elif answer in ("no", "n"):
                    print("  Skipped.")
                    break
                else:
                    print("  Please enter 'yes' or 'no'.")

        print(f"\n{'─' * 60}")
        print(f"  Deleted {deleted_count} series.")
        print(f"  Space freed: {self.human_readable_size(freed_space)}")
        print(f"{'─' * 60}")

    async def generate_report(self, limit: int = None, months: int = 2) -> None:
        """Write JSON and HTML reports without prompting for deletion."""
        unwatched = await self.get_unwatched(limit, months)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        json_path = os.path.join(self.report_path, f"unwatched_sonarr_{timestamp}.json")
        with open(json_path, "w") as f:
            json.dump(
                {
                    "report_date": datetime.datetime.now().isoformat(),
                    "unwatched_count": len(unwatched),
                    "months_threshold": months,
                    "unwatched_series": unwatched,
                },
                f,
                indent=2,
            )

        html_path = os.path.join(self.report_path, f"unwatched_sonarr_{timestamp}.html")
        self._write_html_report(unwatched, html_path, months)

        print(f"\nReport generated:")
        print(f"  JSON: {json_path}")
        print(f"  HTML: {html_path}")
        print(f"\n{len(unwatched)} series not watched in {months} months.")
        print(
            f"Total reclaimable: {self.human_readable_size(sum(s['size'] for s in unwatched))}"
        )

    def _write_html_report(self, unwatched: List[Dict], path: str, months: int) -> None:
        total_size = self.human_readable_size(sum(s["size"] for s in unwatched))
        rows = "\n".join(
            f"        <tr><td>{s['title']}</td><td>{s['size_human']}</td><td>{s['path']}</td></tr>"
            for s in sorted(unwatched, key=lambda x: x["size"], reverse=True)
        )
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Unwatched Series Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .summary {{ margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>Unwatched Series Report</h1>
    <div class="summary">
        <p>Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <p><strong>{len(unwatched)}</strong> series not watched in <strong>{months}</strong> months.</p>
        <p>Reclaimable space: <strong>{total_size}</strong></p>
    </div>
    <table>
        <tr><th>Title</th><th>Size</th><th>Path</th></tr>
{rows}
    </table>
</body>
</html>"""
        with open(path, "w") as f:
            f.write(html)

    @staticmethod
    def human_readable_size(size_bytes: int) -> str:
        if size_bytes == 0:
            return "0B"
        size_names = ("B", "KB", "MB", "GB", "TB", "PB")
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_names[i]}"


async def main_async():
    parser = argparse.ArgumentParser(
        description="Find unwatched Sonarr series via Tautulli and delete them interactively."
    )
    parser.add_argument("-c", "--config", default="config.ini", help="Path to config file")
    parser.add_argument("-l", "--limit", type=int, default=None, help="Only check top N series by size")
    parser.add_argument("-m", "--months", type=int, default=2, help="Inactivity threshold in months (default: 2)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show match details")
    parser.add_argument("-d", "--debug", action="store_true", help="Print full API responses")
    parser.add_argument("--report-only", action="store_true", help="Write JSON/HTML report without deletion prompt")
    args = parser.parse_args()

    cleanup = SonarrCleanup(args.config, verbose=args.verbose, debug=args.debug)
    try:
        if args.report_only:
            await cleanup.generate_report(args.limit, args.months)
        else:
            await cleanup.interactive_cleanup(args.limit, args.months)
    finally:
        await cleanup.close_session()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
