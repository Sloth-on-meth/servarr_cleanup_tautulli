#!/usr/bin/env python3
"""
Servarr Tautulli Analyzer

This script analyzes your Sonarr/Radarr library, checks Tautulli watch history,
and generates a report of shows/movies that haven't been watched in the past two months.
"""

import os
import sys
import json
import time
import re
import datetime
import asyncio
import aiohttp
import requests
import argparse
from typing import Dict, List, Any, Optional, Tuple
from configparser import ConfigParser
from difflib import SequenceMatcher

class ServarrTautulliAnalyzer:
    def __init__(self, config_file: str, mode: str = 'sonarr', verbose: bool = False, debug: bool = False):
        """Initialize the analyzer with configuration from the config file.
        
        Args:
            config_file: Path to the config file
            mode: 'sonarr' or 'radarr'
            verbose: Enable verbose output
            debug: Enable debug output with API responses
        """
        self.config = ConfigParser()
        self.verbose = verbose
        self.debug = debug
        self.session = None  # Will be initialized in async context
        self.mode = mode.lower()
        
        if self.mode not in ['sonarr', 'radarr']:
            print(f"Error: Invalid mode '{mode}'. Must be 'sonarr' or 'radarr'.")
            sys.exit(1)
        
        if not os.path.exists(config_file):
            print(f"Error: Config file {config_file} not found.")
            sys.exit(1)
            
        self.config.read(config_file)
        
        # Sonarr/Radarr configuration
        if self.mode == 'sonarr':
            self.servarr_url = self.config.get('sonarr', 'url')
            self.servarr_api_key = self.config.get('sonarr', 'api_key')
            self.item_count = int(self.config.get('sonarr', 'show_count', fallback=100))
            self.item_type = 'series'
            self.tautulli_library_name = self.config.get('tautulli', 'tv_library_name', fallback='TV Shows')
        else:  # radarr
            self.servarr_url = self.config.get('radarr', 'url')
            self.servarr_api_key = self.config.get('radarr', 'api_key')
            self.item_count = int(self.config.get('radarr', 'movie_count', fallback=100))
            self.item_type = 'movie'
            self.tautulli_library_name = self.config.get('tautulli', 'movie_library_name', fallback='Films')
        
        # Tautulli configuration
        self.tautulli_url = self.config.get('tautulli', 'url')
        self.tautulli_api_key = self.config.get('tautulli', 'api_key')
        
        # Plex configuration (still needed for some operations)
        self.plex_url = self.config.get('plex', 'url')
        self.plex_token = self.config.get('plex', 'token')
        
        # Report configuration
        self.report_path = self.config.get('report', 'path', fallback='./report')
        
        # Create report directory if it doesn't exist
        os.makedirs(self.report_path, exist_ok=True)
        
    async def get_items(self) -> List[Dict[str, Any]]:
        """Get all series/movies from Sonarr/Radarr."""
        await self.setup_session()
        endpoint = "series" if self.mode == "sonarr" else "movie"
        url = f"{self.servarr_url}/api/v3/{endpoint}"
        headers = {"X-Api-Key": self.servarr_api_key}
        
        try:
            async with self.session.get(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                return data
        except aiohttp.ClientError as e:
            print(f"Error connecting to {self.mode.capitalize()}: {e}")
            sys.exit(1)
    
    async def delete_item(self, item_id: int, delete_files: bool = False) -> bool:
        """Delete a series/movie from Sonarr/Radarr."""
        await self.setup_session()
        endpoint = "series" if self.mode == "sonarr" else "movie"
        url = f"{self.servarr_url}/api/v3/{endpoint}/{item_id}"
        headers = {"X-Api-Key": self.servarr_api_key}
        params = {"deleteFiles": str(delete_files).lower()}
        
        try:
            async with self.session.delete(url, headers=headers, params=params) as response:
                if response.status == 200:
                    return True
                else:
                    print(f"Error deleting {self.item_type}: HTTP {response.status}")
                    return False
        except aiohttp.ClientError as e:
            print(f"Error deleting {self.item_type}: {e}")
            return False
    
    async def get_item_size(self, item_id: int) -> int:
        """Get the disk size of a series/movie in bytes."""
        await self.setup_session()
        endpoint = "series" if self.mode == "sonarr" else "movie"
        url = f"{self.servarr_url}/api/v3/{endpoint}/{item_id}"
        headers = {"X-Api-Key": self.servarr_api_key}
        
        try:
            async with self.session.get(url, headers=headers) as response:
                response.raise_for_status()
                item_data = await response.json()
                if self.mode == "sonarr":
                    return item_data.get('statistics', {}).get('sizeOnDisk', 0)
                else:  # radarr
                    return item_data.get('sizeOnDisk', 0)
        except aiohttp.ClientError as e:
            print(f"Error getting {self.item_type} size: {e}")
            return 0
    
    async def get_top_items_by_size(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get the top series/movies by disk size."""
        if limit is None:
            limit = self.item_count
            
        items = await self.get_items()
        
        # Add size information to each item in parallel
        size_tasks = []
        for item in items:
            size_tasks.append(self.get_item_size(item['id']))
        
        # Wait for all size tasks to complete
        sizes = await asyncio.gather(*size_tasks)
        
        # Add sizes to item data
        for i, item in enumerate(items):
            item['sizeOnDisk'] = sizes[i]
        
        # Sort by size (descending) and take the top 'limit' items
        top_items = sorted(items, key=lambda x: x.get('sizeOnDisk', 0), reverse=True)[:limit]
        
        return top_items
    
    def get_plex_library_section_id(self, library_name: str) -> Optional[int]:
        """Get the Plex library section ID for the given library name."""
        url = f"{self.plex_url}/library/sections"
        headers = {"X-Plex-Token": self.plex_token}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            # Parse XML response
            from xml.etree import ElementTree
            root = ElementTree.fromstring(response.content)
            
            for directory in root.findall('.//Directory'):
                if directory.get('title') == library_name:
                    return directory.get('key')
            
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error getting Plex library sections: {e}")
            return None
    
    async def setup_session(self):
        """Set up the aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def close_session(self):
        """Close the aiohttp session."""
        if self.session is not None:
            await self.session.close()
            self.session = None
    
    def debug_request(self, name: str, url: str, params: dict, status_code: int, data: Any) -> None:
        """Debug a request by printing details about it."""
        if self.debug:
            print(f"\n==== DEBUG: {name} ====")
            print(f"URL: {url}")
            print(f"Params: {json.dumps(params, indent=2)}")
            print(f"Status Code: {status_code}")
            try:
                print(f"Response: {json.dumps(data, indent=2)}")
            except:
                print(f"Response (text): {str(data)[:500]}...")
            print("==== END DEBUG ====\n")
    
    async def get_tautulli_library_sections(self) -> List[Dict[str, Any]]:
        """
        Get all library sections from Tautulli.
        """
        try:
            await self.setup_session()
            url = f"{self.tautulli_url}/api/v2"
            params = {
                "apikey": self.tautulli_api_key,
                "cmd": "get_libraries"
            }
            
            async with self.session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                self.debug_request("Get Tautulli Libraries", url, params, response.status, data)
                
                if data.get('response', {}).get('result') != 'success':
                    print(f"Error getting library sections from Tautulli: {data.get('response', {}).get('message')}")
                    return []
                
                return data.get('response', {}).get('data', [])
        except Exception as e:
            print(f"Error getting library sections from Tautulli: {e}")
            return []
    
    async def check_tautulli_watch_history(self, item_title: str, months: int = 2) -> bool:
        """
        Check if anyone has watched the series/movie in the past specified months using Tautulli API.
        Returns True if watched, False if not watched.
        """
        # Calculate the timestamp for X months ago
        now = datetime.datetime.now()
        months_ago = now - datetime.timedelta(days=30 * months)
        unix_timestamp = int(time.mktime(months_ago.timetuple()))
        
        if self.verbose:
            print(f"\nChecking watch history for '{item_title}' in the past {months} months...")
        
        try:
            # First, get all library sections from Tautulli
            library_sections = await self.get_tautulli_library_sections()
            
            # Determine the section type based on mode
            section_type = 'show' if self.mode == 'sonarr' else 'movie'
            
            # Find the appropriate library section using the name from config
            target_section = None
            for section in library_sections:
                if section.get('section_type') == section_type and section.get('section_name') == self.tautulli_library_name:
                    target_section = section
                    break
                    
            # If we didn't find a section with the configured name, fall back to the first section of the right type
            if not target_section:
                if self.verbose or self.debug:
                    print(f"Warning: Could not find library named '{self.tautulli_library_name}', falling back to first {section_type} library")
                for section in library_sections:
                    if section.get('section_type') == section_type:
                        target_section = section
                        break
            
            if not target_section:
                print(f"Error: Could not find {section_type.capitalize()} library section in Tautulli.")
                return False
            
            section_id = target_section.get('section_id')
            
            if self.verbose:
                print(f"Found {section_type.capitalize()} library section: {target_section.get('section_name')} (ID: {section_id})")
            
            # Get watch history for the past X months for this library section
            await self.setup_session()
            history_url = f"{self.tautulli_url}/api/v2"
            params = {
                "apikey": self.tautulli_api_key,
                "cmd": "get_history",
                "section_id": section_id,
                "length": 10000,  # Get a large amount of history
                "order_column": "date",
                "order_dir": "desc",  # Most recent first
                "after": unix_timestamp  # Only get history after our cutoff date
            }
            
            async with self.session.get(history_url, params=params) as history_response:
                history_response.raise_for_status()
                history_data = await history_response.json()
                
                self.debug_request(f"Get Tautulli History (after {datetime.datetime.fromtimestamp(unix_timestamp)})", 
                                  history_url, params, history_response.status, history_data)
                
                if history_data.get('response', {}).get('result') != 'success':
                    print(f"Error getting history from Tautulli: {history_data.get('response', {}).get('message')}")
                    return False
                
                # Get all watched items in the past X months
                watched_items = set()
                watch_counts = {}
                
                for item in history_data.get('response', {}).get('data', {}).get('data', []):
                    # For TV shows, use grandparent_title (show name)
                    # For movies, use title
                    if self.mode == 'sonarr':
                        item_name = item.get('grandparent_title')
                    else:  # radarr
                        item_name = item.get('title')
                        
                    if item_name:
                        item_name_lower = item_name.lower()
                        watched_items.add(item_name_lower)
                        watch_counts[item_name_lower] = watch_counts.get(item_name_lower, 0) + 1
                
                if self.verbose or self.debug:
                    item_type_plural = "shows" if self.mode == "sonarr" else "movies"
                    print(f"Found {len(watched_items)} {item_type_plural} watched in the past {months} months")
                    if len(watched_items) > 0:
                        # Sort by watch count
                        sorted_items = sorted(watch_counts.items(), key=lambda x: x[1], reverse=True)
                        print(f"Top 10 most watched {item_type_plural}:")
                        for item_name, count in sorted_items[:10]:
                            print(f"  - '{item_name}': {count} plays")
                        
                        if self.debug:
                            print(f"\nAll watched {item_type_plural}:")
                            for item_name in sorted(watched_items):
                                print(f"  - '{item_name}'")
                                
                        print("\n")
                
                # Check if our item is in the watched items
                item_title_lower = item_title.lower()
                
                # Direct match
                if item_title_lower in watched_items:
                    if self.verbose:
                        print(f"'{item_title}' was watched recently (exact match)")
                    return True
                
                # Check for partial matches
                for watched_item in watched_items:
                    # Check if the item title is contained in the watched item title
                    if item_title_lower in watched_item:
                        if self.verbose:
                            print(f"'{item_title}' was watched recently via match '{watched_item}'")
                        return True
                    # Check if the watched item title is contained in the item title
                    elif watched_item in item_title_lower:
                        if self.verbose:
                            print(f"'{item_title}' was watched recently via match '{watched_item}'")
                        return True
                    # Special case for Supernatural
                    elif item_title == "Supernatural" and "supernatural" in watched_item:
                        if self.verbose:
                            print(f"'{item_title}' was watched recently via match '{watched_item}'")
                        return True
                
                if self.verbose:
                    print(f"No recent watches found for '{item_title}'")
                return False
        except aiohttp.ClientError as e:
            print(f"Error checking Tautulli watch history for '{item_title}': {e}")
            return False
        except Exception as e:
            print(f"Error processing '{item_title}' in Tautulli: {e}")
            # If there's an error processing this item, we'll assume it's not watched
            # to be safe (so it shows up in the report)
            return False
    
    async def get_unwatched_items(self, limit: int = None, months: int = 2) -> List[Dict[str, Any]]:
        """Get a list of unwatched series/movies."""
        # Use class instance item_count if limit is not provided
        if limit is None:
            limit = self.item_count
            
        item_type_plural = "series" if self.mode == "sonarr" else "movies"
        print(f"Finding top {limit} {item_type_plural} by size that haven't been watched in {months} months...")
        
        # Get top items by size
        top_items = await self.get_top_items_by_size(limit)
        
        # Check watch history for each item in parallel
        watch_tasks = []
        for item in top_items:
            watch_tasks.append(self.check_tautulli_watch_history(item['title'], months))
        
        # Wait for all watch history checks to complete
        watch_results = await asyncio.gather(*watch_tasks)
        
        # Process results
        unwatched_items = []
        for idx, (item, watched) in enumerate(zip(top_items, watch_results)):
            print(f"Checking {idx+1}/{len(top_items)}: {item['title']}")
            if not watched:
                unwatched_items.append({
                    'id': item['id'],
                    'title': item['title'],
                    'size': item['sizeOnDisk'],
                    'size_human': self.human_readable_size(item['sizeOnDisk']),
                    'path': item.get('path', 'Unknown'),
                })
                
        return unwatched_items
        
    async def interactive_cleanup(self, limit: int = None, months: int = 2, delete_files: bool = False) -> None:
        """Interactive terminal UI for deleting unwatched series/movies."""
        unwatched_items = await self.get_unwatched_items(limit, months)
        
        item_type = "series" if self.mode == "sonarr" else "movies"
        item_type_singular = "series" if self.mode == "sonarr" else "movie"
        
        if not unwatched_items:
            print(f"\nNo unwatched {item_type} found!")
            return
            
        print(f"\nFound {len(unwatched_items)} {item_type} that haven't been watched in {months} months.")
        print(f"Total space that could be freed: {self.human_readable_size(sum(item['size'] for item in unwatched_items))}")
        print(f"\nInteractive deletion mode. For each {item_type_singular}, you'll be asked if you want to delete it.")
        print(f"Delete files option is {'ENABLED' if delete_files else 'DISABLED'}")
        print("\nPress Enter to continue or Ctrl+C to abort...")
        input()
        
        deleted_count = 0
        freed_space = 0
        
        for idx, item in enumerate(unwatched_items):
            print(f"\n[{idx+1}/{len(unwatched_items)}] {item['title']}")
            print(f"Size: {item['size_human']}")
            print(f"Path: {item['path']}")
            
            while True:
                response = input(f"Delete this {item_type_singular}? [y/n]: ").lower()
                if response in ['y', 'yes']:
                    print(f"Deleting {item['title']}...")
                    success = await self.delete_item(item['id'], delete_files)
                    if success:
                        print(f"Successfully deleted {item['title']}")
                        deleted_count += 1
                        freed_space += item['size']
                    else:
                        print(f"Failed to delete {item['title']}")
                    break
                elif response in ['n', 'no']:
                    print(f"Skipping {item['title']}")
                    break
                else:
                    print("Please enter 'y' or 'n'")
        
        print(f"\nDeletion complete. Deleted {deleted_count} {item_type}.")
        print(f"Freed space: {self.human_readable_size(freed_space)}")
    
    async def generate_report(self, limit: int = None, months: int = 2) -> None:
        """Generate a report of unwatched series/movies."""
        unwatched_items = await self.get_unwatched_items(limit, months)
        
        item_type = "series" if self.mode == "sonarr" else "movies"
        
        # Generate report
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_file = os.path.join(self.report_path, f"unwatched_{self.mode}_{timestamp}.json")
        
        with open(report_file, 'w') as f:
            json.dump({
                'report_date': datetime.datetime.now().isoformat(),
                'mode': self.mode,
                'unwatched_count': len(unwatched_items),
                'months_threshold': months,
                'unwatched_items': unwatched_items
            }, f, indent=2)
        
        # Generate HTML report
        html_report_file = os.path.join(self.report_path, f"unwatched_{self.mode}_{timestamp}.html")
        self.generate_html_report(unwatched_items, html_report_file, months)
        
        print(f"\nReport generated:")
        print(f"- JSON: {report_file}")
        print(f"- HTML: {html_report_file}")
        
        print(f"\nFound {len(unwatched_items)} {item_type} that haven't been watched in {months} months.")
        print(f"Total space that could be freed: {self.human_readable_size(sum(item['size'] for item in unwatched_items))}")
    
    def generate_html_report(self, unwatched_items: List[Dict], file_path: str, months: int) -> None:
        """Generate an HTML report of unwatched series/movies."""
        total_size = sum(item['size'] for item in unwatched_items)
        
        item_type = "Series" if self.mode == "sonarr" else "Movies"
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unwatched {item_type} Report</title>
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
    <h1>Unwatched {item_type} Report</h1>
    <div class="summary">
        <p>Report generated on: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <p>Found <strong>{len(unwatched_items)}</strong> {item_type.lower()} that haven't been watched in <strong>{months}</strong> months.</p>
        <p>Total space that could be freed: <strong>{self.human_readable_size(total_size)}</strong></p>
    </div>
    <table>
        <tr>
            <th>Title</th>
            <th>Size</th>
            <th>Path</th>
        </tr>"""
        
        # Sort by size (descending)
        sorted_items = sorted(unwatched_items, key=lambda x: x['size'], reverse=True)
        
        for item in sorted_items:
            html += f"""
        <tr>
            <td>{item['title']}</td>
            <td>{item['size_human']}</td>
            <td>{item['path']}</td>
        </tr>"""
        
        html += """
    </table>
</body>
</html>"""
        
        with open(file_path, 'w') as f:
            f.write(html)
    
    @staticmethod
    def human_readable_size(size_bytes: int) -> str:
        """Convert bytes to a human-readable format."""
        if size_bytes == 0:
            return "0B"
        
        size_names = ("B", "KB", "MB", "GB", "TB", "PB")
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.2f} {size_names[i]}"


async def main_async():
    parser = argparse.ArgumentParser(description='Analyze Sonarr/Radarr library and check Tautulli watch history.')
    parser.add_argument('-c', '--config', default='config.ini', help='Path to config file')
    parser.add_argument('-l', '--limit', type=int, default=None, help='Limit to top N items by size')
    parser.add_argument('-m', '--months', type=int, default=2, help='Check if watched in the past N months')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode with detailed API responses')
    parser.add_argument('-t', '--tui', action='store_true', help='Enable terminal UI with interactive deletion')
    parser.add_argument('--delete-files', action='store_true', help='Delete files when removing items (only with --tui)')
    parser.add_argument('--mode', choices=['sonarr', 'radarr'], default='sonarr', help='Select mode: sonarr for TV shows, radarr for movies')
    
    args = parser.parse_args()
    
    analyzer = ServarrTautulliAnalyzer(args.config, mode=args.mode, verbose=args.verbose, debug=args.debug)
    try:
        if args.tui:
            await analyzer.interactive_cleanup(args.limit, args.months, args.delete_files)
        else:
            await analyzer.generate_report(args.limit, args.months)
    finally:
        await analyzer.close_session()

def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
