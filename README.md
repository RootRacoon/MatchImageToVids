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
├── videos\                  <- put the videos to scan here
├── results.txt              <- readable output (created after a run)
├── results.csv              <- same data as a spreadsheet
└── sorted\                  <- matched videos copied into per-person folders
```

---

## Quick start (one-click)

1. Put **reference photos** in `search_pics\`. Name each file after the person:
   - `Bride.jpg`, `Groom.jpg`
   - Multiple photos of the same person: `Bride_1.jpg`, `Bride_2.jpg` (auto-grouped)
   - Use clear, front-facing photos with just that one person's face.
2. Put the **videos** to scan in `videos\`.
3. **Double-click `run.bat`.**

On the **first run only** it creates a Python environment, installs dependencies,
and downloads the face model (~300 MB, needs internet once). Every run after is fast
and works offline.

When it finishes, `results.txt` opens automatically.

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

## Configuration (edit `run.bat`)

Near the top of `run.bat`:

```bat
REM Video extensions to scan (comma-separated, no dots).
set "EXTS=mp4,mov,m2ts,mts,avi,mkv,mxf,wmv,flv,webm,m4v,mpg,mpeg,3gp,ts"

REM (1) DATE RANGE via Everything - fastest, searches all drives by date.
set "DATE_FROM="
set "DATE_TO="
set "DATE_FIELD=modified"      REM modified = recording date, created = copy date
set "ES_PATH="                 REM full path to es.exe if it's not on PATH

REM (2) If no dates: 1 = search ALL drives, 0 = only the "videos" folder.
set "SEARCH_ALL=0"

REM Paths to SKIP (semicolon-separated).
set "EXCLUDE="
```

- **EXTS** — add/remove extensions (comma-separated, no dots).
- **DATE_FROM / DATE_TO** — fill **both** (e.g. `2025-01-01`) to have Everything
  find all videos in that range across every drive automatically. Needs Everything
  + `es.exe` installed. Leave blank to skip.
- **DATE_FIELD** — `modified` (the recording date) or `created` (when copied).
- **SEARCH_ALL** — used only if no dates: `1` = sweep all drives, `0` = `videos\` folder.
- **EXCLUDE** — semicolon-separated paths to skip (e.g. `D:\Backups;E:\Proxies`).
  Any file or folder under these is ignored, in every input mode.

### Recommended workflow (fully automatic)

Install [Everything](https://www.voidtools.com/) + its `es` command-line tool, put
your photos in `search_pics\`, set `DATE_FROM`/`DATE_TO` in `run.bat`, and
double-click. No paths, no copying videos — it finds them by date across all drives
and sorts them. This is the fastest end-to-end option.

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

Pick one input source: `--from/--to`, `--videos`, `--files`, or `--all`.

| Option          | Default        | What it does |
|-----------------|----------------|--------------|
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
