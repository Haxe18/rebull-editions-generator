# Red Bull Editions Generator - Project Context

## Project Overview
This project scrapes Red Bull's global websites to collect all available "Editions" (flavored energy drinks) worldwide. It uses a two-stage process:

1. **Raw Data Collection**: Fetches product data from Red Bull APIs for all countries
2. **AI Normalization**: Uses Google Gemini API to translate and standardize flavor names

## Key Files
- `redbull_editions_json_generate.py` - Main script with RedBullGenerator class
- `gemini_prompt.txt` - AI prompt for data normalization
- `dist/` - Output directory for JSON files
- `requirements.txt` - Python dependencies

## Architecture
- **RedBullGenerator class**: Main orchestrator
- **External APIs**: Red Bull language API + GraphQL API
- **AI Processing**: Google Gemini for translation/normalization
- **File Management**: Raw data → AI processing → Final JSON

## Data Flow
1. Fetch locale list from Red Bull API
2. For each locale: Get editions → Fetch GraphQL details
3. Save raw data to `dist/redbull_editions_raw.json`
4. Compare with previous run for changes
5. If changes detected: Send to Gemini for normalization
6. Save final data to `dist/redbull_editions.json`

## Command Line Options
- `--skip-external-fetch`: Use local data only (from `.previous.json`)
- `-v, --verbose`: Enable debug logging

## Environment Variables
- `GEMINI_API_KEY`: Required for AI processing 