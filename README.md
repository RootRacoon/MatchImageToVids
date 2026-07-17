# Video Face Sort

Scan a batch of videos and sort them by **who appears in them**, matching against
your own reference photos. Built for wedding / event footage (e.g. find every clip
with the bride or groom).

It samples a few frames spread across each video (not the whole thing) and compares
faces to your reference images, so it's fast even on lots of long clips.

---

## Folder layout

```
YourFolder\
├── run.bat                  <- double-click this
├── sort_videos_by_face.py
├── search_pics\             <- put your reference photos here
├── extensions.txt           <- which video types to scan (auto-created)
├── negation.txt             <- paths to SKIP (auto-created)
├── target.txt               <- paths to SEARCH; empty = all drives (auto-created)
├── results.txt              <- readable output (created after a run)
├── results.csv              <- same data as a spreadsheet
└── sorted\                  <- matched videos copied into per-person folders
```

---

## Quick start (one-click)

1. Put **reference photos** in `search_pics\`. The filename is the person's name
   (`Bride.jpg`, `Groom.jpg`). Group photos are fine — every face in them is used.
2. **Double-click `run.bat`** and answer the questions:
   - **Date filter** — single day, a date range (`YYYY-MM-DD-HH`), or none.
   - **Footage type** — Normal, or Sparse/short (more lenient) for short clips.
   - **Copy matches?** — yes/no.
3. Done — `results.txt` opens automatically.

Where it looks for videos:
- If `target.txt` has paths → it scans those (files or folders).
- If `target.txt` is empty → it searches **all drives** (via Everything if installed).

On the **first run only** it creates a Python environment, installs dependencies,
and downloads the face model (~300 MB, needs internet once). Every run after is fast.

### The three config files (plain text, edit any time)

| File | What goes in it |
|------|-----------------|
| `extensions.txt` | Video extensions to scan, one per line (no dots) |
| `negation.txt`   | Paths to **skip**, one per line (backups, proxies, …) |
| `target.txt`     | Paths to **search**, one per line — leave empty for all drives |

They're created automatically with examples the first time you run.

---

## What you get

`results.txt` (grouped by person):

```
=== Bride  (12 video(s)) ===
  D:\...\videos\clip001.mp4
      matched image=Bride_2.jpg  hits=6  best=0.63  first@00:00:03
```

- **matched image** = the exact file in `search_pics` that matched best
- **hits** = how many sampled frames matched
- **best** = match confidence (higher = more certain)
- **first** = timestamp the person first appears

`results.csv` has the same info with a `matched_image` column, and `sorted\Bride\`,
`sorted\Groom\` contain copies of the matching videos (originals are never touched).

---

## Configuration (the three text files)

Instead of editing the script, tune these plain-text files (auto-created on first run):

- **`extensions.txt`** — one extension per line, no dots.
- **`negation.txt`** — one path per line to skip. Anything under it is ignored.
- **`target.txt`** — one path per line to search (files or folders). Leave it empty
  (comments only) to search **all drives**.

Lines starting with `#` are ignored, so you can keep notes/examples in them.

### Fastest workflow (all drives by date)

Install [Everything](https://www.voidtools.com/) + its `es` command-line tool, put
your photos in `search_pics\`, leave `target.txt` empty, double-click `run.bat`, and
choose a date range. It finds matching videos across every drive instantly and sorts
them. No paths to type, no copying footage around.

---

## Requirements

- Windows
- Python 3.10+ from https://www.python.org/downloads/ — during install **tick
  "Add Python to PATH"**.
- Internet connection on the first run (to install packages + download the model).
- Optional: an NVIDIA GPU for a big speedup (see below).

---

## Running manually (advanced / options)

You can run the Python script directly instead of `run.bat`:

```powershell
# activate the environment first (created by run.bat)
.venv\Scripts\activate

# basic run (the videos\ folder)
py sort_videos_by_face.py --videos "videos" --known "search_pics" --copy

# scan videos found elsewhere (a folder on another drive)
py sort_videos_by_face.py --videos "D:\Footage" --known "search_pics" --copy

# run against specific files AND/OR folders (folders get scanned)
py sort_videos_by_face.py --files "D:\a.mp4" "E:\ShootDay1" --known "search_pics" --copy

# search EVERY drive on the system
py sort_videos_by_face.py --all --known "search_pics" --copy

# DATE RANGE across all drives via Everything (fastest, no paths needed)
py sort_videos_by_face.py --from 2025-01-01 --to 2025-06-30 --known "search_pics" --copy

# exclude folders from any run
py sort_videos_by_face.py --all --exclude "D:\Backups" "E:\Proxies" --copy

# feed a list of paths (e.g. exported from the Everything search tool)
py sort_videos_by_face.py --videos found_videos.txt --known "search_pics" --copy

# use only specific extensions
py sort_videos_by_face.py --videos "videos" --ext "mp4,mov,mxf" --copy

# be more thorough (more frames per video)
py sort_videos_by_face.py --videos "videos" --multiplier 2 --copy

# use an NVIDIA GPU
py sort_videos_by_face.py --videos "videos" --gpu --copy
```

### All options

`--wizard` is the interactive mode `run.bat` uses (reads the 3 text files, asks the
questions). Otherwise pick one input source: `--from/--to`, `--videos`, `--files`, or `--all`.

| Option          | Default        | What it does |
|-----------------|----------------|--------------|
| `--wizard`      | —              | Interactive: read config files + ask date/footage questions |
| `--from`/`--to` | —              | Date range; uses Everything to find videos on all drives |
| `--date-field`  | `modified`     | `modified` (recording date) or `created` (copy date) |
| `--es-path`     | —              | Path to `es.exe` if not on PATH |
| `--videos`      | —              | Folder of videos, OR a `.txt`/`.csv` list of video paths |
| `--files`       | —              | Run against these path(s) only — each can be a file or a folder |
| `--all`         | off            | Search every drive on the system for videos |
| `--exclude`     | —              | Path(s) to skip — files/folders under these are ignored |
| `--known`       | `search_pics`  | Folder of reference images (filename = person name) |
| `--ext`         | built-in list  | Comma-separated extensions to scan, e.g. `mp4,mov,mkv` |
| `--multiplier`  | `1.0`          | Scales how many frames are checked (2 = twice as many) |
| `--samples`     | `0` (auto)     | Force a fixed frame count instead of auto-by-length |
| `--threshold`   | `0.45`         | Match strictness (0.35 loose .. 0.55 strict) |
| `--min-hits`    | `2`            | Person must appear in this many frames to count |
| `--no-stop-early` | off          | Check all frames even after everyone is found |
| `--copy`        | off            | Copy matches into `sorted\<Person>\` |
| `--report`      | `report.csv`   | CSV output path |
| `--txt`         | `results.txt`  | Text output path |
| `--gpu`         | off            | Use NVIDIA GPU if available |

---

## Supported video formats

By default: `mp4, mov, m2ts, mts, avi, mkv, mxf, wmv, flv, webm, m4v, mpg, mpeg, 3gp, ts`.

This covers all common camera and editor formats. To scan others, add them to the
`EXTS` line in `run.bat` (or use `--ext`).

---

## Tips

- **Test on a few videos first** to check your reference photos and threshold before
  running the whole batch.
- Too many false matches? Raise `--threshold` (e.g. `0.5`) or `--min-hits` (e.g. `3`).
- Missing real matches? Lower `--threshold` (e.g. `0.4`) or add more reference photos
  of that person.
- Long ceremony clips: the frame count auto-scales with length; use `--multiplier 2`
  for extra thoroughness.

---

## Troubleshooting

- **"Python is not installed"** — install from python.org and tick *Add Python to PATH*.
- **Dependency install failed** — check internet and re-run `run.bat`.
- **A reference photo is ignored** — the console prints `no face found in <file>`; use a
  clearer, front-facing photo.
- **Everything shows as no match** — timestamps/thresholds aside, confirm the videos are
  actually in `videos\` and use an extension listed in `EXTS`.
