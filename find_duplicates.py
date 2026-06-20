#!/usr/bin/env python3
"""
find_duplicates.py — Find duplicate image/video files by content checksum.

Two files with identical checksums are guaranteed to be the same file
regardless of filename, date, or location.

Single folder mode — finds duplicates within one folder:
    python find_duplicates.py <folder> [options]

Two folder mode — finds files in folder2 that already exist in folder1:
    python find_duplicates.py <folder1> --compare <folder2> [options]

    In two-folder mode, folder1 is the MASTER (kept untouched).
    Only duplicates found in folder2 are moved or deleted.

Options:
    --compare PATH   Second folder to compare against the first
    --dry-run        Report duplicates without moving or deleting anything
    --move PATH      Move duplicates to this folder instead of deleting
    --delete         Delete duplicates (keeps one copy — the first found)
    --no-recursive   Only scan top-level folder (default: recursive)

Examples:
    # Within one folder
    python find_duplicates.py "C:/Photos" --dry-run
    python find_duplicates.py "C:/Photos" --move "C:/Photos/duplicates"
    python find_duplicates.py "C:/Photos" --delete

    # Between two folders (duplicates in folder2 that exist in folder1)
    python find_duplicates.py "C:/Photos/Master" --compare "C:/Photos/Downloads" --dry-run
    python find_duplicates.py "C:/Photos/Master" --compare "C:/Photos/Downloads" --move "C:/Photos/dupes"
    python find_duplicates.py "C:/Photos/Master" --compare "C:/Photos/Downloads" --delete
"""

import argparse
import hashlib
import sys
import shutil
from pathlib import Path
from collections import defaultdict

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".bmp", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".wmv", ".mts", ".m2ts"}
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS


def checksum(filepath, chunk_size=65536):
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def find_files(folder, recursive):
    folder = Path(folder)
    if not folder.is_dir():
        print(f"ERROR: '{folder}' is not a directory.")
        sys.exit(1)
    pattern = "**/*" if recursive else "*"
    return sorted(f for f in folder.glob(pattern) if f.is_file() and f.suffix.lower() in ALL_EXTS)


def build_checksum_map(files, label=""):
    """Return {checksum: [paths]} for a list of files."""
    print(f"Checksumming {len(files)} file(s){' in ' + label if label else ''}...")
    seen = defaultdict(list)
    for i, f in enumerate(files, 1):
        if i % 50 == 0 or i == len(files):
            print(f"  {i}/{len(files)}...", end="\r")
        try:
            h = checksum(f)
            seen[h].append(f)
        except (OSError, IOError) as e:
            print(f"  WARNING: Could not read {f.name} — {e}")
    print()
    return seen


def handle_dupe(d, i, move_folder, dry_run, delete):
    if dry_run:
        return
    if delete:
        d.unlink()
        print(f"          → deleted")
    elif move_folder:
        dest = move_folder / d.name
        if dest.exists():
            dest = move_folder / f"{d.stem}_{i}{d.suffix}"
        shutil.move(str(d), str(dest))
        print(f"          → moved to {dest.name}")


def run_single_folder(args, recursive):
    files = find_files(args.folder, recursive)
    if not files:
        print("No supported image/video files found.")
        return

    checksum_map = build_checksum_map(files)
    duplicate_groups = [g for g in checksum_map.values() if len(g) > 1]

    if not duplicate_groups:
        print("No duplicates found.")
        return

    total_dupes = sum(len(g) - 1 for g in duplicate_groups)
    print(f"Found {len(duplicate_groups)} group(s) of duplicates ({total_dupes} extra file(s)).\n")

    move_folder = None
    if args.move:
        move_folder = Path(args.move)
        if not args.dry_run:
            move_folder.mkdir(parents=True, exist_ok=True)

    base = Path(args.folder)
    for i, group in enumerate(duplicate_groups, 1):
        # Keep file with shortest/simplest name
        keeper = sorted(group, key=lambda f: (len(f.name), f.name))[0]
        dupes = [f for f in group if f != keeper]

        print(f"Group {i}:")
        print(f"  KEEP: {keeper.relative_to(base)}")
        for d in dupes:
            print(f"  DUPE: {d.relative_to(base)}")
            handle_dupe(d, i, move_folder, args.dry_run, args.delete)
        print()

    if args.dry_run:
        print(f"Dry run complete. {total_dupes} duplicate(s) would be removed.")
    elif args.delete:
        print(f"Done. {total_dupes} duplicate(s) deleted.")
    elif args.move:
        print(f"Done. {total_dupes} duplicate(s) moved to '{args.move}'.")


def run_two_folders(args, recursive):
    folder1 = Path(args.folder)
    folder2 = Path(args.compare)

    files1 = find_files(folder1, recursive)
    files2 = find_files(folder2, recursive)

    if not files1:
        print(f"No files found in master folder: {folder1}")
        return
    if not files2:
        print(f"No files found in compare folder: {folder2}")
        return

    map1 = build_checksum_map(files1, label=f"master ({folder1.name})")
    map2 = build_checksum_map(files2, label=f"compare ({folder2.name})")

    # Find checksums present in both folders
    master_hashes = set(map1.keys())
    dupes_in_folder2 = {h: paths for h, paths in map2.items() if h in master_hashes}

    if not dupes_in_folder2:
        print("No duplicates found between the two folders.")
        return

    total_dupes = sum(len(p) for p in dupes_in_folder2.values())
    print(f"\nFound {total_dupes} file(s) in '{folder2.name}' that already exist in '{folder1.name}'.\n")

    move_folder = None
    if args.move:
        move_folder = Path(args.move)
        if not args.dry_run:
            move_folder.mkdir(parents=True, exist_ok=True)

    for i, (h, dupes) in enumerate(dupes_in_folder2.items(), 1):
        master_copy = map1[h][0]
        print(f"Group {i}:")
        print(f"  MASTER: {master_copy.relative_to(folder1)}")
        for d in dupes:
            print(f"  DUPE:   {d.relative_to(folder2)}")
            handle_dupe(d, i, move_folder, args.dry_run, args.delete)
        print()

    if args.dry_run:
        print(f"Dry run complete. {total_dupes} duplicate(s) in '{folder2.name}' would be removed.")
    elif args.delete:
        print(f"Done. {total_dupes} duplicate(s) deleted from '{folder2.name}'.")
    elif args.move:
        print(f"Done. {total_dupes} duplicate(s) moved to '{args.move}'.")


def main():
    parser = argparse.ArgumentParser(
        description="Find duplicate image/video files by checksum."
    )
    parser.add_argument("folder", help="Folder to scan (or master folder when using --compare)")
    parser.add_argument("--compare", metavar="PATH", help="Second folder to compare against the first")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no files moved or deleted")
    parser.add_argument("--move", metavar="PATH", help="Move duplicates to this folder")
    parser.add_argument("--delete", action="store_true", help="Delete duplicate files")
    parser.add_argument("--no-recursive", action="store_true", help="Only scan top-level folder")
    args = parser.parse_args()

    if args.delete and args.move:
        print("ERROR: use either --delete or --move, not both.")
        sys.exit(1)

    if not args.dry_run and not args.delete and not args.move:
        print("No action specified. Use --dry-run to preview, --move PATH to move duplicates, or --delete to delete them.")
        sys.exit(1)

    recursive = not args.no_recursive

    if args.compare:
        run_two_folders(args, recursive)
    else:
        run_single_folder(args, recursive)


if __name__ == "__main__":
    main()
