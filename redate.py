#!/usr/bin/env python3
"""
redate.py — Batch update created/modified dates on image and video files.

Usage:
    python redate.py <folder> <date> [options]

Date formats:
    YYYY-MM-DD   exact date (time set to 12:00:00)
    YYYY-MM      year and month only (day defaults to 01)

Options:
    --dry-run        Preview changes without writing anything
    --recursive      Also process subfolders
    --day N          When using YYYY-MM format, set day to N (default: 1)
    --time HH:MM:SS  Set a specific time (default: 12:00:00)
    --exiftool PATH  Path to exiftool executable (default: exiftool)

Examples:
    python redate.py "D:/Photos/2019 Trip" 2019-07-15
    python redate.py "D:/Photos/Old Scans" 2005-03 --recursive
    python redate.py "D:/Photos/Old Scans" 2005-03 --day 15 --dry-run
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

# Default exiftool path relative to this script
_SCRIPT_DIR = Path(__file__).parent
_DEFAULT_EXIFTOOL = str(_SCRIPT_DIR / "exiftool" / "exiftool.exe")

# Maps city name (lowercase, no spaces) to IANA timezone name for DST-aware offsets
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


def city_to_offset(city_key, date_str, day, time_str):
    """Return UTC offset string (e.g. +02:00) for a city on a given date, DST-aware."""
    iana = CITY_TIMEZONES[city_key]

    if not _HAS_ZONEINFO:
        print("WARNING: zoneinfo not available (Python 3.9+ required for DST). Using fixed offsets.")
        # Fallback fixed offsets
        fallback = {
            "Europe/London": "+00:00", "Europe/Paris": "+01:00", "Europe/Berlin": "+01:00",
            "Europe/Vienna": "+01:00", "America/New_York": "-05:00", "America/Chicago": "-06:00",
            "America/Denver": "-07:00", "America/Los_Angeles": "-08:00",
        }
        return fallback.get(iana, "+00:00")

    # Parse the date to determine DST
    exact = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if exact:
        y, m, d = int(exact.group(1)), int(exact.group(2)), int(exact.group(3))
    else:
        partial = re.fullmatch(r"(\d{4})-(\d{2})", date_str)
        y, m, d = int(partial.group(1)), int(partial.group(2)), day

    h, mn, s = (int(x) for x in time_str.split(":"))
    dt = datetime(y, m, d, h, mn, s, tzinfo=ZoneInfo(iana))
    offset = dt.utcoffset()
    total_minutes = int(offset.total_seconds() / 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".bmp", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".wmv", ".mts", ".m2ts"}
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS


def parse_date(date_str, day=1, time_str="12:00:00", timezone=None):
    """Parse YYYY-MM-DD or YYYY-MM into an exiftool-compatible datetime string."""
    tz = timezone or ""

    exact = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if exact:
        y, m, d = exact.groups()
        return f"{y}:{m}:{d} {time_str}{tz}"

    partial = re.fullmatch(r"(\d{4})-(\d{2})", date_str)
    if partial:
        y, m = partial.groups()
        return f"{y}:{m}:{day:02d} {time_str}{tz}"

    print(f"ERROR: Unrecognised date format '{date_str}'. Use YYYY-MM-DD or YYYY-MM.")
    sys.exit(1)


def find_files(folder, recursive):
    path = Path(folder)
    if path.is_file():
        if path.suffix.lower() not in ALL_EXTS:
            print(f"ERROR: '{path.name}' is not a supported image/video file.")
            sys.exit(1)
        return [path]
    if not path.is_dir():
        print(f"ERROR: '{path}' is not a file or directory.")
        sys.exit(1)
    pattern = "**/*" if recursive else "*"
    files = [f for f in path.glob(pattern) if f.is_file() and f.suffix.lower() in ALL_EXTS]
    return sorted(files)


def check_exiftool(exiftool_path):
    try:
        result = subprocess.run(
            [exiftool_path, "-ver"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    print(f"ERROR: exiftool not found at '{exiftool_path}'.")
    print("Download from https://exiftool.org and ensure it's on your PATH.")
    sys.exit(1)


def datetime_str_to_timestamp(datetime_str):
    """Convert exiftool datetime string (YYYY:MM:DD HH:MM:SS+HH:MM) to a Unix timestamp."""
    # Strip timezone offset if present
    m = re.match(r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})([+-]\d{2}:\d{2})?", datetime_str)
    if not m:
        return None
    y, mo, d, h, mn, s = (int(m.group(i)) for i in range(1, 7))
    tz_str = m.group(7)
    if tz_str:
        sign = 1 if tz_str[0] == "+" else -1
        tz_h, tz_m = int(tz_str[1:3]), int(tz_str[4:6])
        tz = dt_timezone(timedelta(hours=sign * tz_h, minutes=sign * tz_m))
    else:
        tz = dt_timezone.utc
    dt = datetime(y, mo, d, h, mn, s, tzinfo=tz)
    return dt.timestamp()


def update_dates(files, datetime_str, exiftool_path, dry_run, touch=False):
    if not files:
        print("No supported image/video files found.")
        return

    print(f"{'DRY RUN — ' if dry_run else ''}Setting date to: {datetime_str}")
    if touch:
        print("File system timestamps will also be updated (--touch).")
    print(f"Files found: {len(files)}\n")

    args = [
        exiftool_path,
        f"-DateTimeOriginal={datetime_str}",
        f"-CreateDate={datetime_str}",
        f"-ModifyDate={datetime_str}",
        f"-TrackCreateDate={datetime_str}",
        f"-TrackModifyDate={datetime_str}",
        f"-MediaCreateDate={datetime_str}",
        f"-MediaModifyDate={datetime_str}",
        "-overwrite_original",
    ]
    if not touch:
        args.append("-P")  # preserve filesystem timestamps

    if dry_run:
        for f in files:
            print(f"  [dry run] {f}")
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write("\n".join(str(f) for f in files))
        tmp_path = tmp.name

    try:
        result = subprocess.run(args + ["-@", tmp_path], capture_output=True, text=True)
    finally:
        os.unlink(tmp_path)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print("exiftool reported errors (see above).")
        sys.exit(result.returncode)

    # Optionally update filesystem modified/access time
    if touch:
        ts = datetime_str_to_timestamp(datetime_str)
        if ts:
            for f in files:
                os.utime(f, (ts, ts))
            print(f"File system timestamps updated for {len(files)} file(s).")

    print(f"\nDone. {len(files)} file(s) updated.")


def rename_files(files, datetime_str, dry_run, tbc=False):
    """Rename files to YYYYMMDD_001.ext or YYYYMMDD_001_TBC.ext format."""
    m = re.match(r"(\d{4}):(\d{2}):(\d{2})", datetime_str)
    if not m:
        print("ERROR: Could not parse date for renaming.")
        return
    date_prefix = f"{m.group(1)}{m.group(2)}{m.group(3)}"
    suffix = "_TBC" if tbc else ""
    width = max(3, len(str(len(files))))

    print(f"\n{'DRY RUN — ' if dry_run else ''}Renaming {len(files)} file(s) to {date_prefix}_NNN{suffix} format:")
    for i, f in enumerate(files, start=1):
        new_name = f"{date_prefix}_{i:0{width}}{suffix}{f.suffix.lower()}"
        new_path = f.parent / new_name
        print(f"  {f.name} → {new_name}")
        if not dry_run:
            f.rename(new_path)


def main():
    parser = argparse.ArgumentParser(
        description="Batch update image/video created dates using exiftool."
    )
    parser.add_argument("folder", help="Folder containing files to update")
    parser.add_argument("date", help="Date as YYYY-MM-DD or YYYY-MM")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes written")
    parser.add_argument("--recursive", action="store_true", help="Process subfolders too")
    parser.add_argument("--day", type=int, default=1, help="Day to use when date is YYYY-MM (default: 1)")
    parser.add_argument("--time", default="12:00:00", help="Time to set (default: 12:00:00)")
    parser.add_argument("--timezone", default=None, help="Timezone offset e.g. +02:00 or -05:00")
    parser.add_argument("--city", default=None, help="City name to set timezone e.g. cairo, dubai, denver")
    parser.add_argument("--touch", action="store_true", help="Also update Windows file system modified date")
    parser.add_argument("--rename", action="store_true", help="Rename files to YYYYMMDD_001.ext format")
    parser.add_argument("--tbc", action="store_true", help="Add _TBC to filenames when date is uncertain")
    parser.add_argument("--exiftool", default=_DEFAULT_EXIFTOOL, help="Path to exiftool executable")
    args = parser.parse_args()

    # Resolve timezone from city if provided
    timezone = args.timezone
    if args.city:
        key = args.city.lower().replace(" ", "")
        if key not in CITY_TIMEZONES:
            print(f"ERROR: City '{args.city}' not recognised. Available cities:")
            print("  " + ", ".join(sorted(CITY_TIMEZONES.keys())))
            sys.exit(1)
        timezone = city_to_offset(key, args.date, args.day, args.time)
        print(f"City '{args.city}' ({CITY_TIMEZONES[key]}) → UTC offset {timezone} on {args.date}")

    version = check_exiftool(args.exiftool)
    print(f"exiftool {version} found.\n")

    datetime_str = parse_date(args.date, day=args.day, time_str=args.time, timezone=timezone)
    files = find_files(args.folder, args.recursive)
    update_dates(files, datetime_str, args.exiftool, args.dry_run, touch=args.touch)
    if args.rename:
        rename_files(files, datetime_str, args.dry_run, tbc=args.tbc)


if __name__ == "__main__":
    main()
