#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path

import anthropic
import pdfplumber

KNOWN_COMPANIES = {"GS", "Citi", "CF40", "DB", "Nomura", "JPM"}

SYSTEM_PROMPT = """You extract metadata from financial research PDF text.
Return ONLY a JSON object with these exact keys:
- "date": report date as YYMMDD string (e.g. "260517"), or null if unclear
- "company": issuing firm — must be one of: GS, Citi, CF40, DB, Nomura, JPM — or null if not found
- "country": ISO-like country code (e.g. "TA" for Taiwan), or "Global" if the report has no specific country focus or the country is unclear
- "title": short descriptive title (max 60 chars, no special characters except spaces and hyphens), or null if unclear

No explanation, no markdown — only the JSON object."""


def extract_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[:2]
        text = "\n".join(p.extract_text() or "" for p in pages)
    return text[:2000]


def query_claude(client: anthropic.Anthropic, text: str) -> dict:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"PDF text:\n{text}"}],
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.DOTALL)
    return json.loads(raw)


def sanitize_title(title: str) -> str:
    title = title.strip()
    title = re.sub(r"[/:]+", "-", title)
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"[^\w\s\-]", "", title)
    return title.strip()


def build_new_name(meta: dict) -> tuple[str | None, str | None]:
    """Returns (new_filename, missing_field) — one will be None."""
    for field in ("date", "company", "title"):
        if not meta.get(field):
            return None, field
    if not meta.get("country"):
        meta["country"] = "Global"
    if meta["company"] not in KNOWN_COMPANIES:
        return None, "company"
    country = meta["country"]
    title = sanitize_title(meta["title"])
    if title.lower().startswith(country.lower() + " "):
        title = title[len(country):].strip()
    name = f"{meta['date']}-{meta['company']}-{country}-{title}.pdf"
    return name, None


def collect_pdfs(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(target.glob("*.pdf"))


def main():
    parser = argparse.ArgumentParser(description="Auto-rename financial research PDFs")
    parser.add_argument("path", type=Path, help="PDF file or folder containing PDFs")
    parser.add_argument("--yes", "-y", action="store_true", help="Apply renames without confirmation prompt")
    args = parser.parse_args()

    if not args.path.exists():
        sys.exit(f"Error: {args.path} does not exist")

    pdfs = collect_pdfs(args.path)
    if not pdfs:
        sys.exit("No PDF files found.")

    client = anthropic.Anthropic()
    renames: list[tuple[Path, str]] = []

    for pdf in pdfs:
        if re.match(r"^\d{6}-[^-]+-[^-]+-.*\.pdf$", pdf.name):
            print(f"[SKIP] {pdf.name} — already renamed")
            continue
        print(f"Processing {pdf.name} ...", end=" ", flush=True)
        try:
            text = extract_text(pdf)
            meta = query_claude(client, text)
            new_name, missing = build_new_name(meta)
        except Exception as e:
            print(f"\n[SKIP] {pdf.name} — error: {e}")
            continue

        if missing:
            print(f"\n[SKIP] {pdf.name} — missing field: {missing}")
        else:
            print("done")
            renames.append((pdf, new_name))

    if not renames:
        print("\nNo files to rename.")
        return

    print(f"\n{'Original':<50}  {'Proposed'}")
    print("-" * 100)
    for src, dst in renames:
        print(f"{src.name:<50}  {dst}")

    if not args.yes:
        answer = input(f"\nApply {len(renames)} rename(s)? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted. No files were renamed.")
            return

    for src, dst in renames:
        dest_path = src.parent / dst
        os.rename(src, dest_path)
        print(f"[OK] {src.name} → {dst}")


if __name__ == "__main__":
    main()
