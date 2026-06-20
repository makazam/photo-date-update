#!/usr/bin/env python3
"""
rename_to_exif.py — Rename image/video files to match their EXIF date.

Reads the DateTimeOriginal (or CreateDate) from each file's metadata and
renames it to YYYYMMDD_NNN.ext, where NNN continues from the highest
existing number for that date in the folder.

Usage:
    python rename_to_exif.py <folder> [options]

Options:
    --dry-run        Preview renames without applying them
    --recursive      Also process subfolders
    --exiftool PATH  Path to exiftool executable

Examples:
    python rename_to_exif.py "C:/Photos/2023" --dry-run
    python rename_to_exif.py "C:/Photos/2023"
    python rename_to_exif.py "C:/Photos" --recursive --dry-run
"""

import argparse
import subprocess
import sys
import re
import os
import tempfile
from pathlib import Path
from collections import defaultdict

_SCRIPT_DIR = Path(__file__).parent
_DEFAULT_EXIFTOOL = str(_SCRIPT_DIR / "exiftool" / "exiftool.exe")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".bmp", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".wmv", ".mts", ".m2ts"}
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS

# Matches existing YYYYMMDD_NNN filenames to avoid conflicts
EXISTING_PATTERN = re.compile(r"^(\d{8})_(\d+)", re.IGNORECASE)


def check_exiftool(exiftool_path):
    try:
        result = subprocess.run([exiftool_path, "-ver"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    print(f"ERROR: exiftool not found at '{exiftool_path}'.")
    sys.exit(1)


def find_files(folder, recursive):
    folder = Path(folder)
    if not folder.is_dir():
        print(f"ERROR: '{folder}' is not a directory.")
        sys.exit(1)
    pattern = "**/*" if recursive else "*"
    return sorted(f for f in folder.glob(pattern) if f.is_file() and f.suffix.lower() in ALL_EXTS)


def get_exif_dates(files, exiftool_path):
    """Run exiftool once on all files and return {filepath: 'YYYYMMDD'} dict."""
    if not files:
        return {}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write("\n".join(str(f) for f in files))
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [exiftool_path, "-DateTimeOriginal", "-CreateDate", "-d", "%Y%m%d", "-csv", "-@", tmp_path],
            capture_output=True, text=True
        )
    finally:
        os.unlink(tmp_path)

    dates = {}
    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        return dates

    # CSV header: SourceFile,DateTimeOriginal,CreateDate
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        filepath = parts[0].strip()
        date_val = parts[1].strip() if len(parts) > 1 else ""
        # Fall back to CreateDate if DateTimeOriginal is missing
        if not date_val and len(parts) > 2:
            date_val = parts[2].strip()
        # Validate it looks like YYYYMMDD
        if re.fullmatch(r"\d{8}", date_val):
            dates[filepath] = date_val

    return dates


def build_next_counters(folder, recursive):
    """Scan folder for existing YYYYMMDD_NNN files and return {date: next_number}."""
    folder = Path(folder)
    pattern = "**/*" if recursive else "*"
    counters = defaultdict(int)

    for f in folder.glob(pattern):
        if not f.is_file():
            continue
        m = EXISTING_PATTERN.match(f.stem)
        if m:
            date_key = m.group(1)
            num = int(m.group(2))
            if num > counters[date_key]:
                counters[date_key] = num

    # next available number = current max + 1
    return defaultdict(int, {k: v + 1 for k, v in counters.items()})


def main():
    parser = argparse.ArgumentParser(
        description="Rename files to YYYYMMDD_NNN.ext based on their EXIF date."
    )
    parser.add_argument("folder", help="Folder containing files to rename")
    parser.add_argument("--dry-run", action="store_true", help="Preview renames without applying")
    parser.add_argument("--recursive", action="store_true", help="Also process subfolders")
    parser.add_argument("--exiftool", default=_DEFAULT_EXIFTOOL, help="Path to exiftool executable")
    args = parser.parse_args()

    version = check_exiftool(args.exiftool)
    print(f"exiftool {version} found.\n")

    files = find_files(args.folder, args.recursive)
    if not files:
        print("No supported image/video files found.")
        return

    print(f"Reading EXIF dates from {len(files)} file(s)...")
    exif_dates = get_exif_dates(files, args.exiftool)

    # Build counters from existing YYYYMMDD_NNN files in the folder
    next_counters = build_next_counters(args.folder, args.recursive)

    no_date = []
    already_correct = []
    to_rename = []

    for f in files:
        # Normalise path separators for dict lookup
        key = str(f).replace("\\", "/")
        date = exif_dates.get(key) or exif_dates.get(str(f))

        if not date:
            no_date.append(f)
            continue

        # Check if filename already matches YYYYMMDD_ for this date
        if f.stem.startswith(date + "_"):
            already_correct.append(f)
            continue

        to_rename.append((f, date))

    print(f"Already correctly named: {len(already_correct)}")
    print(f"No EXIF date found:      {len(no_date)}")
    print(f"To rename:               {len(to_rename)}\n")

    if no_date:
        print("Files with no EXIF date (skipped):")
        for f in no_date:
            print(f"  {f.name}")
        print()

    if not to_rename:
        print("Nothing to rename.")
        return

    if args.dry_run:
        print("DRY RUN — no changes written:\n")

    # Assign new names, picking up from existing counters per date
    for f, date in to_rename:
        n = next_counters[date]
        next_counters[date] += 1
        width = 3
        new_name = f"{date}_{n:0{width}}{f.suffix.lower()}"
        new_path = f.parent / new_name
        print(f"  {f.name} → {new_name}")
        if not args.dry_run:
            f.rename(new_path)

    if not args.dry_run:
        print(f"\nDone. {len(to_rename)} file(s) renamed.")
    else:
        print(f"\nDry run complete. {len(to_rename)} file(s) would be renamed.")


if __name__ == "__main__":
    main()
