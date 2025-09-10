#!/usr/bin/env python3
"""
Sonarr Tautulli Analyzer

This script analyzes your Sonarr library, checks Tautulli watch history,
and generates a report of shows that haven't been watched in the past two months.
"""

import os
import sys
import json
import time
import re
import datetime
import requests
import argparse
from typing import Dict, List, Any, Optional, Tuple
from configparser import ConfigParser
from difflib import SequenceMatcher

class SonarrTautulliAnalyzer:
    def __init__(self, config_file: str, verbose: bool = False, debug: bool = False):
        """Initialize the analyzer with configuration from the config file."""
        self.config = ConfigParser()
        self.verbose = verbose
        self.debug = debug
        
        if not os.path.exists(config_file):
            print(f"Error: Config file {config_file} not found.")
            sys.exit(1)
            
        self.config.read(config_file)
        
        # Sonarr configuration
        self.sonarr_url = self.config.get('sonarr', 'url')
        self.sonarr_api_key = self.config.get('sonarr', 'api_key')
        self.show_count = int(self.config.get('sonarr', 'show_count', fallback=100))
        
        # Tautulli configuration
        self.tautulli_url = self.config.get('tautulli', 'url')
        self.tautulli_api_key = self.config.get('tautulli', 'api_key')
        self.tautulli_library_name = self.config.get('tautulli', 'library_name', fallback='TV Shows')
        
        # Plex configuration (still needed for some operations)
        self.plex_url = self.config.get('plex', 'url')
        self.plex_token = self.config.get('plex', 'token')
        
        # Report configuration
        self.report_path = self.config.get('report', 'path', fallback='./report')
        
        # Create report directory if it doesn't exist
        os.makedirs(self.report_path, exist_ok=True)
        
    def get_sonarr_series(self) -> List[Dict[str, Any]]:
        """Get all series from Sonarr."""
        url = f"{self.sonarr_url}/api/v3/series"
        headers = {"X-Api-Key": self.sonarr_api_key}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error connecting to Sonarr: {e}")
            sys.exit(1)
    
    def get_series_size(self, series_id: int) -> int:
        """Get the disk size of a series in bytes."""
        url = f"{self.sonarr_url}/api/v3/series/{series_id}"
        headers = {"X-Api-Key": self.sonarr_api_key}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            series_data = response.json()
            return series_data.get('statistics', {}).get('sizeOnDisk', 0)
        except requests.exceptions.RequestException as e:
            print(f"Error getting series size: {e}")
            return 0
    
    def get_top_series_by_size(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get the top series by disk size."""
        series = self.get_sonarr_series()
        
        # Add size information to each series
        for s in series:
            s['sizeOnDisk'] = self.get_series_size(s['id'])
        
        # Sort by size (descending) and take the top 'limit' items
        top_series = sorted(series, key=lambda x: x.get('sizeOnDisk', 0), reverse=True)[:limit]
        
        return top_series
    
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
    
    def debug_request(self, name: str, url: str, params: dict, response: requests.Response) -> None:
        """Debug a request by printing details about it."""
        if self.debug:
            print(f"\n==== DEBUG: {name} ====")
            print(f"URL: {url}")
            print(f"Params: {json.dumps(params, indent=2)}")
            print(f"Status Code: {response.status_code}")
            try:
                data = response.json()
                print(f"Response: {json.dumps(data, indent=2)}")
            except:
                print(f"Response (text): {response.text[:500]}...")
            print("==== END DEBUG ====\n")
    
    def get_tautulli_library_sections(self) -> List[Dict[str, Any]]:
        """
        Get all library sections from Tautulli.
        """
        try:
            url = f"{self.tautulli_url}/api/v2"
            params = {
                "apikey": self.tautulli_api_key,
                "cmd": "get_libraries"
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            self.debug_request("Get Tautulli Libraries", url, params, response)
            
            data = response.json()
            
            if data.get('response', {}).get('result') != 'success':
                print(f"Error getting library sections from Tautulli: {data.get('response', {}).get('message')}")
                return []
            
            return data.get('response', {}).get('data', [])
        except Exception as e:
            print(f"Error getting library sections from Tautulli: {e}")
            return []
    
    def check_tautulli_watch_history(self, series_title: str, months: int = 2) -> bool:
        """
        Check if anyone has watched the series in the past specified months using Tautulli API.
        Returns True if watched, False if not watched.
        """
        # Calculate the timestamp for X months ago
        now = datetime.datetime.now()
        months_ago = now - datetime.timedelta(days=30 * months)
        unix_timestamp = int(time.mktime(months_ago.timetuple()))
        
        if self.verbose:
            print(f"\nChecking watch history for '{series_title}' in the past {months} months...")
        
        try:
            # First, get all library sections from Tautulli
            library_sections = self.get_tautulli_library_sections()
            
            # Find the TV Shows library section using the name from config
            tv_section = None
            for section in library_sections:
                if section.get('section_type') == 'show' and section.get('section_name') == self.tautulli_library_name:
                    tv_section = section
                    break
                    
            # If we didn't find a section with the configured name, fall back to the first show section
            if not tv_section:
                if self.verbose or self.debug:
                    print(f"Warning: Could not find library named '{self.tautulli_library_name}', falling back to first show library")
                for section in library_sections:
                    if section.get('section_type') == 'show':
                        tv_section = section
                        break
            
            if not tv_section:
                print("Error: Could not find TV Shows library section in Tautulli.")
                return False
            
            section_id = tv_section.get('section_id')
            
            if self.verbose:
                print(f"Found TV Shows library section: {tv_section.get('section_name')} (ID: {section_id})")
            
            # Get watch history for the past X months for this library section
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
            
            history_response = requests.get(history_url, params=params)
            history_response.raise_for_status()
            
            self.debug_request(f"Get Tautulli History (after {datetime.datetime.fromtimestamp(unix_timestamp)})", 
                              history_url, params, history_response)
            
            history_data = history_response.json()
            
            if history_data.get('response', {}).get('result') != 'success':
                print(f"Error getting history from Tautulli: {history_data.get('response', {}).get('message')}")
                return False
            
            # Get all watched shows in the past X months
            watched_shows = set()
            watch_counts = {}
            
            for item in history_data.get('response', {}).get('data', {}).get('data', []):
                # Get the grandparent title (show name)
                show_title = item.get('grandparent_title')
                if show_title:
                    show_title_lower = show_title.lower()
                    watched_shows.add(show_title_lower)
                    watch_counts[show_title_lower] = watch_counts.get(show_title_lower, 0) + 1
            
            if self.verbose or self.debug:
                print(f"Found {len(watched_shows)} shows watched in the past {months} months")
                if len(watched_shows) > 0:
                    # Sort by watch count
                    sorted_shows = sorted(watch_counts.items(), key=lambda x: x[1], reverse=True)
                    print(f"Top 10 most watched shows:")
                    for show, count in sorted_shows[:10]:
                        print(f"  - '{show}': {count} plays")
                    
                    if self.debug:
                        print("\nAll watched shows:")
                        for show in sorted(watched_shows):
                            print(f"  - '{show}'")
                            
                    print("\n")
            
            # Check if our series is in the watched shows
            series_title_lower = series_title.lower()
            
            # Direct match
            if series_title_lower in watched_shows:
                if self.verbose:
                    print(f"'{series_title}' was watched recently (exact match)")
                return True
            
            # Check for partial matches
            for watched_show in watched_shows:
                # Check if the series title is contained in the watched show title
                if series_title_lower in watched_show:
                    if self.verbose:
                        print(f"'{series_title}' was watched recently via match '{watched_show}'")
                    return True
                # Check if the watched show title is contained in the series title
                elif watched_show in series_title_lower:
                    if self.verbose:
                        print(f"'{series_title}' was watched recently via match '{watched_show}'")
                    return True
                # Special case for Supernatural
                elif series_title == "Supernatural" and "supernatural" in watched_show:
                    if self.verbose:
                        print(f"'{series_title}' was watched recently via match '{watched_show}'")
                    return True
            
            if self.verbose:
                print(f"No recent watches found for '{series_title}'")
            return False
        except requests.exceptions.RequestException as e:
            print(f"Error checking Tautulli watch history for '{series_title}': {e}")
            return False
        except Exception as e:
            print(f"Error processing '{series_title}' in Tautulli: {e}")
            # If there's an error processing this show, we'll assume it's not watched
            # to be safe (so it shows up in the report)
            return False
    
    def generate_report(self, limit: int = None, months: int = 2) -> None:
        """Generate a report of unwatched series."""
        # Use class instance show_count if limit is not provided
        if limit is None:
            limit = self.show_count
            
        print(f"Generating report of top {limit} series by size that haven't been watched in {months} months...")
        
        # Get top series by size
        top_series = self.get_top_series_by_size(limit)
        
        # Check watch history for each series
        unwatched_series = []
        for idx, series in enumerate(top_series):
            print(f"Checking {idx+1}/{len(top_series)}: {series['title']}")
            
            watched = self.check_tautulli_watch_history(series['title'], months)
            if not watched:
                unwatched_series.append({
                    'title': series['title'],
                    'size': series['sizeOnDisk'],
                    'size_human': self.human_readable_size(series['sizeOnDisk']),
                    'path': series.get('path', 'Unknown'),
                })
        
        # Generate report
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_file = os.path.join(self.report_path, f"unwatched_report_{timestamp}.json")
        
        with open(report_file, 'w') as f:
            json.dump({
                'report_date': datetime.datetime.now().isoformat(),
                'total_series_checked': len(top_series),
                'unwatched_series_count': len(unwatched_series),
                'months_threshold': months,
                'unwatched_series': unwatched_series
            }, f, indent=2)
        
        # Generate HTML report
        html_report_file = os.path.join(self.report_path, f"unwatched_report_{timestamp}.html")
        self.generate_html_report(unwatched_series, html_report_file, months)
        
        print(f"\nReport generated:")
        print(f"- JSON: {report_file}")
        print(f"- HTML: {html_report_file}")
        print(f"\nFound {len(unwatched_series)} series that haven't been watched in {months} months.")
        
        # Print total space that could be freed
        total_size = sum(series['size'] for series in unwatched_series)
        print(f"Total space that could be freed: {self.human_readable_size(total_size)}")
    
    def generate_html_report(self, unwatched_series: List[Dict], file_path: str, months: int) -> None:
        """Generate an HTML report of unwatched series."""
        total_size = sum(series['size'] for series in unwatched_series)
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unwatched Sonarr Series Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            color: #333;
        }}
        h1, h2 {{
            color: #2c3e50;
        }}
        .summary {{
            background-color: #f8f9fa;
            border-left: 4px solid #4CAF50;
            padding: 15px;
            margin-bottom: 20px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin-top: 20px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
        }}
        tr:nth-child(even) {{
            background-color: #f2f2f2;
        }}
        tr:hover {{
            background-color: #ddd;
        }}
        .timestamp {{
            color: #777;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <h1>Unwatched Sonarr Series Report</h1>
    <p class="timestamp">Generated on {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <p>Found <strong>{len(unwatched_series)}</strong> series that haven't been watched in the past {months} months.</p>
        <p>Total space that could be freed: <strong>{self.human_readable_size(total_size)}</strong></p>
    </div>
    
    <h2>Unwatched Series</h2>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Series Title</th>
                <th>Size</th>
                <th>Path</th>
            </tr>
        </thead>
        <tbody>
"""
        
        # Add rows for each unwatched series
        for idx, series in enumerate(sorted(unwatched_series, key=lambda x: x['size'], reverse=True)):
            html += f"""
            <tr>
                <td>{idx + 1}</td>
                <td>{series['title']}</td>
                <td>{series['size_human']}</td>
                <td>{series['path']}</td>
            </tr>"""
        
        html += """
        </tbody>
    </table>
</body>
</html>
"""
        
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


def main():
    parser = argparse.ArgumentParser(description='Analyze Sonarr library and check Tautulli watch history.')
    parser.add_argument('-c', '--config', default='config.ini', help='Path to config file')
    parser.add_argument('-l', '--limit', type=int, default=None, help='Limit to top N series by size')
    parser.add_argument('-m', '--months', type=int, default=2, help='Check if watched in the past N months')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode with detailed API responses')
    
    args = parser.parse_args()
    
    analyzer = SonarrTautulliAnalyzer(args.config, verbose=args.verbose, debug=args.debug)
    analyzer.generate_report(args.limit, args.months)


if __name__ == "__main__":
    main()
