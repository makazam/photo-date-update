#!/usr/bin/env python3
"""
redate_from_name.py — Set image/video dates based on the date in the filename.

Expects filenames in the format: YYYYMMDD_anything.ext
Example: 20230915_0042.jpg → date 2023-09-15

Usage:
    python redate_from_name.py <folder> [options]

Options:
    --dry-run        Preview changes without writing anything
    --recursive      Also process subfolders
    --time HH:MM:SS  Time to set on all files (default: 12:00:00)
    --city NAME      City name for DST-aware timezone (e.g. cairo, munich)
    --timezone +HH:MM  Manual UTC offset (e.g. +02:00)
    --exiftool PATH  Path to exiftool executable

Examples:
    python redate_from_name.py "C:/Photos/2023" --dry-run
    python redate_from_name.py "C:/Photos/2023" --city cairo
    python redate_from_name.py "C:/Photos/2023" --city denver --time 14:00:00
"""

import argparse
import subprocess
import sys
import re
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone as dt_timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    _HAS_ZONEINFO = True
except ImportError:
    _HAS_ZONEINFO = False

_SCRIPT_DIR = Path(__file__).parent
_DEFAULT_EXIFTOOL = str(_SCRIPT_DIR / "exiftool" / "exiftool.exe")

CITY_TIMEZONES = {
    # Africa
    "cairo": "Africa/Cairo", "alexandria": "Africa/Cairo", "sharmelsheikh": "Africa/Cairo", "johannesburg": "Africa/Johannesburg", "nairobi": "Africa/Nairobi",
    "lagos": "Africa/Lagos", "casablanca": "Africa/Casablanca", "accra": "Africa/Accra",
    # Middle East
    "dubai": "Asia/Dubai", "abudhabi": "Asia/Dubai", "sharjah": "Asia/Dubai", "riyadh": "Asia/Riyadh",
    "doha": "Asia/Qatar", "kuwait": "Asia/Kuwait", "beirut": "Asia/Beirut",
    "amman": "Asia/Amman", "jerusalem": "Asia/Jerusalem", "tehran": "Asia/Tehran",
    # Europe
    "london": "Europe/London", "paris": "Europe/Paris", "berlin": "Europe/Berlin",
    "rome": "Europe/Rome", "madrid": "Europe/Madrid", "amsterdam": "Europe/Amsterdam",
    "brussels": "Europe/Brussels", "zurich": "Europe/Zurich", "vienna": "Europe/Vienna",
    "munich": "Europe/Berlin", "kitzbuehel": "Europe/Vienna",
    "stockholm": "Europe/Stockholm", "oslo": "Europe/Oslo", "copenhagen": "Europe/Copenhagen",
    "helsinki": "Europe/Helsinki", "athens": "Europe/Athens", "istanbul": "Europe/Istanbul",
    "reykjavik": "Atlantic/Reykjavik", "moscow": "Europe/Moscow",
    # Americas
    "newyork": "America/New_York", "boston": "America/New_York", "miami": "America/New_York",
    "toronto": "America/Toronto", "montreal": "America/Montreal", "atlanta": "America/New_York",
    "chicago": "America/Chicago", "houston": "America/Chicago", "dallas": "America/Chicago",
    "denver": "America/Denver", "phoenix": "America/Phoenix",
    "saltlakecity": "America/Denver", "albuquerque": "America/Denver",
    "losangeles": "America/Los_Angeles", "seattle": "America/Los_Angeles",
    "sanfrancisco": "America/Los_Angeles", "sanjose": "America/Los_Angeles",
    "vancouver": "America/Vancouver", "anchorage": "America/Anchorage", "honolulu": "Pacific/Honolulu",
    "mexico": "America/Mexico_City", "bogota": "America/Bogota", "lima": "America/Lima",
    "santiago": "America/Santiago", "buenosaires": "America/Argentina/Buenos_Aires",
    "saopaulo": "America/Sao_Paulo",
    # Asia / Pacific
    "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata", "kolkata": "Asia/Kolkata",
    "karachi": "Asia/Karachi", "islamabad": "Asia/Karachi", "dhaka": "Asia/Dhaka",
    "colombo": "Asia/Colombo", "bangkok": "Asia/Bangkok", "jakarta": "Asia/Jakarta",
    "singapore": "Asia/Singapore", "kualalumpur": "Asia/Kuala_Lumpur", "hongkong": "Asia/Hong_Kong",
    "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai", "taipei": "Asia/Taipei",
    "tokyo": "Asia/Tokyo", "seoul": "Asia/Seoul", "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne", "auckland": "Pacific/Auckland",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".bmp", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".wmv", ".mts", ".m2ts"}
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS

DATE_PATTERNS = [
    re.compile(r"^(\d{4})(\d{2})(\d{2})_"),                      # 20230915_0042.jpg
    re.compile(r"^IMG-(\d{4})(\d{2})(\d{2})-", re.IGNORECASE),   # IMG-20230915-WA0001.jpg
    re.compile(r"^VID-(\d{4})(\d{2})(\d{2})-", re.IGNORECASE),   # VID-20230915-WA0001.mp4
]


def extract_date(filename):
    """Extract date from filename. Supports YYYYMMDD_ and IMG-YYYYMMDD- formats."""
    for pattern in DATE_PATTERNS:
        m = pattern.match(filename)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            try:
                datetime(int(y), int(mo), int(d))  # validate
                return y, mo, d
            except ValueError:
                continue
    return None


def city_to_offset(city_key, y, mo, d, time_str):
    """Return UTC offset string (e.g. +02:00) for a city on a given date, DST-aware."""
    iana = CITY_TIMEZONES[city_key]
    if not _HAS_ZONEINFO:
        print("WARNING: zoneinfo not available. Install tzdata: python -m pip install tzdata")
        return "+00:00"
    h, mn, s = (int(x) for x in time_str.split(":"))
    dt = datetime(int(y), int(mo), int(d), h, mn, s, tzinfo=ZoneInfo(iana))
    offset = dt.utcoffset()
    total_minutes = int(offset.total_seconds() / 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


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


def build_datetime_str(y, mo, d, time_str, timezone):
    tz = timezone or ""
    return f"{y}:{mo}:{d} {time_str}{tz}"


def main():
    parser = argparse.ArgumentParser(
        description="Set image/video dates from filename (format: YYYYMMDD_anything)."
    )
    parser.add_argument("folder", help="Folder containing files to update")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes written")
    parser.add_argument("--recursive", action="store_true", help="Process subfolders too")
    parser.add_argument("--time", default="12:00:00", help="Time to set (default: 12:00:00)")
    parser.add_argument("--timezone", default=None, help="UTC offset e.g. +02:00")
    parser.add_argument("--city", default=None, help="City for DST-aware timezone e.g. cairo")
    parser.add_argument("--touch", action="store_true", help="Also update Windows file system modified date")
    parser.add_argument("--rename", action="store_true", help="Rename files to YYYYMMDD_001.ext format")
    parser.add_argument("--tbc", action="store_true", help="Add _TBC to filenames when date is uncertain")
    parser.add_argument("--exiftool", default=_DEFAULT_EXIFTOOL, help="Path to exiftool executable")
    args = parser.parse_args()

    version = check_exiftool(args.exiftool)
    print(f"exiftool {version} found.\n")

    files = find_files(args.folder, args.recursive)
    if not files:
        print("No supported image/video files found.")
        return

    # Resolve city key once (timezone may vary per file date if DST, handled per file)
    city_key = None
    if args.city:
        city_key = args.city.lower().replace(" ", "")
        if city_key not in CITY_TIMEZONES:
            print(f"ERROR: City '{args.city}' not recognised. Available cities:")
            print("  " + ", ".join(sorted(CITY_TIMEZONES.keys())))
            sys.exit(1)

    skipped = []
    # Group files by their date so we can call exiftool once per date
    date_groups: dict[str, list] = {}

    for f in files:
        result = extract_date(f.name)
        if result is None:
            skipped.append(f)
            continue
        y, mo, d = result

        if city_key:
            tz = city_to_offset(city_key, y, mo, d, args.time)
        else:
            tz = args.timezone

        datetime_str = build_datetime_str(y, mo, d, args.time, tz)
        date_groups.setdefault(datetime_str, []).append(f)

    print(f"Files found:   {len(files)}")
    print(f"Skipped (no date in name): {len(skipped)}")
    print(f"To update:     {len(files) - len(skipped)}")
    if skipped:
        print("\nSkipped files:")
        for f in skipped:
            print(f"  {f.name}")
    print()

    if not date_groups:
        print("Nothing to update.")
        return

    if args.dry_run:
        print("DRY RUN — no changes written:\n")
        for datetime_str, group in sorted(date_groups.items()):
            print(f"  → {datetime_str}")
            for f in group:
                print(f"      {f.name}")
        return

    total_updated = 0
    for datetime_str, group in sorted(date_groups.items()):
        exif_args = [
            args.exiftool,
            f"-DateTimeOriginal={datetime_str}",
            f"-CreateDate={datetime_str}",
            f"-ModifyDate={datetime_str}",
            f"-TrackCreateDate={datetime_str}",
            f"-TrackModifyDate={datetime_str}",
            f"-MediaCreateDate={datetime_str}",
            f"-MediaModifyDate={datetime_str}",
            "-overwrite_original",
        ]
        if not args.touch:
            exif_args.append("-P")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
            tmp.write("\n".join(str(f) for f in group))
            tmp_path = tmp.name

        try:
            result = subprocess.run(exif_args + ["-@", tmp_path], capture_output=True, text=True)
        finally:
            os.unlink(tmp_path)

        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)

        if args.touch:
            m = re.match(r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})([+-]\d{2}:\d{2})?", datetime_str)
            if m:
                y2, mo2, d2, h2, mn2, s2 = (int(m.group(i)) for i in range(1, 7))
                tz_str = m.group(7)
                if tz_str:
                    sign = 1 if tz_str[0] == "+" else -1
                    tz_h, tz_m = int(tz_str[1:3]), int(tz_str[4:6])
                    tz = dt_timezone(timedelta(hours=sign * tz_h, minutes=sign * tz_m))
                else:
                    tz = dt_timezone.utc
                ts = datetime(y2, mo2, d2, h2, mn2, s2, tzinfo=tz).timestamp()
                for f in group:
                    os.utime(f, (ts, ts))

        total_updated += len(group)

    if args.touch:
        print(f"File system timestamps updated for {total_updated} file(s).")
    print(f"\nDone. {total_updated} file(s) updated.")

    if args.rename:
        suffix = "_TBC" if args.tbc else ""
        print()
        for datetime_str, group in sorted(date_groups.items()):
            m = re.match(r"(\d{4}):(\d{2}):(\d{2})", datetime_str)
            if not m:
                continue
            date_prefix = f"{m.group(1)}{m.group(2)}{m.group(3)}"
            width = max(3, len(str(len(group))))
            for i, f in enumerate(group, start=1):
                new_name = f"{date_prefix}_{i:0{width}}{suffix}{f.suffix.lower()}"
                new_path = f.parent / new_name
                print(f"  {f.name} → {new_name}")
                f.rename(new_path)


if __name__ == "__main__":
    main()
