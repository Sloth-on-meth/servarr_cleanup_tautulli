# Servarr Tautulli Analyzer

Checks your Sonarr library against Tautulli watch history, lists every show that hasn't been watched recently, and lets you delete them one by one — including their files on disk.

> **Note:** Radarr support is not yet working. Only Sonarr (TV shows) is currently supported.

## How it works

1. Fetches all series from Sonarr and your recent watch history from Tautulli (in parallel)
2. Checks every series against the watch history
3. Prints a numbered list of unwatched shows with sizes and total reclaimable space
4. Asks you whether to delete each one — if you say yes, the series and its files are permanently removed via the Sonarr API

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

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Copy and edit the config file:
   ```
   cp config.sample.ini config.ini
   ```

## Configuration

```ini
[sonarr]
url = http://localhost:8989
api_key = YOUR_SONARR_API_KEY

[tautulli]
url = http://localhost:8181
api_key = YOUR_TAUTULLI_API_KEY
tv_library_name = TV Shows  # Must match the library name in Tautulli exactly

[plex]
url = http://localhost:32400
token = YOUR_PLEX_TOKEN

[report]
path = ./reports
```

### Getting your API keys

**Sonarr:** Settings → General → API Key

**Tautulli:** Settings → Web Interface → API Key

**Plex token:** Play any video in the Plex web app, open dev tools (Ctrl+Shift+I), go to the Network tab, and find `X-Plex-Token` in any `/library/` request URL.

## Usage

```
python servarr_diskspace_analyzer.py
```

By default the script checks **all** series and prompts you to delete each unwatched one.

### Options

| Flag | Description |
|------|-------------|
| `-c, --config` | Path to config file (default: `config.ini`) |
| `-l, --limit` | Only check the top N series by size |
| `-m, --months` | Inactivity threshold in months (default: `2`) |
| `-v, --verbose` | Show match details for each title |
| `-d, --debug` | Print full API responses |
| `--report-only` | Write JSON/HTML reports without the deletion prompt |

### Examples

```bash
# Check all shows, prompt to delete (default)
python servarr_diskspace_analyzer.py

# Only look at the 50 largest shows, use a 3-month threshold
python servarr_diskspace_analyzer.py --limit 50 --months 3

# Just generate the report files, no deletion prompts
python servarr_diskspace_analyzer.py --report-only
```

## Report files

When run with `--report-only`, two files are written to the configured report directory:

- `unwatched_sonarr_YYYY-MM-DD_HH-MM-SS.json`
- `unwatched_sonarr_YYYY-MM-DD_HH-MM-SS.html`

## License

MIT
