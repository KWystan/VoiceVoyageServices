"""Synchronize dynamic-module text with the phoneme service catalog.

The curated CSV remains the runtime source of truth. Existing catalog entries
win over word-bank IPA. New exact text entries are bootstrapped from component
catalog words when possible, otherwise from the authored word-bank phonemes.

Run from ``VoiceVoyageServices``:

    python -X utf8 scripts/sync_word_bank_catalog.py --write
    python -X utf8 scripts/sync_word_bank_catalog.py --check
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORD_BANK = ROOT / "dynamic_modules_service" / "data" / "word_bank.json"
CURATED_CSV = ROOT / "phoneme_service" / "data" / "curated_words.csv"


def clean_text(value: str) -> str:
    value = re.sub(r"[^A-Za-z\s'-]", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def phoneme_tokens(value: str) -> list[str]:
    return [token.strip() for token in value.split(",") if token.strip()]


def load_catalog() -> tuple[dict[str, list[str]], list[str]]:
    catalog: dict[str, list[str]] = {}
    order: list[str] = []
    with CURATED_CSV.open(encoding="utf-8-sig", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            key = clean_text(row.get("word", ""))
            tokens = phoneme_tokens(row.get("phonemes", ""))
            if not key or not tokens:
                continue
            if key not in catalog:
                order.append(key)
            # Match the runtime loader's established behavior: when legacy
            # rows duplicate a key, the final authored row is canonical. The
            # rewritten CSV removes the duplicate.
            catalog[key] = tokens
    return catalog, order


def synchronized_data() -> tuple[dict, dict[str, list[str]], list[str], list[str]]:
    with WORD_BANK.open(encoding="utf-8") as bank_file:
        bank_data = json.load(bank_file)
    catalog, order = load_catalog()
    added: list[str] = []
    seen_bank: dict[str, list[str]] = {}

    for item in bank_data.get("items", []):
        text = str(item.get("text", "")).strip()
        key = clean_text(text)
        authored = phoneme_tokens(str(item.get("phonemes", "")))
        if not key or not authored:
            raise ValueError(f"Word-bank item has invalid text/phonemes: {text!r}")

        canonical = catalog.get(key)
        if canonical is None:
            words = key.split()
            if len(words) > 1 and all(word in catalog for word in words):
                canonical = [
                    token
                    for word in words
                    for token in catalog[word]
                ]
            else:
                canonical = authored
            catalog[key] = canonical
            order.append(key)
            added.append(key)

        prior = seen_bank.get(key)
        if prior is not None and prior != canonical:
            raise ValueError(f"Conflicting word-bank IPA for '{key}'")
        seen_bank[key] = canonical
        item["phonemes"] = ",".join(canonical)
        item.setdefault("language", "en")
        item.setdefault("language_variety", "project-english-reference")

    return bank_data, catalog, order, added


def write_data(bank_data, catalog, order) -> None:
    with WORD_BANK.open("w", encoding="utf-8", newline="\n") as bank_file:
        json.dump(bank_data, bank_file, ensure_ascii=True, indent=2)
        bank_file.write("\n")
    with CURATED_CSV.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, lineterminator="\n")
        writer.writerow(["word", "phonemes"])
        for key in order:
            writer.writerow([key, ",".join(catalog[key])])


def check_current(bank_data, catalog) -> list[str]:
    failures: list[str] = []
    with WORD_BANK.open(encoding="utf-8") as bank_file:
        current_bank = json.load(bank_file)
    for current, expected in zip(
        current_bank.get("items", []), bank_data.get("items", [])
    ):
        if current.get("phonemes") != expected.get("phonemes"):
            failures.append(
                f"{current.get('text')}: word-bank phonemes differ from catalog"
            )
        if clean_text(str(current.get("text", ""))) not in catalog:
            failures.append(f"{current.get('text')}: missing exact catalog entry")
    if len(current_bank.get("items", [])) != len(bank_data.get("items", [])):
        failures.append("word-bank item count changed during synchronization")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    bank_data, catalog, order, added = synchronized_data()
    if args.write:
        write_data(bank_data, catalog, order)
        print(
            f"Synchronized {len(bank_data['items'])} items; "
            f"added {len(added)} exact catalog entries."
        )
        return 0

    failures = check_current(bank_data, catalog)
    if failures or added:
        for failure in failures:
            print(f"ERROR: {failure}")
        for key in added:
            print(f"ERROR: '{key}' is missing from curated_words.csv")
        return 1
    print(f"Catalog alignment OK for {len(bank_data['items'])} items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
