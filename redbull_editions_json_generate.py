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
# Manual fixes to apply before AI processing, Data broken from the API
DATA_FIXES = [
    {
        "id": "ac367322-24c1-44a9-ad4a-1e022f9347d6:fi-FI",
        "field": "flavor",
        "search": "Dragon fruit",
        "replace": "Curuba-Elderflower"
    },
    {
        "id": "f900c5b7-d33e-4a8e-a186-5cee5bd291a1:en-MEA",
        "field": "standfirst",
        "search": "Summer Edition",
        "replace": "The Apricot Edition"
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
        "id": "9f5e826b-3589-4e15-8da7-86759325fc9b:en-GB",
        "field": "flavor",
        "search": "Dragon Fruit",
        "replace": "Curuba-Elderflower"
    },
    {
        "id": "9f5e826b-3589-4e15-8da7-86759325fc9b:en-GB",
        "field": "standfirst",
        "search": "Dragon Fruit",
        "replace": "Curuba Elderflower"
    }
]


class RedBullGenerator:
    """
    Generates Red Bull editions JSON by fetching raw data and using a conditional AI step for normalization.
    """

    def __init__(self, force_mode=False):
        """Initializes the generator, session, and Gemini model."""
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

    def compare_raw_data_and_generate_changelog(self) -> Tuple[bool, str]:
        """
        Compares the new raw data with the previous version on a per-country basis.
        Generates a markdown changelog and returns if changes were detected.

        Returns:
            A tuple (has_changes: bool, changelog_content: str)
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
        """Fetches GraphQL data for a given ID with a small delay."""
        try:
            time.sleep(randint(REQUEST_DELAY_FROM,REQUEST_DELAY_TO))
            gql_response = self.session.get(GRAPHQL_URL.format(graphql_id=graphql_id))
            gql_response.raise_for_status()
            return gql_response.json().get('data', {})
        except (requests.exceptions.RequestException, json.JSONDecodeError) as exc:
            logging.error("Error fetching or parsing GraphQL data for %s: %s", graphql_id, exc)
            return None

    @staticmethod
    def _clean_duplicated_text(text):
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
        """Safely extracts and formats relevant fields from the GraphQL response."""
        image_url_template = gql_data.get('image', {}).get('imageEssence', {}).get('imageURL')
        formatted_image_url = ""
        if image_url_template:
            formatted_image_url = image_url_template.format(op='e_trim:1:transparent/c_limit,w_800,h_800/bo_5px_solid_rgb:00000000')

        product_id = gql_data.get('id', '').replace('rrn:content:energy-drinks:', '')
        flavor = self._clean_duplicated_text(gql_data.get('flavour', ''))

        return {
            "id": product_id,
            "name": f"The {title}" if "Edition" in (title := gql_data.get('title') or "") else title,
            "flavor": flavor,
            "standfirst": gql_data.get('standfirst').strip(' "'),
            "color": gql_data.get('brandingHexColorCode'),
            "image_url": formatted_image_url,
            "alt_text": gql_data.get('image', {}).get('altText'),
            "product_url": gql_data.get('reference', {}).get('externalUrl').replace('http://','https://'),
        }

    def _fetch_editions_for_locale(self, lang_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetches all editions for a single locale."""
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
        """Fetches all raw product data from all available locales."""
        logging.info("--- STAGE 1: Fetching all raw data from Red Bull APIs ---")
        all_raw_data = {}
        logging.info("Fetching list of all available Red Bull locales...")
        try:
            start_api_url = LANG_API_URL.format(locale='int-en')
            lang_api_result = self.session.get(start_api_url)
            lang_api_result.raise_for_status()
            all_langs = lang_api_result.json()['selectableLocales']
        except (requests.exceptions.RequestException, json.JSONDecodeError, KeyError) as exc:
            logging.critical("FATAL: Could not fetch the main language list. Error: %s", exc)
            sys.exit(1)

        for lang_info in all_langs:
            if country_data := self._fetch_editions_for_locale(lang_info):
                all_raw_data.update(country_data)

        logging.info("Finished fetching raw data for %d locales.", len(all_raw_data))
        return {"raw_data_by_locale": all_raw_data}

    def normalize_with_gemini(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Sends the entire raw data to Gemini for normalization with retry logic for 503 errors."""
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
                else:
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
        """Strips non-essential data and creates lookup maps for re-hydration."""
        logging.info("Creating lookup maps and stripping data for AI.")
        product_details_map = {}
        country_details_map = {}
        stripped_data = copy.deepcopy(raw_data)

        edition_keys_to_remove = ["color", "image_url", "alt_text", "product_url"]
        country_keys_to_remove = ["flag_url"]

        # Text fields that need cleaning (remove special characters)
        text_fields_to_clean = ["standfirst"]

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
                        # Remove only unwanted characters but keep letters (including umlauts), numbers, spaces, and common punctuation
                        cleaned_text = re.sub(r'[#*@$^<>[\]{}|\\/`~!]', '', str(edition[field]))
                        # Remove multiple spaces
                        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                        edition[field] = cleaned_text
                        logging.debug("Cleaned %s field: '%s' → '%s'", field, edition.get(field, ""), cleaned_text)

                for key in edition_keys_to_remove:
                    if key in edition:
                        del edition[key]

        return stripped_data, product_details_map, country_details_map

    def _apply_data_fixes(self, raw_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Applies manual data corrections before AI processing."""
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
        Capitalizes the second word in a hyphen-separated string.

        Example:
        'strawberry-apricot' -> 'strawberry-Apricot'
        'one-two-three' -> 'one-Two-three'

        Args:
            text: The input string.

        Returns:
            The modified string. If there is no hyphen, the original
            string is returned.
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
        """Re-inserts preserved details back into the AI-normalized data."""
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

                if 'flavor' in edition:
                    edition["flavor"] = self._capitalize_second_word(edition["flavor"])

                if 'flavor_description' in edition:
                    # Cleanup, string remove *# etc ...
                    edition["flavor_description"] = re.sub(r'[^a-zA-Z0-9:%\. ]', '', edition["flavor_description"]).replace('  ', ' ')

        return ai_response

    def run(self, skip_external_fetch=False):
        """Executes the full generation process."""
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
                else:
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


def main():
    """Main script execution function."""
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
