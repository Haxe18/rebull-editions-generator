# Red Bull Editions Generator

This project contains a Python script that fetches Red Bull's "Editions" (flavored energy drinks) from all available countries worldwide. It collects raw data from Red Bull's APIs, applies manual corrections, and uses Google Gemini AI to normalize and translate flavor names into a comprehensive `redbull_editions.json` file.

## Features

- **🌍 Global Data Collection:** Fetches data from Red Bull APIs for all available countries
- **🤖 AI-Powered Normalization:** Uses Google Gemini to translate and standardize flavor names
- **🔧 Manual Data Corrections:** Applies fixes for known API data issues
- **📊 Smart Change Detection:** Only processes data when changes are detected
- **⚡ Efficient Processing:** Saves API costs by skipping unchanged data
- **🔄 Automated Workflow:** GitHub Actions run daily with manual trigger support
- **📝 Detailed Changelog:** Tracks all changes and applied fixes

## Local Setup and Execution

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/Haxe18/rebull-editions-generator
    cd rebull-editions-generator
    ```

2.  **Install dependencies** (using a virtual environment is recommended):
    ```sh
    pip install -r requirements.txt
    ```

3.  **Set up the API Key:**
    The script requires a Google Gemini API key. To keep it secure, store it as an environment variable.

    -   **Linux/macOS:**
        ```sh
        export GEMINI_API_KEY="YOUR_API_KEY_HERE"
        ```
    -   **Windows (PowerShell):**
        ```sh
        $env:GEMINI_API_KEY="YOUR_API_KEY_HERE"
        ```

4.  **Run the script:**
    ```sh
    python redbull_editions_json_generate.py
    ```

    **Available command line options:**
    - `-v, --verbose`: Enable verbose (DEBUG) logging output
    - `--skip-external-fetch`: Skip external data fetching and use only locally available data from `dist/redbull_editions_raw.previous.json`
    - `--force`: Force processing even when no changes are detected

    **Examples:**
    ```sh
    # Normal run with external data fetching
    python redbull_editions_json_generate.py

    # Run with verbose logging
    python redbull_editions_json_generate.py -v

    # Skip external fetching, use local data only
    python redbull_editions_json_generate.py --skip-external-fetch

    # Force processing despite no changes
    python redbull_editions_json_generate.py --force

    # Combine multiple options
    python redbull_editions_json_generate.py -v --skip-external-fetch --force
    ```

## Output Files

The script generates several files in the `dist/` directory:

- **`redbull_editions.json`** - Final normalized data with all editions
- **`redbull_editions_raw.json`** - Raw data from Red Bull APIs
- **`redbull_editions_raw.previous.json`** - Previous run's raw data for comparison
- **`changelog.md`** - Detailed changelog of all changes and fixes applied

## Automation

This repository is configured with a GitHub Action that runs daily at 5:11 UTC. The action:

- **Scheduled Runs:** Execute normally and only process data when changes are detected
- **Manual Triggers:** Run with `--force` flag to process data regardless of changes
- **Automatic Releases:** Create GitHub releases with changelog when data is updated
- **Smart Commit:** Only commit changes when the `dist/` folder has been modified

### Manual Trigger
You can manually trigger the workflow from the GitHub Actions tab. Manual runs will force processing even if no changes are detected, useful for testing or immediate updates.

## License

This project is licensed under the WTFPL (Do What The Fuck You Want To Public License) Version 2.

See the [LICENSE](LICENSE) file for details.
