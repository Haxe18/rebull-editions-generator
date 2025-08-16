#!/usr/bin/env python3
"""
This script builds a comprehensive JSON file of Red Bull editions from around the world.

It follows a new, robust, two-stage process:
1.  Raw Data Collection & Comparison:
    - Fetches all product data directly from Red Bull's APIs for every available country.
    - Saves this raw, unprocessed data into a `redbull_editions_raw.json` file.
    - Compares this new raw data with the previous run's raw data (`redbull_editions_raw.previous.json`).

2.  AI-Powered Normalization (Conditional):
    - If and only if changes are detected, the script proceeds.
    - The entire raw JSON data is sent to the Google Gemini API in a single request.
    - Gemini is instructed to translate, normalize, and consolidate all edition names and flavors
      based on a set of rules, using English-language locales (GB, US, INT) as a reference.
    - The final, clean data is saved to `redbull_editions.json`.
    - The new raw data is then saved as the reference for the next run.
    - If no changes are detected, the script exits early to save resources and API costs.
"""
import sys
import os
import json
import logging
from random import randint
import time
import argparse
import copy
import re
from typing import Dict, Any, Optional, Tuple, List

import unicodedata
import requests
from google import genai
from google.genai.errors import APIError as google_exceptions
from google.genai import types

# --- Configuration ---
GEMINI_MODEL_TO_USE = 'gemini-2.5-flash-lite'
OUTPUT_DIR = "dist"
RAW_JSON_FILE = os.path.join(OUTPUT_DIR, "redbull_editions_raw.json")
PREVIOUS_RAW_JSON_FILE = os.path.join(OUTPUT_DIR, "redbull_editions_raw.previous.json")
FINAL_JSON_FILE = os.path.join(OUTPUT_DIR, "redbull_editions.json")
CHANGELOG_FILE = os.path.join(OUTPUT_DIR, "changelog.md")
PROMPT_FILE = "gemini_prompt.txt"
REQUEST_DELAY_FROM = 1
REQUEST_DELAY_TO = 3
LANG_API_URL = 'https://www.redbull.com/v3/api/custom/header/v2?locale={locale}'
GRAPHQL_URL = 'https://www.redbull.com/v3/api/graphql/v1/?rb3ResourceId={graphql_id}&rb3Schema=v1:assetInfo'
FLAG_BASE_URL = 'https://rbds-static.redbull.com/@cosmos/foundation/latest/flags/cosmos-flag-{flag_code}.svg'

# --- Data Fixes Configuration ---
# Manual corrections to apply before AI processing
# Format: {"id": "product_id", "field": "field_name", "search": "text_to_find", "replace": "text_to_replace"}
# Manual fixes to apply before AI processing, Data broken/wrong from the API
DATA_FIXES = [
    {
        "id": "f900c5b7-d33e-4a8e-a186-5cee5bd291a1:en-MEA",
        "field": "flavor_description",
        "search": "Summer Edition",
        "replace": "The Apricot Edition"
    },
    {
        "id": "ac367322-24c1-44a9-ad4a-1e022f9347d6:fi-FI",
        "field": "flavor",
        "search": "Dragon fruit",
        "replace": "Curuba-Elderflower"
    },
    {
        "id": "22f260ac-2e6a-4082-9469-3bba2de2b523:hr-HR",
        "field": "flavor_description",
        "search": "merale",
        "replace": "Juneberry"
    },
    {
        "id": "f78cf50c-38e3-423a-ba25-045cbfb7eb50:ja-JP",
        "field": "flavor",
        "search": "Curuba Elderflower",
        "replace": "Muscat"
    },
    {
        "id": "f900c5b7-d33e-4a8e-a186-5cee5bd291a1:pt-BR",
        "field": "flavor",
        "search": "apricot",
        "replace": "Peach"
    },
    {
        "id": "5436c81e-e0b1-4f5f-9ae2-85046d74ccad:pt-PT",
        "field": "flavor",
        "search": "ZERO CALORIAS",
        "replace": "Zero Sugar"
    },
    {
        "id": "add1ea51-ee5f-4c6c-a2d2-efd59791e8f8:pt-PT",
        "field": "flavor",
        "search": "Maracuja-banana",
        "replace": "White Peach"
    },
    {
        "id": "77e43776-f55c-4250-a143-f126e7b543ed:en-SE",
        "field": "flavor",
        "search": "Grapefruit-Woodruff",
        "replace": "Woodruff & Pink Grapefruit"
    },
    {
        "id": "9f5e826b-3589-4e15-8da7-86759325fc9b:en-GB",
        "field": "flavor",
        "search": "Dragon Fruit",
        "replace": "Curuba-Elderflower"
    },
    {
        "id": "9f5e826b-3589-4e15-8da7-86759325fc9b:en-GB",
        "field": "flavor_description",
        "search": "Dragon Fruit",
        "replace": "Curuba Elderflower"
    },
    {
        "id": "b72f0639-7324-4c1b-9b22-9058ff040feb:de-DE",
        "field": "name",
        "search": "Pink Edition",
        "replace": "Pink Edition Sugarfree"
    }
]


class RedBullGenerator:
    """
    Generates comprehensive Red Bull editions JSON data from worldwide sources.

    This class orchestrates a two-stage data pipeline:
    1. Raw data collection from Red Bull's APIs across all available regions
    2. AI-powered normalization and translation using Google Gemini

    The generator intelligently handles locale deduplication, applies manual data fixes,
    and only processes data through AI when changes are detected to minimize API costs.

    :param force_mode: When True, forces AI processing even if no changes detected
    :type force_mode: bool

    :ivar session: Persistent HTTP session for API requests
    :type session: requests.Session
    :ivar gemini_client: Google Gemini AI client for data normalization
    :type gemini_client: genai.Client
    :ivar force_mode: Flag to force processing regardless of changes
    :type force_mode: bool

    :raises KeyError: If GEMINI_API_KEY environment variable is not set
    :raises SystemExit: If critical initialization fails

    .. note::
        Requires GEMINI_API_KEY environment variable to be set

    .. example::
        generator = RedBullGenerator(force_mode=True)
        generator.run(skip_external_fetch=False)
    """

    def __init__(self, force_mode: bool = False) -> None:
        """
        Initialize the Red Bull data generator with required services.

        :param force_mode: Force AI processing even without detected changes
        :type force_mode: bool
        :raises KeyError: If GEMINI_API_KEY environment variable is missing
        :raises SystemExit: If Gemini client initialization fails
        """
        self.force_mode = force_mode
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (https://github.com/Haxe18/rebull-editions-generator) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
        })
        try:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise KeyError("GEMINI_API_KEY environment variable not set.")
            self.gemini_client = genai.Client()
        except KeyError as exc:
            logging.critical("FATAL: %s", exc)
            logging.critical("Please set the environment variable before running the script.")
            sys.exit(1)
        # Catch more specific exceptions instead of the general 'Exception'
        except (google_exceptions, ValueError) as exc:
            logging.critical("FATAL: Could not initialize Gemini model. Error: %s", exc)
            sys.exit(1)

    @staticmethod
    def compare_raw_data_and_generate_changelog() -> Tuple[bool, str]:
        """
        Compare new raw data with previous version and generate changelog.

        Performs country-level comparison to detect additions, removals, and updates.
        Generates a formatted markdown changelog documenting all changes.

        :return: Tuple of (changes_detected, changelog_markdown)
        :rtype: Tuple[bool, str]

        :raises IOError: If raw data files cannot be read
        :raises json.JSONDecodeError: If JSON parsing fails

        .. note::
            Returns (True, "Initial Data Release") on first run when no previous data exists
        """
        if not os.path.exists(PREVIOUS_RAW_JSON_FILE):
            logging.info("No previous raw data file found. Assuming first run.")
            return True, "# Initial Data Release\n\nFirst-time generation of all Red Bull edition data."

        try:
            with open(RAW_JSON_FILE, 'r', encoding='utf-8') as new_file, \
                 open(PREVIOUS_RAW_JSON_FILE, 'r', encoding='utf-8') as old_file:
                new_data = json.load(new_file).get("raw_data_by_locale", {})
                old_data = json.load(old_file).get("raw_data_by_locale", {})
        except (IOError, json.JSONDecodeError) as error:
            logging.error("Could not read or parse raw data files for comparison: %s", error)
            return True, f"# Data Update\n\nCould not compare with previous data due to an error: {error}"

        added_countries = sorted([c for c in new_data if c not in old_data])
        removed_countries = sorted([c for c in old_data if c not in new_data])
        updated_countries = sorted([
            c for c in new_data if c in old_data and old_data[c] != new_data[c]
        ])

        if not any([added_countries, updated_countries, removed_countries]):
            return False, ""

        changelog_parts = ["# Red Bull Edition Data Update\n"]
        if updated_countries:
            changelog_parts.append("## 🔄 Updated Countries\n- " + "\n- ".join(updated_countries))
        if added_countries:
            changelog_parts.append("## ➕ Added Countries\n- " + "\n- ".join(added_countries))
        if removed_countries:
            changelog_parts.append("## ➖ Removed Countries\n- " + "\n- ".join(removed_countries))

        return True, "\n".join(changelog_parts)

    def _get_graphql_data(self, graphql_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch product details from Red Bull's GraphQL API.

        :param graphql_id: The GraphQL resource ID for the product
        :type graphql_id: str
        :return: GraphQL data dictionary or None if fetch fails
        :rtype: Optional[Dict[str, Any]]

        .. note::
            Includes random delay between requests to avoid rate limiting
        """
        try:
            time.sleep(randint(REQUEST_DELAY_FROM,REQUEST_DELAY_TO))
            gql_response = self.session.get(GRAPHQL_URL.format(graphql_id=graphql_id))
            gql_response.raise_for_status()
            return gql_response.json().get('data', {})
        except (requests.exceptions.RequestException, json.JSONDecodeError) as exc:
            logging.error("Error fetching or parsing GraphQL data for %s: %s", graphql_id, exc)
            return None

    @staticmethod
    def _clean_duplicated_text(text: str) -> str:
        """
        Clean duplicated words and normalize spacing in text.

        Removes consecutive duplicate words (case-insensitive) and normalizes
        whitespace. Useful for cleaning product names from APIs that may
        contain formatting issues.

        :param text: Input text to clean
        :type text: str
        :return: Cleaned text with duplicates removed
        :rtype: str

        :Example::
            >>> _clean_duplicated_text("Red Bull Bull Energy")
            "Red Bull Energy"
            >>> _clean_duplicated_text("Tropical/Tropical Edition")
            "Tropical Edition"
        """
        # Replace slashes with spaces to separate the words
        text = text.replace("/", " ")

        # Remove any extra spaces that may have been created and trim whitespace from ends
        text = re.sub(r'\s+', ' ', text).strip()

        # Use a regular expression to find and remove duplicated words.
        # The regex (\b\w+\b) captures a whole word.
        # \s+ matches one or more spaces.
        # \1 refers to the word captured in the first group.
        # The re.I flag makes the matching case-insensitive.
        text = re.sub(r'(\b\w+\b)\s+\1', r'\1', text, flags=re.I)

        return text

    def _extract_relevant_gql_details(self, gql_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and format relevant product details from GraphQL response.

        :param gql_data: Raw GraphQL response data
        :type gql_data: Dict[str, Any]
        :return: Formatted product details dictionary
        :rtype: Dict[str, Any]

        .. note::
            - Normalizes Açai variations to 'Acai'
            - Formats image URLs with proper dimensions
            - Cleans duplicated text in product names
        """
        image_url_template = gql_data.get('image', {}).get('imageEssence', {}).get('imageURL')
        formatted_image_url = ""
        if image_url_template:
            formatted_image_url = image_url_template.format(op='e_trim:1:transparent/c_limit,w_800,h_800/bo_5px_solid_rgb:00000000')

        product_id = gql_data.get('id', '').replace('rrn:content:energy-drinks:', '')
        flavor = self._clean_duplicated_text(gql_data.get('flavour', ''))

        flavor_description_space_cleaned = gql_data.get('standfirst').strip(' "')
        flavor_description_upper_cleaned = " ".join([word.capitalize() if word.isupper() else word for word in flavor_description_space_cleaned.split()])

        # Normalize all Açai variations to 'Acai' in flavor_description
        # This handles: açai, açaí, açaï, açaì, Açai, Açaí, etc.
        flavor_description_normalized = unicodedata.normalize('NFD', flavor_description_upper_cleaned)

        # Pattern matches all variations of açai with different diacritics in NFD form
        # After NFD normalization: ç becomes c + \u0327, í becomes i + \u0301
        pattern = r'[aA][çc]\u0327?[aA][iI]\u0301?'
        flavor_description_acai_fix = re.sub(pattern, 'Acai', flavor_description_normalized, flags=re.IGNORECASE)

        # Normalize back to composed form
        flavor_description_acai_fix = unicodedata.normalize('NFC', flavor_description_acai_fix)

        return {
            "id": product_id,
            "name": f"The {title}" if "Edition" in (title := gql_data.get('title') or "") else title,
            "flavor": flavor,
            "flavor_description": flavor_description_acai_fix,
            "color": gql_data.get('brandingHexColorCode'),
            "image_url": formatted_image_url,
            "alt_text": gql_data.get('image', {}).get('altText'),
            "product_url": gql_data.get('reference', {}).get('externalUrl').replace('http://','https://'),
        }

    def _fetch_editions_for_locale(self, lang_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fetch all product editions for a specific locale/country.

        :param lang_info: Locale information dictionary containing domain, countryName, flagCode
        :type lang_info: Dict[str, Any]
        :return: Dictionary with country data or None if no editions found
        :rtype: Optional[Dict[str, Any]]

        :Example return::
            {
                "Germany": {
                    "flag": "DE",
                    "editions": [...],
                    "flag_url": "https://..."
                }
            }
        """
        lang_code = lang_info.get('domain')
        country_name = lang_info.get('countryName')
        flag_code = lang_info.get('flagCode', 'Worldwide')
        flag_code = 'Worldwide' if 'INT' in flag_code else flag_code
        logging.info("Fetching data for: %s (%s)", country_name, lang_code)

        try:
            api_url = LANG_API_URL.format(locale=lang_code)
            response = self.session.get(api_url)
            response.raise_for_status()
            api_data = response.json()
            lang_editions_raw = api_data.get('featuredEnergyDrinks', [])

            if not lang_editions_raw:
                logging.warning("No editions found for %s. Skipping.", country_name)
                return None

            country_editions = []
            for edition_data in lang_editions_raw:
                graphql_id = edition_data.get('reference', {}).get('id')
                if not graphql_id:
                    continue
                if gql_data := self._get_graphql_data(graphql_id):
                    extracted_details = self._extract_relevant_gql_details(gql_data)
                    country_editions.append(extracted_details)

            if country_editions:
                return {
                    country_name: {
                        "flag": flag_code,
                        "editions": country_editions,
                        "flag_url": FLAG_BASE_URL.format(flag_code=flag_code)
                    }
                }
        except (requests.exceptions.RequestException, json.JSONDecodeError) as exc:
            logging.error("Could not process locale %s. Error: %s", lang_code, exc)
        return None

    def fetch_all_raw_data(self) -> Dict[str, Any]:
        """
        Fetch comprehensive raw product data from all Red Bull locales worldwide.

        Implements intelligent locale deduplication:
        - Caribbean region: Keeps all locales (English and Spanish)
        - Other regions: Prefers English locale when multiple exist
        - Falls back to first available locale if no English version

        :return: Dictionary containing all raw data organized by locale
        :rtype: Dict[str, Any]

        :raises SystemExit: If main language list cannot be fetched

        :Example return::
            {
                "raw_data_by_locale": {
                    "Germany": {...},
                    "United States": {...},
                    "Caribbean (English)": {...},
                    "Caribbean (Spanish)": {...}
                }
            }
        """
        logging.info("--- STAGE 1: Fetching all raw data from Red Bull APIs ---")
        all_raw_data = {}
        countries_processed = {}  # Track which countries have been processed

        logging.info("Fetching list of all available Red Bull locales...")
        try:
            start_api_url = LANG_API_URL.format(locale='int-en')
            lang_api_result = self.session.get(start_api_url)
            lang_api_result.raise_for_status()
            all_langs = lang_api_result.json()['selectableLocales']
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as exc:
            logging.critical("FATAL: Could not fetch the main language list. Error: %s", exc)
            sys.exit(1)

        # Group locales by country
        countries_locales = {}
        for lang_info in all_langs:
            country_name = lang_info.get('countryName')
            if country_name not in countries_locales:
                countries_locales[country_name] = []
            countries_locales[country_name].append(lang_info)

        # Process each country
        for country_name, locales in countries_locales.items():
            # Special case: Caribbean should keep all locales (both English and Spanish)
            if country_name == 'Caribbean':
                logging.info("Processing Caribbean with all %d locales", len(locales))
                for locale in locales:
                    if country_data := self._fetch_editions_for_locale(locale):
                        all_raw_data.update(country_data)
                        countries_processed[f"{country_name} ({locale.get('language', 'default')})"] = locale.get('label')
            else:
                # For other countries, use deduplication logic
                selected_locale = None

                if len(locales) == 1:
                    # Only one locale for this country
                    selected_locale = locales[0]
                    logging.debug("Single locale for %s: %s", country_name, selected_locale.get('label'))
                else:
                    # Multiple locales - prefer English
                    english_locales = [l for l in locales if '(en)' in l.get('label', '')]

                    if english_locales:
                        selected_locale = english_locales[0]
                        logging.info("Multiple locales for %s, selected English: %s",
                                    country_name, selected_locale.get('label'))
                    else:
                        # No English version, use first available
                        selected_locale = locales[0]
                        logging.info("Multiple locales for %s, no English found, using: %s",
                                    country_name, selected_locale.get('label'))

                    # Log skipped locales
                    for locale in locales:
                        if locale != selected_locale:
                            logging.debug("Skipping duplicate locale: %s", locale.get('label'))

                # Fetch data for selected locale
                if selected_locale and (country_data := self._fetch_editions_for_locale(selected_locale)):
                    all_raw_data.update(country_data)
                    countries_processed[country_name] = selected_locale.get('label')

        logging.info("Finished fetching raw data for %d countries.", len(all_raw_data))
        logging.debug("Countries processed: %s", countries_processed)
        return {"raw_data_by_locale": all_raw_data}

    def normalize_with_gemini(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize raw data using Google Gemini AI with retry logic.

        :param raw_data: Prepared raw data dictionary for AI processing
        :type raw_data: Dict[str, Any]
        :return: Normalized data dictionary or None if AI processing fails
        :rtype: Optional[Dict[str, Any]]

        :raises FileNotFoundError: If prompt file is not found

        .. note::
            - Uses deterministic settings (temperature=0, seed=11)
            - Retries up to 3 times on 503 errors with 60-second delay
            - Model: gemini-2.5-flash-lite for cost efficiency
        """
        logging.info("--- STAGE 3: Normalizing data with Gemini API ---")
        try:
            with open(PROMPT_FILE, "r", encoding="utf-8") as prompt_file:
                prompt_template = prompt_file.read()
        except FileNotFoundError:
            logging.critical("FATAL: Prompt file '%s' not found.", PROMPT_FILE)
            return None

        raw_json_str = json.dumps(raw_data, indent=2, ensure_ascii=False)
        prompt = prompt_template.format(raw_json_str=raw_json_str)
        logging.debug("Full prompt sent to Gemini.")

        max_retries = 3
        retry_delay = 60  # 1 minute

        for attempt in range(1, max_retries + 1):
            try:
                logging.info("Sending request to Gemini... (Attempt %d/%d)", attempt, max_retries)
                logging.debug(prompt)
                response = self.gemini_client.models.generate_content(
                    model=GEMINI_MODEL_TO_USE,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction='You are an expert data normalization and translation AI. Your task is to process a raw JSON object containing Red Bull product data from various countries and transform it into a clean, standardized, internationalized english language and consolidated JSON format.',
                        response_mime_type='application/json',
                        # A value of 1 means the model can only choose the single most likely word.
                        # This is the most restrictive and deterministic setting.
                        top_k=1,
                        # Value 0 makes the model deterministic.
                        # It will always choose the most likely next word, resulting in very predictable and consistent answers.
                        temperature=0,
                        # A specific seed, the "random" aspects of the generation process (if temperature > 0) become predictable.
                        # Running the same prompt with the same seed will produce the exact same output every time.
                        seed=11
                    )
                )
                logging.info("Received response from Gemini. Parsing JSON...")
                return json.loads(response.text)

            except json.JSONDecodeError as exc:
                logging.critical("FATAL: Could not parse Gemini's JSON response. Error: %s", exc)
                if 'response' in locals():
                    logging.info("--- Gemini Response Text ---\n%s", response.text)
                return None

            except google_exceptions as exc:
                error_message = str(exc)
                if "503" in error_message and "UNAVAILABLE" in error_message and attempt < max_retries:
                    logging.warning("Gemini API returned 503 (overloaded). Retrying in %d seconds... (Attempt %d/%d)",
                                  retry_delay, attempt, max_retries)
                    time.sleep(retry_delay)
                    continue

                logging.critical("FATAL: An error occurred with the Gemini API. Error: %s", exc)
                if 'response' in locals():
                    logging.info("--- Gemini Response ---\n%s", response)
                return None

            except ValueError as exc:
                logging.critical("FATAL: An error occurred with the Gemini API. Error: %s", exc)
                if 'response' in locals():
                    logging.info("--- Gemini Response ---\n%s", response)
                return None

        logging.critical("FATAL: All %d attempts to call Gemini API failed.", max_retries)
        return None

    def _prepare_data_for_ai(self, raw_data: Dict[str, Any]) -> Tuple[Dict, Dict, Dict]:
        """
        Prepare raw data for AI processing by stripping non-essential fields.

        Creates lookup maps to preserve data that AI doesn't need to process,
        reducing token usage and improving AI focus on core normalization tasks.

        :param raw_data: Complete raw data dictionary
        :type raw_data: Dict[str, Any]
        :return: Tuple of (stripped_data, product_details_map, country_details_map)
        :rtype: Tuple[Dict, Dict, Dict]

        .. note::
            Removes: color, image_url, alt_text, product_url, flag_url
            Cleans: Special characters from flavor_description
        """
        logging.info("Creating lookup maps and stripping data for AI.")
        product_details_map = {}
        country_details_map = {}
        stripped_data = copy.deepcopy(raw_data)

        edition_keys_to_remove = ["color", "image_url", "alt_text", "product_url"]
        country_keys_to_remove = ["flag_url"]

        # Text fields that need cleaning (remove special characters)
        text_fields_to_clean = ["flavor_description"]

        for country_name, country_content in stripped_data.get("raw_data_by_locale", {}).items():
            country_details_map[country_name] = {
                "flag_url": raw_data["raw_data_by_locale"][country_name].get("flag_url")
            }
            for key in country_keys_to_remove:
                if key in country_content:
                    del country_content[key]

            for edition in country_content.get("editions", []):
                if product_id := edition.get("id"):
                    product_details_map[product_id] = {
                        "color": edition.get("color"),
                        "image_url": edition.get("image_url"),
                        "alt_text": edition.get("alt_text"),
                        "product_url": edition.get("product_url")
                    }

                # Clean text fields - remove unwanted characters like *, #, @, etc. but keep umlauts and accented characters
                for field in text_fields_to_clean:
                    if field in edition and edition[field]:
                        original_text = str(edition[field])
                        # Remove only unwanted characters but keep letters (including umlauts), numbers, spaces, and common punctuation
                        cleaned_text = re.sub(r'[#*@$^<>[\]{}|\\/`~!]', ' ', original_text)
                        # Remove multiple spaces
                        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                        if original_text != cleaned_text:
                            logging.debug("Cleaned %s field: '%s' → '%s'", field, original_text, cleaned_text)
                        edition[field] = cleaned_text

                for key in edition_keys_to_remove:
                    if key in edition:
                        del edition[key]

        return stripped_data, product_details_map, country_details_map

    def _apply_data_fixes(self, raw_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Apply manual data corrections for known API issues.

        :param raw_data: Raw data dictionary to fix
        :type raw_data: Dict[str, Any]
        :return: Tuple of (fixed_data, changelog_entries)
        :rtype: Tuple[Dict[str, Any], List[str]]

        .. note::
            Fixes are defined in DATA_FIXES configuration array
            Logs warnings for fixes that couldn't be applied
        """
        logging.info("Applying manual data corrections...")
        applied_fixes = []
        skipped_fixes = []

        for fix in DATA_FIXES:
            target_id = fix["id"]
            field = fix["field"]
            search_text = fix["search"]
            replace_text = fix["replace"]

            # Find the product in the data
            found = False
            for country_data in raw_data.get("raw_data_by_locale", {}).values():
                for edition in country_data.get("editions", []):
                    if edition.get("id") == target_id:
                        found = True
                        current_value = edition.get(field, "")

                        if search_text.lower() in current_value.lower():
                            # Apply the fix - preserve original case in the replacement
                            new_value = current_value.replace(search_text, replace_text)
                            # Also try case-insensitive replacement for different cases
                            if search_text.lower() != search_text:
                                new_value = re.sub(re.escape(search_text), replace_text, current_value, flags=re.IGNORECASE)
                            edition[field] = new_value
                            applied_fixes.append(f"Fixed {field} for {target_id}: '{search_text}' → '{replace_text}'")
                            logging.info("Applied fix: %s for %s", applied_fixes[-1], target_id)
                        else:
                            # Fix not needed - text not found
                            skipped_fixes.append(f"Skipped {field} fix for {target_id}: '{search_text}' not found in '{current_value}'")
                            logging.info("Skipped fix: %s", skipped_fixes[-1])
                        break
                if found:
                    break

            if not found:
                skipped_fixes.append(f"Product not found: {target_id}")
                logging.warning("Product not found for fix: %s", target_id)

                # Add fix information to changelog - only show skipped fixes for manual cleanup
        if skipped_fixes:
            changelog_additions = ["## Data Fixes - Manual Cleanup Needed"]
            changelog_additions.append("### Skipped Fixes (can be removed from DATA_FIXES)")
            changelog_additions.extend([f"- {fix}" for fix in skipped_fixes])
            changelog_additions.append("")
            changelog_additions.append("*These fixes were not applied and can be safely removed from the DATA_FIXES configuration.*")

            return raw_data, changelog_additions

        return raw_data, []

    @staticmethod
    def _capitalize_second_word(text: str) -> str:
        """
        Capitalize the second word in hyphen-separated flavor names.

        :param text: Input string, typically a flavor name
        :type text: str
        :return: String with second word capitalized after hyphen
        :rtype: str

        :Example::
            >>> _capitalize_second_word('strawberry-apricot')
            'strawberry-Apricot'
            >>> _capitalize_second_word('curuba-elderflower')
            'curuba-Elderflower'
            >>> _capitalize_second_word('single')
            'single'
        """
        # Split the string into a list of words
        parts = text.split('-')

        # Check if a second word exists
        if len(parts) > 1:
            # Capitalize the second word (at index 1)
            parts[1] = parts[1].capitalize()

        # Join the parts back together with a hyphen
        return '-'.join(parts)

    def _rehydrate_ai_response(self, ai_response: Dict, product_map: Dict, country_map: Dict) -> Dict:
        """
        Re-insert preserved details and apply final cleanup to AI-normalized data.

        :param ai_response: Normalized data from Gemini AI
        :type ai_response: Dict
        :param product_map: Map of product IDs to preserved details
        :type product_map: Dict
        :param country_map: Map of countries to preserved details
        :type country_map: Dict
        :return: Complete final data with all details restored
        :rtype: Dict

        .. note::
            - Restores: color, image_url, alt_text, product_url, flag_url
            - Fixes: 'description' -> 'flavor_description' field naming
            - Cleans: Punctuation spacing, removes trailing periods
            - Normalizes: 'sugars' -> 'sugar' variations
        """
        logging.info("Re-inserting preserved details into the normalized data.")

        for country_name, country_value in ai_response.items():
            # The country_name is the key, so we use it directly to look up in country_map
            if country_name in country_map:
                country_value.update(country_map[country_name])
            else:
                logging.warning(
                    "Could not find matching country details for country name '%s'.",
                    country_name
                )

            for edition in country_value.get("editions", []):
                product_id = edition.pop('id', None)
                if product_id and product_id in product_map:
                    edition.update(product_map[product_id])
                else:
                    logging.warning("Could not find matching product details for ID '%s'.", product_id)

                # Fix field naming: rename 'description' to 'flavor_description' if AI used wrong field name
                if 'description' in edition and 'flavor_description' not in edition:
                    edition['flavor_description'] = edition.pop('description')
                    logging.warning("Fixed field name: renamed 'description' to 'flavor_description' for product ID '%s'", product_id)

                if 'flavor' in edition:
                    edition["flavor"] = self._capitalize_second_word(edition["flavor"])

                if 'flavor_description' in edition:
                    # Cleanup, string remove *# etc ...
                    desc = edition["flavor_description"]

                    # Remove special characters except allowed ones
                    desc = re.sub(r'[^a-zA-Z0-9:%\.,!? ]', '', desc)

                    # Fix spacing around punctuation (space before -> no space, ensure space after)
                    desc = re.sub(r'\s+([.,!?])', r'\1', desc)  # Remove spaces before punctuation
                    desc = re.sub(r'([.,!?])(?=[a-zA-Z0-9])', r'\1 ', desc)  # Add space after if missing

                    # Remove multiple spaces
                    desc = re.sub(r'\s+', ' ', desc).strip()

                    # Remove trailing period at the end of the description
                    if desc.endswith('.'):
                        desc = desc[:-1].strip()

                    # Replace "sugars" with "sugar" (preserve most cases, normalize SUGARS)
                    desc = re.sub(r'\bSugars\b', 'Sugar', desc)  # Capitalized
                    desc = re.sub(r'\bsugars\b', 'sugar', desc)  # Lowercase
                    desc = re.sub(r'\bSUGARS\b', 'Sugar', desc)  # UPPERCASE -> Normal case

                    edition["flavor_description"] = desc

        return ai_response

    def run(self, skip_external_fetch: bool = False) -> None:
        """
        Execute the complete Red Bull editions data generation pipeline.

        :param skip_external_fetch: Use cached data instead of fetching from APIs
        :type skip_external_fetch: bool

        :raises SystemExit: If critical errors occur during processing

        .. note::
            Pipeline stages:
            1. Fetch/load raw data
            2. Compare with previous run
            3. Apply manual fixes (if changes detected)
            4. Process with Gemini AI (if changes detected)
            5. Save final normalized data
        """
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        if skip_external_fetch:
            logging.info("--- SKIPPING EXTERNAL DATA FETCH ---")
            logging.info("Using locally available data from previous run.")

            if not os.path.exists(PREVIOUS_RAW_JSON_FILE):
                logging.critical("FATAL: No previous raw data file found at '%s'. Cannot proceed without external fetch.", PREVIOUS_RAW_JSON_FILE)
                sys.exit(1)

            try:
                with open(PREVIOUS_RAW_JSON_FILE, "r", encoding='utf-8') as raw_file:
                    new_raw_data = json.load(raw_file)
                logging.info("Successfully loaded previous raw data from '%s'.", PREVIOUS_RAW_JSON_FILE)
            except (IOError, json.JSONDecodeError) as error:
                logging.critical("FATAL: Could not read or parse previous raw data file. Error: %s", error)
                sys.exit(1)
        else:
            new_raw_data = self.fetch_all_raw_data()

            try:
                with open(RAW_JSON_FILE, "w", encoding='utf-8') as raw_file:
                    json.dump(new_raw_data, raw_file, indent=4, ensure_ascii=False)
                logging.info("Successfully saved new raw data to '%s'.", RAW_JSON_FILE)
            except (IOError, OSError) as error:
                logging.critical("FATAL: Could not save raw data file. Error: %s", error)
                sys.exit(1)

        if skip_external_fetch:
            # Skip comparison when using local data - assume changes exist
            has_changes = True
            changelog_text = "# Local Data Processing\n\nProcessing existing data with AI normalization and manual fixes."
            logging.info("Skipping data comparison - processing local data with AI.")
        else:
            has_changes, changelog_text = self.compare_raw_data_and_generate_changelog()

            if not has_changes:
                logging.info("No changes detected. The existing '%s' is up to date.", FINAL_JSON_FILE)
                if not self.force_mode:
                    os.remove(RAW_JSON_FILE)
                    return

                logging.info("Force mode enabled - proceeding with AI processing despite no changes.")
                changelog_text = "# Force Mode Processing\n\nProcessing data despite no changes detected."

        logging.info("Changes detected. Proceeding with AI normalization.")

        # Apply manual data fixes before AI processing
        new_raw_data, fix_changelog = self._apply_data_fixes(new_raw_data)

        # Combine changelog with fix information
        if fix_changelog:
            changelog_text += "\n\n" + "\n".join(fix_changelog)

        logging.info("--- Changelog ---\n%s", changelog_text)
        with open(CHANGELOG_FILE, "w", encoding="utf-8") as changelog_file:
            changelog_file.write(changelog_text)

        stripped_data, product_map, country_map = self._prepare_data_for_ai(new_raw_data)
        final_data_from_ai = self.normalize_with_gemini(stripped_data)

        if final_data_from_ai:
            final_data = self._rehydrate_ai_response(final_data_from_ai, product_map, country_map)
            logging.info("--- STAGE 4: Saving final results ---")
            with open(FINAL_JSON_FILE, "w", encoding='utf-8') as final_file:
                json.dump(final_data, final_file, indent=4, ensure_ascii=False)
            logging.info("Successfully created final output '%s'.", FINAL_JSON_FILE)
            if not skip_external_fetch:
                os.replace(RAW_JSON_FILE, PREVIOUS_RAW_JSON_FILE)
                logging.info("Updated reference file '%s'.", PREVIOUS_RAW_JSON_FILE)
        else:
            logging.critical("AI normalization failed. Final files were not updated.")
            if not skip_external_fetch and os.path.exists(RAW_JSON_FILE):
                os.remove(RAW_JSON_FILE)

        logging.info("Script finished.")


def main() -> None:
    """
    Main entry point for the Red Bull editions generator script.

    Parses command-line arguments and executes the generation pipeline.

    :Command-line arguments:
        -v, --verbose: Enable DEBUG level logging
        --skip-external-fetch: Use cached data only
        --force: Force processing even without changes

    :Environment variables:
        GEMINI_API_KEY: Required Google Gemini API key

    :Example::
        python redbull_editions_json_generate.py --verbose --force
    """
    parser = argparse.ArgumentParser(
        description="Fetches and normalizes Red Bull edition data using Red Bull APIs and Google Gemini.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose (DEBUG) logging output.'
    )
    parser.add_argument(
        '--skip-external-fetch',
        action='store_true',
        help='Skip external data fetching and use only locally available data from dist/redbull_editions_raw.previous.json'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force processing even when no changes are detected'
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )

    if not args.verbose:
        for logger_name in ["httpx", "httpcore", "hpack", "urllib3", "google.api_core", "google.auth", "google.generativeai"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)

    logging.debug("Verbose mode enabled.")
    generator = RedBullGenerator(force_mode=args.force)
    generator.run(skip_external_fetch=args.skip_external_fetch)


if __name__ == "__main__":
    main()
