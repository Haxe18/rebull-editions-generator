# Red Bull Editions Scraper

This project contains a Python script that scrapes Red Bull's websites for all available "Editions" worldwide. It collects the data, translates and normalizes flavor names using the Google Gemini API, and compiles everything into a comprehensive `redbull_editions.json` file.

## Features

- **Comprehensive Data Collection:** Scans all country-specific sites provided by the Red Bull API.
- **High-Quality Translation:** Uses the Google Gemini API for context-aware and accurate flavor translations.
- **Data Normalization:** Leverages an internal knowledge base to standardize flavor names (e.g., "Waldbeeren" and "Frutti di Bosco" both become "Forest Berries").
- **Daily Automation:** A GitHub Action runs the script every day to keep the data fresh.
- **Automatic Pull Requests:** If the data changes, a pull request is automatically created with the updated `redbull_editions.json` file.

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
        export GOOGLE_API_KEY="YOUR_API_KEY_HERE"
        ```
    -   **Windows (PowerShell):**
        ```sh
        $env:GOOGLE_API_KEY="YOUR_API_KEY_HERE"
        ```

4.  **Run the script:**
    ```sh
    python redbull_editions_json_generate.py
    ```

## Automation

This repository is configured with a GitHub Action that runs daily. The action executes the scraper script and creates a pull request if any changes to `redbull_editions.json` are detected.

## License

This project is licensed under the WTFPL (Do What The Fuck You Want To Public License) Version 2.

See the [LICENSE](LICENSE) file for details.
