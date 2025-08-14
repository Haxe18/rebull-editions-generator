# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Red Bull Editions data generator that collects product information from Red Bull's APIs worldwide and uses Google Gemini AI to normalize and translate the data into a comprehensive JSON file.

## Key Commands

### Running the Script

```bash
# Normal run - fetches external data and processes if changes detected
python redbull_editions_json_generate.py

# Run with verbose/debug logging
python redbull_editions_json_generate.py -v

# Skip external API calls - use local cached data only
python redbull_editions_json_generate.py --skip-external-fetch

# Force processing even if no changes detected
python redbull_editions_json_generate.py --force

# Combine options
python redbull_editions_json_generate.py -v --skip-external-fetch --force
```

### Setup

```bash
# Install dependencies (use virtual environment recommended)
pip install -r requirements.txt

# Set Gemini API key (required)
export GEMINI_API_KEY="your_api_key_here"  # Linux/macOS
$env:GEMINI_API_KEY="your_api_key_here"    # Windows PowerShell
```

## Architecture

### Two-Stage Processing Pipeline

1. **Raw Data Collection Stage**
   - Fetches locale list from Red Bull's header API
   - For each locale, fetches product editions and their GraphQL details
   - Applies manual data fixes for known API issues (defined in `DATA_FIXES` array)
   - Saves to `dist/redbull_editions_raw.json`

2. **AI Normalization Stage** (only runs if changes detected)
   - Compares new raw data with previous run (`dist/redbull_editions_raw.previous.json`)
   - If changes found, sends entire dataset to Gemini AI
   - AI translates and normalizes flavor names based on rules in `gemini_prompt.txt`
   - Outputs final data to `dist/redbull_editions.json`

### Core Components

- **RedBullGenerator class** (`redbull_editions_json_generate.py`): Main orchestrator with comprehensive PyCharm-style docstrings
  - `fetch_all_raw_data()`: Collects data from Red Bull APIs with intelligent locale deduplication
  - `compare_raw_data_and_generate_changelog()`: Detects changes (static method)
  - `normalize_with_gemini()`: AI processing step with retry logic
  - `_apply_data_fixes()`: Applies manual data corrections
  - `_rehydrate_ai_response()`: Post-processing and cleanup (punctuation, field naming fixes)

- **External APIs Used**:
  - Red Bull Header API: `https://www.redbull.com/v3/api/custom/header/v2`
  - Red Bull GraphQL API: `https://www.redbull.com/v3/api/graphql/v1/`

- **Output Files** (all in `dist/`):
  - `redbull_editions.json`: Final normalized data
  - `redbull_editions_raw.json`: Current raw API data
  - `redbull_editions_raw.previous.json`: Previous run's raw data
  - `changelog.md`: Generated changelog of changes

### GitHub Actions Automation

- Runs daily at 5:11 UTC via `.github/workflows/daily_update.yml`
- Manual triggers run with `--force` flag
- Automatically commits changes and creates releases when data updates

## Important Context

- The script includes manual data corrections in the `DATA_FIXES` array for known API issues
- Change detection prevents unnecessary API costs by skipping Gemini processing when data hasn't changed
- The Gemini prompt (`gemini_prompt.txt`) contains detailed instructions for AI normalization
- Uses `gemini-2.5-flash-lite` model for cost efficiency
- Request delays are implemented to avoid rate limiting
- Caribbean region keeps all locales (English and Spanish) while other regions deduplicate
- Post-processing includes automatic field renaming ('description' → 'flavor_description') and punctuation cleanup