# Photo Date Update

A set of Python scripts to manage, date, rename, and deduplicate image and video files using [ExifTool](https://exiftool.org).

Useful for scanned photos, old imports, WhatsApp exports, or any files where the date is wrong, missing, or the filenames are inconsistent.

---

## Requirements

- **Python 3.9+**
- **ExifTool** — download the Windows Executable from https://exiftool.org, rename it to `exiftool.exe`, and place it in the `exiftool/` folder inside this project

Install the timezone package (required for DST-aware city support):
```
python -m pip install tzdata
```

---

## Scripts

### 1. `redate.py` — Set a date you specify

Use this when you know the date and want to apply it to all files in a folder.

```
python redate.py <folder or file> <date> [options]
```

**Date formats:**
- `YYYY-MM-DD` — exact date, e.g. `2003-08-01`
- `YYYY-MM` — year and month only, e.g. `2003-08` (day defaults to 01, or use `--day`)

**Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview changes without writing anything |
| `--recursive` | Also process files in subfolders |
| `--day N` | Day to use when date is YYYY-MM (default: 1) |
| `--time HH:MM:SS` | Time to set on all files (default: 12:00:00) |
| `--city NAME` | City name for automatic DST-aware timezone (see city list below) |
| `--timezone +HH:MM` | Manual UTC offset e.g. `+02:00` or `-05:00` |
| `--touch` | Also update the Windows file system "Date Modified" |
| `--rename` | Rename files to `YYYYMMDD_001.ext` format |
| `--tbc` | Add `_TBC` suffix to renamed files when date is uncertain |

**Examples:**

```powershell
# Basic — set all files in a folder to a specific date
python redate.py "D:\Photos\1996 School" 1996-11-22

# With city timezone and time
python redate.py "D:\Photos\2003 Sharm" 2003-08-01 --city sharmelsheikh --time 15:00:00

# Preview first, then apply
python redate.py "D:\Photos\Old Scans" 2005-03 --dry-run
python redate.py "D:\Photos\Old Scans" 2005-03 --city cairo --touch --rename

# Uncertain date — adds _TBC to filenames
python redate.py "D:\Photos\Unknown" 1995-06 --city cairo --rename --tbc

# Single file
python redate.py "D:\Photos\scan001.jpg" 1998-12-25 --city dubai --time 18:00:00 --touch

# Year and month only, set day to 15
python redate.py "D:\Photos\Old Scans" 2005-03 --day 15 --city london
```

---

### 2. `redate_from_name.py` — Read the date from the filename

Use this when your files are already named with a date. The date is extracted automatically from the filename.

**Supported filename formats:**
- `YYYYMMDD_anything.jpg` — e.g. `20230915_0042.jpg`
- `IMG-YYYYMMDD-WA00xxx.jpg` — WhatsApp images
- `VID-YYYYMMDD-WA00xxx.mp4` — WhatsApp videos

```
python redate_from_name.py <folder> [options]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview changes without writing anything |
| `--recursive` | Also process files in subfolders |
| `--time HH:MM:SS` | Time to set on all files (default: 12:00:00) |
| `--city NAME` | City name for automatic DST-aware timezone (see city list below) |
| `--timezone +HH:MM` | Manual UTC offset e.g. `+02:00` |
| `--touch` | Also update the Windows file system "Date Modified" |
| `--rename` | Rename files to `YYYYMMDD_001.ext` format (numbering resets per date) |
| `--tbc` | Add `_TBC` suffix to renamed files when date is uncertain |

**Examples:**

```powershell
# Preview what dates will be extracted from filenames
python redate_from_name.py "D:\Photos\WhatsApp" --dry-run

# Apply with Cairo timezone
python redate_from_name.py "D:\Photos\WhatsApp" --city cairo

# Apply with timezone, time, touch, and rename
python redate_from_name.py "D:\Photos\WhatsApp" --city dubai --time 10:00:00 --touch --rename

# Include subfolders
python redate_from_name.py "D:\Photos" --recursive --city cairo --dry-run
```

Files that don't match any supported format are skipped and listed at the end.

---

### 3. `rename_to_exif.py` — Rename files to match their EXIF date

Use this when files have inconsistent or wrong names but correct EXIF dates. Reads the `DateTimeOriginal` from each file and renames it to `YYYYMMDD_NNN.ext`. Numbering continues from whatever already exists in the folder for that date to avoid conflicts.

```
python rename_to_exif.py <folder> [options]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview renames without applying them |
| `--recursive` | Also process files in subfolders |

**Examples:**

```powershell
# Preview renames
python rename_to_exif.py "D:\Photos\2023" --dry-run

# Apply renames
python rename_to_exif.py "D:\Photos\2023"

# Include subfolders
python rename_to_exif.py "D:\Photos" --recursive --dry-run
```

Files with no EXIF date and files already correctly named are skipped and listed.

---

### 4. `find_duplicates.py` — Find and remove duplicate files

Detects duplicate image/video files by content checksum. Two files with identical checksums are guaranteed to be the same file regardless of filename, date, or location.

Works in two modes:

**Single folder** — finds duplicates within one folder:
```
python find_duplicates.py <folder> [options]
```

**Two folder** — finds files in folder2 that already exist in folder1 (folder1 is the master and is never touched):
```
python find_duplicates.py <folder1> --compare <folder2> [options]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Report duplicates without moving or deleting anything |
| `--move PATH` | Move duplicates to this folder (recommended over --delete) |
| `--delete` | Permanently delete duplicates |
| `--compare PATH` | Second folder to compare against the first |
| `--no-recursive` | Only scan top-level folder (default: recursive) |

**Examples:**

```powershell
# Always preview first
python find_duplicates.py "D:\Photos" --dry-run

# Move duplicates to a review folder (safest)
python find_duplicates.py "D:\Photos" --move "D:\Photos\duplicates"

# Delete duplicates permanently
python find_duplicates.py "D:\Photos" --delete

# Compare two folders — only duplicates in Downloads are flagged
python find_duplicates.py "D:\Photos\Master" --compare "D:\Photos\Downloads" --dry-run
python find_duplicates.py "D:\Photos\Master" --compare "D:\Photos\Downloads" --move "D:\Photos\dupes"
```

When duplicates are found within a single folder, the file with the shortest/simplest name is kept.

---

## What dates get updated

`redate.py` and `redate_from_name.py` update the following metadata fields:

| Field | Used by |
|-------|---------|
| `DateTimeOriginal` | Google Photos, Apple Photos, most apps |
| `CreateDate` | General creation date |
| `ModifyDate` | Last modified date in EXIF |
| `TrackCreateDate / TrackModifyDate` | Video track metadata |
| `MediaCreateDate / MediaModifyDate` | Video media metadata |

With `--touch`, the Windows file system "Date Modified" is also updated.

---

## Supported file types

**Images:** `.jpg` `.jpeg` `.png` `.heic` `.heif` `.tiff` `.tif` `.bmp` `.gif` `.webp`

**Videos:** `.mp4` `.mov` `.avi` `.mkv` `.m4v` `.3gp` `.wmv` `.mts` `.m2ts`

---

## City list

The `--city` flag automatically sets the correct UTC offset including daylight saving time for the date provided.

| City | Usage |
|------|-------|
| **Africa** | |
| Cairo | `--city cairo` |
| Alexandria | `--city alexandria` |
| Sharm el Sheikh | `--city sharmelsheikh` |
| Johannesburg | `--city johannesburg` |
| Nairobi | `--city nairobi` |
| Lagos | `--city lagos` |
| Casablanca | `--city casablanca` |
| Accra | `--city accra` |
| **Middle East** | |
| Dubai | `--city dubai` |
| Abu Dhabi | `--city abudhabi` |
| Sharjah | `--city sharjah` |
| Riyadh | `--city riyadh` |
| Doha | `--city doha` |
| Kuwait | `--city kuwait` |
| Beirut | `--city beirut` |
| Amman | `--city amman` |
| Jerusalem | `--city jerusalem` |
| Tehran | `--city tehran` |
| **Europe** | |
| London | `--city london` |
| Paris | `--city paris` |
| Berlin | `--city berlin` |
| Munich | `--city munich` |
| Kitzbuehel | `--city kitzbuehel` |
| Rome | `--city rome` |
| Madrid | `--city madrid` |
| Amsterdam | `--city amsterdam` |
| Brussels | `--city brussels` |
| Zurich | `--city zurich` |
| Vienna | `--city vienna` |
| Stockholm | `--city stockholm` |
| Oslo | `--city oslo` |
| Copenhagen | `--city copenhagen` |
| Helsinki | `--city helsinki` |
| Athens | `--city athens` |
| Istanbul | `--city istanbul` |
| Reykjavik | `--city reykjavik` |
| Moscow | `--city moscow` |
| **Americas** | |
| New York | `--city newyork` |
| Boston | `--city boston` |
| Miami | `--city miami` |
| Toronto | `--city toronto` |
| Montreal | `--city montreal` |
| Atlanta | `--city atlanta` |
| Chicago | `--city chicago` |
| Houston | `--city houston` |
| Dallas | `--city dallas` |
| Denver | `--city denver` |
| Albuquerque | `--city albuquerque` |
| Phoenix | `--city phoenix` |
| Salt Lake City | `--city saltlakecity` |
| Los Angeles | `--city losangeles` |
| San Francisco | `--city sanfrancisco` |
| San Jose | `--city sanjose` |
| Seattle | `--city seattle` |
| Vancouver | `--city vancouver` |
| Anchorage | `--city anchorage` |
| Honolulu | `--city honolulu` |
| Mexico City | `--city mexico` |
| Bogota | `--city bogota` |
| Lima | `--city lima` |
| Santiago | `--city santiago` |
| Buenos Aires | `--city buenosaires` |
| Sao Paulo | `--city saopaulo` |
| **Asia / Pacific** | |
| Mumbai | `--city mumbai` |
| Delhi | `--city delhi` |
| Kolkata | `--city kolkata` |
| Karachi | `--city karachi` |
| Islamabad | `--city islamabad` |
| Dhaka | `--city dhaka` |
| Colombo | `--city colombo` |
| Bangkok | `--city bangkok` |
| Jakarta | `--city jakarta` |
| Singapore | `--city singapore` |
| Kuala Lumpur | `--city kualalumpur` |
| Hong Kong | `--city hongkong` |
| Beijing | `--city beijing` |
| Shanghai | `--city shanghai` |
| Taipei | `--city taipei` |
| Tokyo | `--city tokyo` |
| Seoul | `--city seoul` |
| Sydney | `--city sydney` |
| Melbourne | `--city melbourne` |
| Auckland | `--city auckland` |

---

## Tips

- Always run with `--dry-run` first to preview changes before applying them
- Use `--move` instead of `--delete` the first time — safer to review before permanently removing files
- If a file fails due to corrupted EXIF, open it in Paint, Save As a new file, then retry
- `--tbc` only works together with `--rename`
- City names are case-insensitive and spaces are ignored (`--city new york` and `--city newyork` both work)
- Press **Ctrl+C** in PowerShell to stop a running script at any time
