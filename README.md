# Sonarr Plex Analyzer

This script analyzes your Sonarr library, checks Plex watch history, and generates a report of shows that haven't been watched in the past two months.

## Features

- Gets the top 100 series from Sonarr by disk size
- Checks if anyone has watched these series in Plex within a specified time period
- Generates both JSON and HTML reports of unwatched series
- Shows how much disk space could be freed by removing unwatched series

## Requirements

- Python 3.6+
- Sonarr with API access
- Plex Media Server with API access

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/sonarr_plex_analyzer.git
   cd sonarr_plex_analyzer
   ```

2. Install required packages:
   ```
   pip install requests
   ```

3. Configure the application (see Configuration section)

## Configuration

Copy the `config.ini` file and update it with your settings:

```ini
[sonarr]
url = http://localhost:8989
api_key = YOUR_SONARR_API_KEY

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
- `-l, --limit`: Limit to top N series by size (default: 100)
- `-m, --months`: Check if watched in the past N months (default: 2)

Example:
```
python sonarr_plex_analyzer.py --limit 50 --months 3
```

## Output

The script generates two report files in the configured report directory:

1. JSON report: `unwatched_report_YYYY-MM-DD_HH-MM-SS.json`
2. HTML report: `unwatched_report_YYYY-MM-DD_HH-MM-SS.html`

The HTML report provides a user-friendly interface to view the unwatched series, sorted by size.

## License

MIT
