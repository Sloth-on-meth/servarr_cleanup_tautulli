# Sonarr Tautulli Analyzer

This script analyzes your Sonarr library, checks Tautulli watch history, and generates a report of shows that haven't been watched in the past two months.

## Features

- Gets the top 100 series from Sonarr by disk size
- Checks if anyone has watched these series in Tautulli within a specified time period
- Generates both JSON and HTML reports of unwatched series
- Shows how much disk space could be freed by removing unwatched series

## Requirements

- Python 3.6+
- Sonarr with API access
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

[tautulli]
url = http://localhost:8181
api_key = YOUR_TAUTULLI_API_KEY
library_name = TV Shows  # Name of your TV Shows library in Tautulli

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
- `-l, --limit`: Limit to top N series by size (default: from config)
- `-m, --months`: Check if watched in the past N months (default: 2)
- `-v, --verbose`: Enable verbose output
- `-d, --debug`: Enable debug mode with detailed API responses
- `-t, --tui`: Enable terminal UI with interactive deletion
- `--delete-files`: Delete files when removing series (only with --tui)

Examples:
```
# Generate a report of top 50 unwatched series in the past 3 months
python sonarr_plex_analyzer.py --limit 50 --months 3

# Interactive terminal UI to delete unwatched series (keeping files)
python sonarr_plex_analyzer.py --tui

# Interactive terminal UI to delete unwatched series AND their files
python sonarr_plex_analyzer.py --tui --delete-files
```

### Interactive Terminal UI

When using the `--tui` option, the script will:

1. Find all unwatched series based on your criteria
2. Show each series one by one with its size and path
3. Ask if you want to delete it (y/n)
4. If you answer yes, it will delete the series from Sonarr
5. If `--delete-files` is specified, it will also delete the files from disk

This is a convenient way to clean up your library interactively.

## Output

The script generates two report files in the configured report directory:

1. JSON report: `unwatched_report_YYYY-MM-DD_HH-MM-SS.json`
2. HTML report: `unwatched_report_YYYY-MM-DD_HH-MM-SS.html`

The HTML report provides a user-friendly interface to view the unwatched series, sorted by size.

## License

MIT
