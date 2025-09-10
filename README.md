# Servarr Tautulli Analyzer

A script to analyze your Sonarr library, check Tautulli watch history, and generate a report of shows that haven't been watched in the past two months.

> **Note:** Radarr functionality is implemented but not yet working. Currently, only Sonarr (TV shows) is supported.



## Features

- Gets the top series from Sonarr by disk size
- Gets the top movies from Radarr by disk size
- Checks if anyone has watched these series/movies in Tautulli within a specified time period
- Generates both JSON and HTML reports of unwatched content
- Shows how much disk space could be freed by removing unwatched content
- Interactive terminal UI for deleting unwatched content
- Asynchronous operation for faster processing

## Requirements.

- Python 3.6+
- Sonarr and/or Radarr with API access
- Tautulli with API access
- Plex Media Server

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/Sloth-on-meth/servarr_cleanup_tautulli.git
   cd servarr_cleanup_tautulli
   ```

2. Install required packages:
   ```
   pip install -r requirements.txt
   ```

3. Configure the application (see Configuration section)

## Configuration

Copy the `config.sample.ini` to `config.ini` and update it with your settings:

```ini
[sonarr]
url = http://localhost:8989
api_key = YOUR_SONARR_API_KEY
show_count = 100  # Number of shows to check, sorted by size

[radarr]
url = http://localhost:7878
api_key = YOUR_RADARR_API_KEY
movie_count = 100  # Number of movies to check, sorted by size

[tautulli]
url = http://localhost:8181
api_key = YOUR_TAUTULLI_API_KEY
tv_library_name = TV Shows  # Name of your TV Shows library in Tautulli
movie_library_name = Films  # Name of your Movies library in Tautulli

[plex]
url = http://localhost:32400
token = YOUR_PLEX_TOKEN

[report]
path = ./reports
```

### Getting your Sonarr API key

1. Open Sonarr web interface
2. Go to Settings > General
3. Find the API Key section

### Getting your Tautulli API key

1. Open Tautulli web interface
2. Go to Settings > Web Interface
3. Find the API Key section, or enable API if not already enabled
4. Copy the API key

### Getting your Plex token

1. Log in to Plex web app
2. Play any video
3. While playing, press Ctrl+Shift+I to open developer tools
4. Go to Network tab
5. Look for any API request (like `/library/metadata/`)
6. Find the `X-Plex-Token` parameter in the request URL

## Usage

Run the script with:

```
python sonarr_plex_analyzer.py
```

### Command-line options

- `-c, --config`: Path to config file (default: `config.ini`)
- `-l, --limit`: Limit to top N items by size (default: from config)
- `-m, --months`: Check if watched in the past N months (default: 2)
- `-v, --verbose`: Enable verbose output
- `-d, --debug`: Enable debug mode with detailed API responses
- `-t, --tui`: Enable terminal UI with interactive deletion
- `--delete-files`: Delete files when removing items (only with --tui)
- `--mode`: Select mode: `sonarr` for TV shows, `radarr` for movies (default: sonarr)

Examples:
```
# Generate a report of top 50 unwatched TV shows in the past 3 months
python sonarr_plex_analyzer.py --limit 50 --months 3 --mode sonarr

# Generate a report of unwatched movies in the past 6 months
python sonarr_plex_analyzer.py --months 6 --mode radarr

# Interactive terminal UI to delete unwatched TV shows (keeping files)
python sonarr_plex_analyzer.py --tui --mode sonarr

# Interactive terminal UI to delete unwatched movies AND their files
python sonarr_plex_analyzer.py --tui --delete-files --mode radarr
```

### Interactive Terminal UI

When using the `--tui` option, the script will:

1. Find all unwatched series/movies based on your criteria
2. Show each item one by one with its size and path
3. Ask if you want to delete it (y/n)
4. If you answer yes, it will delete the item from Sonarr/Radarr
5. If `--delete-files` is specified, it will also delete the files from disk

This is a convenient way to clean up your library interactively.

## Output

The script generates two report files in the configured report directory:

1. JSON report: `unwatched_report_YYYY-MM-DD_HH-MM-SS.json`
2. HTML report: `unwatched_report_YYYY-MM-DD_HH-MM-SS.html`

The HTML report provides a user-friendly interface to view the unwatched series, sorted by size.

## License

MIT
