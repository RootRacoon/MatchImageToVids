#!/usr/bin/env python3
"""
Sort / tag videos by which known people appear in them (facial recognition).

WORKFLOW
--------
1. Put reference photos in a folder (default: ./known_faces).
   The filename is the person's NAME:
       known_faces/Alice.jpg
       known_faces/Bob.png
   Multiple photos of the same person -> add a suffix, they get grouped:
       known_faces/Alice_1.jpg
       known_faces/Alice_2.jpg
   (Clear, front-facing photos with ONE face work best.)

2. Point --videos at either:
       - a folder of videos, OR
       - a .txt / .csv file listing video paths (e.g. exported from Everything)

3. Run. You get:
       - report.csv : which people appear in each video (+ hits & timestamp)
       - sorted/<Person>/ : copies of matching videos (with --copy)

SETUP (Windows, one time)
-------------------------
    py -m pip install insightface onnxruntime opencv-python numpy
  For an NVIDIA GPU (much faster) also:
    py -m pip install onnxruntime-gpu    # then run with --gpu

EXAMPLES
--------
    py sort_videos_by_face.py --videos "D:\\Footage"
    py sort_videos_by_face.py --videos found_videos.txt --copy --gpu
    py sort_videos_by_face.py --videos "D:\\Footage" --multiplier 2 --min-hits 3
"""

import argparse
import csv
import os
import random
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

import cv2
import numpy as np

VIDEO_EXTS = {".mp4", ".mov", ".m2ts", ".mts", ".avi", ".mkv", ".mxf",
              ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".3gp", ".ts"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# Auto sample count: ~1 frame per SECONDS_PER_SAMPLE of video, scaled by the
# --multiplier, then clamped so tiny clips still get checked and huge clips
# don't explode. e.g. at multiplier 1.0:  1min->5, 5min->10, 30min->40(cap).
SECONDS_PER_SAMPLE = 30.0
MIN_SAMPLES = 5
MAX_SAMPLES = 40


def person_name_from_filename(path):
    """Alice_1.jpg -> Alice ;  Bob (2).png -> Bob ;  Carol.jpg -> Carol"""
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"[\s_\-]*\(?\d+\)?$", "", stem)  # strip trailing number / (n)
    return stem.strip() or os.path.splitext(os.path.basename(path))[0]


def build_face_app(use_gpu):
    from insightface.app import FaceAnalysis
    import onnxruntime as ort

    avail = ort.get_available_providers()
    if use_gpu and "CUDAExecutionProvider" in avail:
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        print("Using GPU (CUDA).")
    else:
        if use_gpu:
            print("GPU requested but CUDA provider not available; using CPU.")
        providers = ["CPUExecutionProvider"]
    app = FaceAnalysis(name="buffalo_l", providers=providers)
    app.prepare(ctx_id=0 if "CUDAExecutionProvider" in providers else -1,
                det_size=(640, 640))
    return app


def load_known_faces(app, known_dir):
    """Return (labels list, Nx512 matrix of normalized embeddings)."""
    if not os.path.isdir(known_dir):
        sys.exit(f"Reference folder not found: {known_dir}")
    labels, img_files, embs = [], [], []
    files = [os.path.join(known_dir, f) for f in sorted(os.listdir(known_dir))
             if os.path.splitext(f)[1].lower() in IMAGE_EXTS]
    if not files:
        sys.exit(f"No reference images in {known_dir}")
    for f in files:
        img = cv2.imread(f)
        if img is None:
            print(f"  ! could not read {f}"); continue
        faces = app.get(img)
        if not faces:
            print(f"  ! no face found in {os.path.basename(f)}"); continue
        # Use EVERY confident face in the image, not just the largest, so group
        # photos contribute all the people in them as reference faces.
        kept = [x for x in faces if getattr(x, "det_score", 1.0) >= 0.5]
        if not kept:
            kept = [max(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))]
        for face in kept:
            labels.append(person_name_from_filename(f))
            img_files.append(os.path.basename(f))
            embs.append(face.normed_embedding)
        print(f"  + {person_name_from_filename(f):<22} {len(kept):2d} face(s) <- {os.path.basename(f)}")
    if not embs:
        sys.exit("No usable reference faces.")
    return labels, img_files, np.vstack(embs).astype(np.float32)


def parse_exts(ext_str):
    """'mp4, mov,.mkv' -> {'.mp4', '.mov', '.mkv'}. Empty -> default list."""
    if not ext_str or not ext_str.strip():
        return set(VIDEO_EXTS)
    out = set()
    for e in ext_str.split(","):
        e = e.strip().lower().lstrip(".")
        if e:
            out.add("." + e)
    return out or set(VIDEO_EXTS)


def find_es(explicit=None):
    """Locate Everything's command-line tool (es.exe)."""
    if explicit and os.path.isfile(explicit):
        return explicit
    w = shutil.which("es") or shutil.which("es.exe")
    if w:
        return w
    for p in (os.path.expandvars(r"%ProgramFiles%\Everything\es.exe"),
              os.path.expandvars(r"%ProgramFiles(x86)%\Everything\es.exe"),
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Everything\es.exe")):
        if os.path.isfile(p):
            return p
    return None


def search_everything(date_from, date_to, field, exts, es_path):
    """Ask Everything (es.exe) for videos in a date range across ALL drives.
    field: 'modified' (recording date, default) or 'created' (copy date)."""
    es = find_es(es_path)
    if not es:
        sys.exit("Everything CLI (es.exe) not found. Install Everything + the "
                 "'es' command-line tool from voidtools.com, or use --videos/--all.")
    ext_q = "ext:" + ";".join(e.lstrip(".") for e in exts)
    kind = "dc" if field == "created" else "dm"
    query = f"file: {ext_q} {kind}:{date_from}..{date_to}"
    print(f"  Everything query: {query}")
    try:
        out = subprocess.run([es, query], capture_output=True, text=True, timeout=120)
    except Exception as e:
        sys.exit(f"Failed to run es.exe: {e}")
    paths = [ln.strip().strip('"') for ln in out.stdout.splitlines() if ln.strip()]
    return sorted({p for p in paths
                   if os.path.splitext(p)[1].lower() in exts and os.path.isfile(p)})


def parse_excludes(exclude_args):
    """Flatten --exclude values, allowing ';'-separated paths in one string."""
    out = []
    for item in (exclude_args or []):
        for piece in item.split(";"):
            piece = piece.strip().strip('"')
            if piece:
                out.append(os.path.normcase(os.path.normpath(piece)))
    return out


def apply_excludes(videos, excludes):
    """Drop any video under (or matching) an excluded path."""
    if not excludes:
        return videos
    kept = []
    for v in videos:
        nv = os.path.normcase(os.path.normpath(v))
        if any(nv == e or nv.startswith(e + os.sep) or e in nv for e in excludes):
            continue
        kept.append(v)
    dropped = len(videos) - len(kept)
    if dropped:
        print(f"  excluded {dropped} file(s) via --exclude")
    return kept


def collect_all_drives(exts):
    """Walk every drive/volume on the system for matching video files."""
    roots = []
    if hasattr(os, "listdrives"):          # Windows, Python 3.12+
        try:
            roots = list(os.listdrives())
        except Exception:
            roots = []
    if not roots:
        if os.name == "nt":
            import string
            roots = [f"{d}:\\" for d in string.ascii_uppercase
                     if os.path.exists(f"{d}:\\")]
        else:
            roots = ["/"]                  # macOS/Linux fallback
    print(f"  searching all drives: {', '.join(roots)}")
    paths = []
    for root in roots:
        for r, _, files in os.walk(root, onerror=lambda e: None):
            for f in files:
                if os.path.splitext(f)[1].lower() in exts:
                    paths.append(os.path.join(r, f))
    return sorted(set(paths))


def collect_files(file_args, exts):
    """Use the given paths. Each entry may be a file OR a folder.
    Files are honored as-is; folders are scanned recursively for videos."""
    paths = []
    for p in file_args:
        p = p.strip().strip('"')
        if not p:
            continue
        if os.path.isfile(p):
            paths.append(p)                # honor explicit files as-is
        elif os.path.isdir(p):
            for root, _, files in os.walk(p, onerror=lambda e: None):
                for f in files:
                    if os.path.splitext(f)[1].lower() in exts:
                        paths.append(os.path.join(root, f))
        else:
            print(f"  ! not found, skipping: {p}")
    return sorted(set(paths))


def collect_videos(videos_arg, exts):
    paths = []
    if os.path.isdir(videos_arg):
        for root, _, files in os.walk(videos_arg):
            for f in files:
                if os.path.splitext(f)[1].lower() in exts:
                    paths.append(os.path.join(root, f))
    elif os.path.isfile(videos_arg):
        with open(videos_arg, "r", encoding="utf-8-sig", errors="ignore") as fh:
            for line in fh:
                p = line.strip().strip('"')
                # handle CSV: take first field that looks like a path
                if "," in p and not os.path.exists(p):
                    p = p.split(",")[0].strip().strip('"')
                if p and os.path.splitext(p)[1].lower() in exts and os.path.exists(p):
                    paths.append(p)
    else:
        sys.exit(f"--videos not found: {videos_arg}")
    return sorted(set(paths))


def auto_sample_count(duration, multiplier):
    """Pick how many frames to check based on the video's length."""
    if not duration or duration <= 0:
        return MIN_SAMPLES
    n = round(duration / SECONDS_PER_SAMPLE * multiplier)
    return int(max(MIN_SAMPLES, min(MAX_SAMPLES, n)))


def make_sample_times(duration, n_samples):
    """Spread n_samples across the video: one random frame per equal section.
    Returns a chronological list of timestamps (seconds), or None if unknown."""
    if not duration or duration <= 0:
        return None
    times = []
    for k in range(n_samples):
        lo = duration * k / n_samples
        hi = duration * (k + 1) / n_samples
        times.append(random.uniform(lo, hi))
    return times


def sample_video(app, path, labels, img_files, known_mat, samples_override,
                 multiplier, threshold, stop_early, min_hits):
    """Return dict person -> {'hits':n, 'best':sim, 'first':'HH:MM:SS'}.

    Samples a few frames spread across the video (not the whole thing). For
    footage where the subject is present throughout (weddings, interviews),
    a handful of well-spread frames is enough to identify who's in it.
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"  ! cannot open {path}"); return {}
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = total / fps if fps else 0
    result = defaultdict(lambda: {"hits": 0, "best": 0.0, "first": None, "image": None})
    all_people = set(labels)

    n_samples = samples_override if samples_override and samples_override > 0 \
        else auto_sample_count(duration, multiplier)

    times = make_sample_times(duration, n_samples)
    if times is None:
        # Duration unknown: fall back to fixed 5s steps up to a safety cap.
        times = [i * 5.0 for i in range(200)]

    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        faces = app.get(frame)
        for face in faces:
            sims = known_mat @ face.normed_embedding  # cosine sim (both normalized)
            j = int(np.argmax(sims))
            s = float(sims[j])
            if s >= threshold:
                name = labels[j]
                r = result[name]
                r["hits"] += 1
                if s > r["best"]:
                    r["best"] = s
                    r["image"] = img_files[j]   # exact reference file that matched best
                if r["first"] is None:
                    r["first"] = f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d}"
        # Early exit once every known person has met the hit threshold.
        if stop_early and all_people and all(
                result[p]["hits"] >= min_hits for p in all_people):
            break
    cap.release()
    return result


# ============================================================================
# Interactive wizard (config from text files + a few questions)
# ============================================================================
CONFIG_TEMPLATES = {
    "extensions.txt": (
        "# Video extensions to scan - one per line, no dots.\n"
        "# Lines starting with # are ignored.\n"
        "mp4\nmov\nm2ts\nmts\navi\nmkv\nmxf\nwmv\nflv\nwebm\nm4v\nmpg\nmpeg\n3gp\nts\n"
    ),
    "negation.txt": (
        "# Paths to SKIP - one per line. Anything under these is ignored.\n"
        "# Example:\n"
        "# D:\\Backups\n"
        "# E:\\Proxies\n"
    ),
    "target.txt": (
        "# Paths to SEARCH - one per line (files or folders).\n"
        "# Leave empty (only comments) to search ALL drives.\n"
        "# Example:\n"
        "# D:\\Footage\n"
        "# E:\\Cards\\Day1\n"
    ),
}


def ensure_configs():
    """Create the config text files with templates if they don't exist."""
    for name, body in CONFIG_TEMPLATES.items():
        if not os.path.exists(name):
            with open(name, "w", encoding="utf-8") as fh:
                fh.write(body)
            print(f"  created {name}")


def read_list_file(path):
    """Return non-comment, non-blank lines from a text file."""
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as fh:
        for line in fh:
            line = line.strip().strip('"')
            if line and not line.startswith("#"):
                out.append(line)
    return out


def parse_dt(s, is_end=False):
    """Parse YYYY-MM-DD, YYYY-MM-DD-HH, or YYYY-MM-DD-HH-MM into a datetime.
    For an end value with no time given, snap to the end of the day/hour."""
    s = s.strip()
    for fmt in ("%Y-%m-%d-%H-%M", "%Y-%m-%d-%H", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if is_end:
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59, second=59)
            elif fmt == "%Y-%m-%d-%H":
                dt = dt.replace(minute=59, second=59)
        return dt
    raise ValueError(f"Unrecognised date: {s!r} (use YYYY-MM-DD or YYYY-MM-DD-HH)")


def filter_by_date(paths, start_dt, end_dt, field):
    """Keep files whose modified/created time is within [start, end]."""
    kept = []
    for p in paths:
        try:
            ts = os.path.getctime(p) if field == "created" else os.path.getmtime(p)
        except OSError:
            continue
        dt = datetime.fromtimestamp(ts)
        if (start_dt is None or dt >= start_dt) and (end_dt is None or dt <= end_dt):
            kept.append(p)
    return kept


def list_all_videos(exts, es_path):
    """Every video on all drives - via Everything if available, else walk."""
    es = find_es(es_path)
    if es:
        ext_q = "ext:" + ";".join(e.lstrip(".") for e in exts)
        query = f"file: {ext_q}"
        try:
            out = subprocess.run([es, query], capture_output=True, text=True, timeout=120)
            paths = [ln.strip().strip('"') for ln in out.stdout.splitlines() if ln.strip()]
            got = sorted({p for p in paths
                          if os.path.splitext(p)[1].lower() in exts and os.path.isfile(p)})
            if got:
                print(f"  Everything found {len(got)} video(s) on all drives")
                return got
        except Exception as e:
            print(f"  es.exe failed ({e}); falling back to walking drives")
    print("  Everything not available - walking all drives (slower)...")
    return collect_all_drives(exts)


def ask(prompt, default=""):
    try:
        ans = input(prompt).strip()
    except EOFError:
        ans = ""
    return ans or default


def run_wizard(args):
    """Ask a few questions, read the config files, return everything needed."""
    print("\n" + "=" * 56)
    print("  VIDEO FACE SORT - setup")
    print("=" * 56)
    ensure_configs()

    # --- extensions ---
    ext_lines = read_list_file("extensions.txt")
    exts = parse_exts(",".join(ext_lines)) if ext_lines else set(VIDEO_EXTS)
    print(f"\nExtensions ({len(exts)}): {', '.join(sorted(e.lstrip('.') for e in exts))}")

    # --- excludes / targets ---
    excludes = parse_excludes(read_list_file("negation.txt"))
    targets = read_list_file("target.txt")
    print(f"Exclude paths (negation.txt): {len(excludes)}")
    print(f"Target paths  (target.txt)  : {len(targets)}"
          + ("" if targets else "  -> will search ALL drives"))

    # --- date filter ---
    print("\nFilter by DATE?")
    print("  1) Single day")
    print("  2) Date range (start - end)")
    print("  3) No date filter")
    choice = ask("Select [1/2/3] (default 3): ", "3")
    start_dt = end_dt = None
    try:
        if choice == "1":
            d = ask("  Day  (format YYYY-MM-DD, e.g. 2025-02-14): ")
            start_dt = parse_dt(d, is_end=False).replace(hour=0, minute=0, second=0)
            end_dt = parse_dt(d, is_end=True)
        elif choice == "2":
            s = ask("  START (format YYYY-MM-DD-HH, e.g. 2025-02-14-09): ")
            e = ask("  END   (format YYYY-MM-DD-HH, e.g. 2025-02-16-18): ")
            start_dt = parse_dt(s, is_end=False)
            end_dt = parse_dt(e, is_end=True)
    except ValueError as ex:
        sys.exit(f"Date error: {ex}")
    if start_dt:
        print(f"  -> {start_dt} .. {end_dt}  (using {args.date_field} date)")

    # --- footage sensitivity ---
    print("\nFootage type?")
    print("  1) Normal        (stricter - fewer false matches)")
    print("  2) Sparse/short  (lenient - catches brief/few faces)")
    sens = ask("Select [1/2] (default 1): ", "1")
    if sens == "2":
        threshold, min_hits, multiplier = 0.40, 1, 3.0
    else:
        threshold, min_hits, multiplier = 0.45, 2, 1.0

    # --- copy? ---
    do_copy = ask("\nCopy matches into 'sorted' folder? [Y/n]: ", "y").lower() != "n"

    # --- build the video list ---
    print("\nGathering videos...")
    if targets:
        videos = collect_files(targets, exts)
    else:
        videos = list_all_videos(exts, args.es_path)
    if start_dt or end_dt:
        before = len(videos)
        videos = filter_by_date(videos, start_dt, end_dt, args.date_field)
        print(f"  date filter: {before} -> {len(videos)} video(s)")
    videos = apply_excludes(videos, excludes)

    print(f"\nReady: {len(videos)} video(s) to scan.")
    ask("Press Enter to start (Ctrl+C to cancel)... ")
    return {"exts": exts, "videos": videos, "excludes": excludes,
            "threshold": threshold, "min_hits": min_hits,
            "multiplier": multiplier, "copy": do_copy}


def main():
    ap = argparse.ArgumentParser(description="Sort videos by which known people appear.")
    ap.add_argument("--wizard", action="store_true",
                    help="Interactive mode: ask questions + read config text files")
    ap.add_argument("--videos",
                    help="Folder of videos OR a .txt/.csv list of video paths")
    ap.add_argument("--files", nargs="+",
                    help="Run against these path(s) only - each can be a file "
                         "OR a folder (folders are scanned for videos)")
    ap.add_argument("--all", action="store_true",
                    help="Search ALL drives on the system for videos")
    ap.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD",
                    help="Date-range start; uses Everything to find videos on all drives")
    ap.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD",
                    help="Date-range end (used with --from)")
    ap.add_argument("--date-field", choices=["modified", "created"],
                    default="modified",
                    help="Which date to filter on (modified = recording date)")
    ap.add_argument("--es-path", default="",
                    help="Full path to es.exe if not on PATH")
    ap.add_argument("--exclude", nargs="+",
                    help="Path(s) to skip - files/folders under these are ignored "
                         "(space-separated, or one ';'-separated string)")
    ap.add_argument("--known", default="search_pics",
                    help="Folder of reference images (filename = person name)")
    ap.add_argument("--out", default="sorted", help="Output folder for --copy")
    ap.add_argument("--report", default="report.csv", help="CSV report path")
    ap.add_argument("--txt", default="results.txt",
                    help="Human-readable text report path")
    ap.add_argument("--multiplier", type=float, default=1.0,
                    help="Scales the auto frame count (2.0 = twice as many "
                         "frames, 0.5 = half). Default auto-picks by length.")
    ap.add_argument("--samples", type=int, default=0,
                    help="Force a fixed frame count, overriding auto/--multiplier")
    ap.add_argument("--threshold", type=float, default=0.45,
                    help="Cosine-similarity match threshold (0.35 loose .. 0.55 strict)")
    ap.add_argument("--min-hits", type=int, default=2,
                    help="Person must appear in at least this many sampled frames to count")
    ap.add_argument("--no-stop-early", action="store_true",
                    help="Check all samples even after everyone has been found")
    ap.add_argument("--copy", action="store_true",
                    help="Copy matching videos into out/<Person>/")
    ap.add_argument("--gpu", action="store_true", help="Use NVIDIA GPU if available")
    ap.add_argument("--ext", default="",
                    help="Comma-separated video extensions to include, "
                         "e.g. \"mp4,mov,mkv\". Empty = built-in default list.")
    args = ap.parse_args()

    # Defaults from the command line; the wizard may override some of these.
    exts = parse_exts(args.ext)
    excludes = parse_excludes(args.exclude)
    threshold, min_hits = args.threshold, args.min_hits
    multiplier, samples = args.multiplier, args.samples
    stop_early, do_copy = not args.no_stop_early, args.copy
    wiz_videos = None

    if args.wizard:
        cfg = run_wizard(args)
        exts, excludes = cfg["exts"], cfg["excludes"]
        threshold, min_hits = cfg["threshold"], cfg["min_hits"]
        multiplier, do_copy = cfg["multiplier"], cfg["copy"]
        wiz_videos = cfg["videos"]

    print("\nLoading recognition model...")
    app = build_face_app(args.gpu)

    print(f"\nReading reference faces from {args.known}/")
    labels, img_files, known_mat = load_known_faces(app, args.known)
    print(f"  -> {len(labels)} reference face(s), {len(set(labels))} person(s)\n")

    # Decide the input source.
    if wiz_videos is not None:
        videos = wiz_videos                      # already resolved by the wizard
    else:
        # priority: --files > date range > --all > --videos
        if args.files:
            print("Input: specific file(s)/folder(s)")
            videos = collect_files(args.files, exts)
        elif args.date_from and args.date_to:
            print(f"Input: date range {args.date_from} .. {args.date_to} "
                  f"({args.date_field}) via Everything")
            videos = search_everything(args.date_from, args.date_to,
                                       args.date_field, exts, args.es_path)
        elif args.all:
            print("Input: all drives")
            videos = collect_all_drives(exts)
        elif args.videos:
            print(f"Input: {args.videos}")
            videos = collect_videos(args.videos, exts)
        else:
            sys.exit("Pick an input: --wizard, --from/--to <dates>, "
                     "--videos <folder/list>, --files <paths...>, or --all")
        videos = apply_excludes(videos, excludes)

    if not videos:
        sys.exit("No videos found.")
    print(f"Scanning {len(videos)} video(s)...\n")

    rows = []
    for i, v in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] {v}")
        res = sample_video(app, v, labels, img_files, known_mat, samples,
                           multiplier, threshold, stop_early, min_hits)
        matched = {name: d for name, d in res.items() if d["hits"] >= min_hits}
        if matched:
            for name, d in sorted(matched.items(), key=lambda kv: -kv[1]["hits"]):
                print(f"      MATCH {name}  via {d['image']}  (hits={d['hits']}, best={d['best']:.2f}, first@{d['first']})")
                rows.append({
                    "video": v, "person": name, "matched_image": d["image"],
                    "hits": d["hits"], "best_similarity": round(d["best"], 3),
                    "first_seen": d["first"],
                })
                if do_copy:
                    dest_dir = os.path.join(args.out, re.sub(r'[<>:"/\\|?*]', "_", name))
                    os.makedirs(dest_dir, exist_ok=True)
                    dest = os.path.join(dest_dir, os.path.basename(v))
                    if not os.path.exists(dest):
                        try:
                            shutil.copy2(v, dest)
                        except Exception as e:
                            print(f"      ! copy failed: {e}")
        else:
            print("      (no known person)")
            rows.append({"video": v, "person": "", "matched_image": "", "hits": 0,
                         "best_similarity": "", "first_seen": ""})

    with open(args.report, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["video", "person", "matched_image",
                                           "hits", "best_similarity", "first_seen"])
        w.writeheader()
        w.writerows(rows)

    # Human-readable text report, grouped by person.
    by_person = defaultdict(list)
    unmatched = []
    for r in rows:
        if r["person"]:
            by_person[r["person"]].append(r)
        else:
            unmatched.append(r["video"])
    matched_videos = len({r["video"] for r in rows if r["person"]})

    with open(args.txt, "w", encoding="utf-8") as fh:
        fh.write("VIDEO FACE-MATCH RESULTS\n")
        fh.write("=" * 60 + "\n")
        fh.write(f"Videos scanned : {len(videos)}\n")
        fh.write(f"Matched        : {matched_videos}\n")
        fh.write(f"No known person: {len(unmatched)}\n\n")
        for person in sorted(by_person):
            items = sorted(by_person[person], key=lambda r: -r["hits"])
            fh.write(f"\n=== {person}  ({len(items)} video(s)) ===\n")
            for r in items:
                fh.write(f"  {r['video']}\n")
                fh.write(f"      matched image={r['matched_image']}  "
                         f"hits={r['hits']}  best={r['best_similarity']}  "
                         f"first@{r['first_seen']}\n")
        if unmatched:
            fh.write(f"\n=== No known person  ({len(unmatched)} video(s)) ===\n")
            for v in unmatched:
                fh.write(f"  {v}\n")

    print(f"\nDone. {matched_videos}/{len(videos)} video(s) matched a known person.")
    print(f"Text report -> {args.txt}")
    print(f"CSV report  -> {args.report}")
    if do_copy:
        print(f"Copies      -> {args.out}/<Person>/")


if __name__ == "__main__":
    main()
