# scraper_goog

Google Maps scraping scripts for collecting places and reviews across multiple cities using Playwright and asyncio.

## What this repo contains

- **`multi_city.py`**: Main multi-city scraper with city selection menu.
- **`dubai.py`**: Dubai-focused scraper setup.
- **`scraper_final.py` / `final_scarper.py` / `enchanced.py`**: Experimental and advanced scraper variants.
- **`proxies.txt`**: Proxy list (`IP:PORT`, one per line).
- **`search_history_*.txt`**: Query history files used to skip already-processed searches.

## Features

- Parallel scraping with multiple scraper workers
- Proxy support
- Query-history tracking to avoid duplicate runs
- CSV output with deduplication
- Optional review extraction from Google Maps
- Multiple predefined cities and neighborhoods

## Requirements

- Python 3.10+
- Google Chrome
- Python packages:
  - `playwright`
  - `pandas`
  - `aiofiles`
  - `psutil`

Install dependencies:

```bash
pip install playwright pandas aiofiles psutil
python -m playwright install chromium
```

## Configuration

Most options are constants at the top of each script, for example:

- `NUM_PARALLEL_SCRAPERS`
- `SKIP_REVIEWS`
- `MAX_PLACES_PER_QUERY`
- break timing and retry settings
- `CITIES` and category definitions

Update **`proxies.txt`** with valid proxies before running.

## Usage

Run the multi-city scraper:

```bash
python /home/runner/work/scraper_goog/scraper_goog/multi_city.py
```

Run the Dubai-only scraper:

```bash
python /home/runner/work/scraper_goog/scraper_goog/dubai.py
```

## Output

- Per-city CSV files (example: `bangkok_final.csv`, `dubai_final.csv`)
- Query history files (`search_history_<city>.txt`)

## Notes

- Scraping Google Maps may trigger rate limits or anti-bot checks.
- Use responsibly and comply with Google terms and local laws.
- Review script-specific settings before long runs.
