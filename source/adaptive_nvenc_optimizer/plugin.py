#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import os
import re
import sqlite3
import statistics
import subprocess
import shutil
import uuid
import time
import threading

import requests

from unmanic import config
from unmanic.libs.logs import UnmanicLogging
from unmanic.libs.plugins import PluginsHandler
from unmanic.libs.unplugins.settings import PluginSettings

PLUGIN_ID = "adaptive_nvenc_optimizer"
METRICS_PLUGIN_ID = "file_size_metrics_plus"
CUSTOM_REPO_MATCH = "Razorsnake706/unmanic-custom-plugins"
_REPO_REFRESH_INTERVAL = 300

logger = UnmanicLogging.get_logger(name="Unmanic.Plugin.adaptive_nvenc_optimizer")
_last_direct_repo_refresh = 0.0
_self_update_lock = threading.Lock()
_self_update_state = {"running": False, "requested_version": None, "error": None}
_sample_job_lock = threading.Lock()
_sample_jobs = {}
_sample_active_job = None


class Settings(PluginSettings):
    settings = {
        "capture_reference_clips": True,
        "keep_sample_files": False,
        "sample_count": 4,
        "tv_sample_seconds": 30,
        "movie_sample_seconds": 45,
        "reference_retention_hours": 72,
        "reference_cache_gb": 10,
    }

    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)
        self.form_settings = {
            "capture_reference_clips": {
                "label": "Capture pre-encode reference clips",
                "description": "Recommended ON for GPU video libraries. Captures short stream-copy reference clips before the normal video transcoder replaces the source.",
            },
            "keep_sample_files": {
                "label": "Keep calibration/test sample files",
                "description": "Off by default. Enable only when you want to manually inspect retained HEVC sample files after a test.",
            },
            "sample_count": {
                "label": "Representative samples per file",
                "description": "Number of positions distributed across the runtime. Recommended: 4.",
                "input_type": "text",
            },
            "tv_sample_seconds": {
                "label": "TV/short-form sample duration (seconds)",
                "description": "Used for media shorter than one hour. Recommended: 30 seconds.",
                "input_type": "text",
            },
            "movie_sample_seconds": {
                "label": "Movie/long-form sample duration (seconds)",
                "description": "Used for media one hour or longer. Recommended: 45 seconds.",
                "input_type": "text",
            },
            "reference_retention_hours": {
                "label": "Uncalibrated reference retention (hours)",
                "description": "Reference clips that have not been tested are automatically cleaned up after this many hours. Recommended: 72.",
                "input_type": "text",
            },
            "reference_cache_gb": {
                "label": "Maximum reference cache (GB)",
                "description": "Soft cap for pre-encode reference clips. Oldest untested captures are removed first when this limit is exceeded. Recommended: 10 GB.",
                "input_type": "text",
            },
        }


settings = Settings()


def _arg(arguments, name, default=""):
    value = (arguments or {}).get(name, default)
    if isinstance(value, list):
        value = value[0] if value else default
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return value


def _float(value):
    try:
        return float(value) if value is not None and str(value) != "" else None
    except Exception:
        return None


def _int(value):
    try:
        return int(value) if value is not None and str(value) != "" else None
    except Exception:
        return None


def _optimizer_profile():
    return settings.get_profile_directory()


def _optimizer_db_path():
    return os.path.join(_optimizer_profile(), "adaptive_optimizer.db")


def _optimizer_db():
    conn = sqlite3.connect(_optimizer_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sample_runs (
            id TEXT PRIMARY KEY,
            metric_id INTEGER,
            file_name TEXT,
            source_path TEXT,
            started REAL,
            finished REAL,
            success INTEGER,
            keep_files INTEGER,
            error TEXT,
            result_json TEXT
        );

        CREATE TABLE IF NOT EXISTS reference_captures (
            id TEXT PRIMARY KEY,
            task_id INTEGER,
            library_id INTEGER,
            source_path TEXT,
            file_name TEXT,
            source_codec TEXT,
            source_size INTEGER,
            created REAL,
            expires REAL,
            sample_length REAL,
            sample_count INTEGER,
            directory TEXT,
            status TEXT,
            keep_files INTEGER,
            manifest_json TEXT,
            error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_reference_task
            ON reference_captures(task_id);
        CREATE INDEX IF NOT EXISTS idx_reference_path
            ON reference_captures(source_path);
        CREATE INDEX IF NOT EXISTS idx_reference_status
            ON reference_captures(status, created);
        """
    )
    return conn


def _sample_root():
    path = os.path.join(_optimizer_profile(), "samples")
    os.makedirs(path, exist_ok=True)
    return path


def _reference_root():
    path = os.path.join(_optimizer_profile(), "reference-captures")
    os.makedirs(path, exist_ok=True)
    return path


def _library_settings(library_id=None):
    try:
        return Settings(library_id=library_id) if library_id else Settings()
    except Exception:
        logger.exception("Unable to load adaptive settings for library %s", library_id)
        return settings


def _sampling_values(setting_obj, duration):
    sample_count = max(1, min(8, _int(setting_obj.get_setting("sample_count")) or 4))
    short_length = max(10, min(120, _int(setting_obj.get_setting("tv_sample_seconds")) or 30))
    long_length = max(10, min(180, _int(setting_obj.get_setting("movie_sample_seconds")) or 45))
    sample_length = long_length if duration and duration >= 3600 else short_length
    return sample_count, sample_length


def _append_worker_log(worker_log, message):
    try:
        if worker_log is not None:
            worker_log.append("\n[Adaptive NVENC Optimizer] {}".format(message))
    except Exception:
        pass


def _directory_size(path):
    total = 0
    if not path or not os.path.isdir(path):
        return 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _capture_manifest(row):
    try:
        return json.loads(row.get("manifest_json") or "{}")
    except Exception:
        return {}


def _capture_files_valid(capture):
    manifest = capture.get("manifest") or {}
    clips = manifest.get("clips") or []
    if not clips:
        return False
    return all(os.path.isfile(clip.get("path") or "") for clip in clips)


def _capture_record(row):
    if row is None:
        return None
    capture = dict(row)
    capture["manifest"] = _capture_manifest(capture)
    capture["available"] = _capture_files_valid(capture)
    capture["bytes"] = _directory_size(capture.get("directory"))
    return capture


def _reference_capture_for_metrics_row(metrics_row):
    r = dict(metrics_row)
    task_id = _int(r.get("task_id"))
    source_path = r.get("source_path")
    with _optimizer_db() as conn:
        row = None
        if task_id is not None:
            row = conn.execute(
                """
                SELECT * FROM reference_captures
                WHERE task_id=? AND status IN ('ready','retained','tested')
                ORDER BY created DESC LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        if row is None and source_path:
            row = conn.execute(
                """
                SELECT * FROM reference_captures
                WHERE source_path=? AND status IN ('ready','retained','tested')
                ORDER BY created DESC LIMIT 1
                """,
                (source_path,),
            ).fetchone()
    capture = _capture_record(row)
    if capture and not capture.get("available"):
        try:
            with _optimizer_db() as conn:
                conn.execute(
                    "UPDATE reference_captures SET status='missing', error=? WHERE id=?",
                    ("Reference files are no longer present.", capture.get("id")),
                )
        except Exception:
            logger.exception("Unable to mark missing reference capture")
        return None
    return capture


def _reference_capture_by_id(capture_id):
    if not capture_id:
        return None
    with _optimizer_db() as conn:
        row = conn.execute(
            "SELECT * FROM reference_captures WHERE id=?",
            (str(capture_id),),
        ).fetchone()
    capture = _capture_record(row)
    return capture if capture and capture.get("available") else None


def _remove_reference_capture(capture, status="consumed"):
    if not capture:
        return
    directory = capture.get("directory")
    try:
        if directory and os.path.isdir(directory):
            shutil.rmtree(directory)
    except Exception:
        logger.exception("Unable to remove reference capture directory %s", directory)
        return
    try:
        with _optimizer_db() as conn:
            conn.execute(
                "UPDATE reference_captures SET status=?, error=NULL WHERE id=?",
                (status, capture.get("id")),
            )
    except Exception:
        logger.exception("Unable to update reference capture status")


def _cleanup_reference_captures(setting_obj=None):
    setting_obj = setting_obj or settings
    now = time.time()
    try:
        max_gb = max(1.0, _float(setting_obj.get_setting("reference_cache_gb")) or 10.0)
    except Exception:
        max_gb = 10.0
    max_bytes = int(max_gb * (1024 ** 3))

    with _optimizer_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM reference_captures
            WHERE status IN ('ready','tested','retained')
            ORDER BY created ASC
            """
        ).fetchall()

    captures = [_capture_record(row) for row in rows]
    for capture in captures:
        if not capture:
            continue
        expires = _float(capture.get("expires"))
        if (
            not capture.get("keep_files")
            and expires is not None
            and expires <= now
        ):
            _remove_reference_capture(capture, status="expired")

    with _optimizer_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM reference_captures
            WHERE status IN ('ready','tested','retained')
            ORDER BY created ASC
            """
        ).fetchall()
    captures = [_capture_record(row) for row in rows]
    total = sum(capture.get("bytes") or 0 for capture in captures if capture)
    if total <= max_bytes:
        return

    for capture in captures:
        if not capture or capture.get("keep_files"):
            continue
        size = capture.get("bytes") or 0
        _remove_reference_capture(capture, status="cache_evicted")
        total -= size
        if total <= max_bytes:
            break


def _metrics_db_path():
    userdata = config.Config().get_userdata_path()
    return os.path.join(userdata, METRICS_PLUGIN_ID, "metrics_plus.db")


def _metrics_db():
    path = _metrics_db_path()
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect("file:{}?mode=ro".format(path), uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _pct_change(before, after):
    before = _float(before)
    after = _float(after)
    if before in (None, 0) or after is None:
        return None
    return (before - after) / before * 100.0


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def _sane_video_bitrate(total_bitrate, audio_bitrate, reported_video_bitrate):
    total = _float(total_bitrate)
    audio = _float(audio_bitrate)
    video = _float(reported_video_bitrate)
    if total is None:
        return video
    residual = total - (audio or 0)
    if residual <= 0:
        return video
    if video is None or video > total * 1.02 or video > residual * 1.10:
        return residual
    return video


def _diagnose(row):
    r = dict(row)
    source_total = _float(r.get("source_total_bitrate"))
    dest_total = _float(r.get("dest_total_bitrate"))
    source_codec = str(r.get("source_codec") or "").lower()
    dest_codec = str(r.get("dest_codec") or "").lower()
    source_audio = _float(r.get("source_audio_bitrate"))
    dest_audio = _float(r.get("dest_audio_bitrate"))
    source_video = _sane_video_bitrate(source_total, source_audio, r.get("source_video_bitrate"))
    dest_video = _sane_video_bitrate(dest_total, dest_audio, r.get("dest_video_bitrate"))
    saved_pct = _float(r.get("percent_saved"))
    source_size = _float(r.get("source_size"))
    dest_size = _float(r.get("dest_size"))
    media_duration = _float(r.get("source_duration")) or _float(r.get("dest_duration"))
    task_duration = _float(r.get("duration"))
    width = _float(r.get("source_width"))
    height = _float(r.get("source_height"))
    fps = _float(r.get("source_fps"))

    video_reduction = _pct_change(source_video, dest_video)
    audio_reduction = _pct_change(source_audio, dest_audio)
    audio_share = (dest_audio / dest_total * 100.0) if dest_audio and dest_total else None
    speed = (media_duration / task_duration) if media_duration and task_duration else None
    source_bpppf = (
        source_video / (width * height * fps)
        if source_video and width and height and fps else None
    )
    dest_bpppf = (
        dest_video / (width * height * fps)
        if dest_video and width and height and fps else None
    )

    required = [
        source_total, dest_total, source_video, dest_video,
        r.get("encoder_quality"), r.get("encoder_preset"),
        r.get("source_fps"), r.get("source_bit_depth"), r.get("dest_bit_depth"),
    ]
    completeness = sum(1 for v in required if v not in (None, "")) / len(required) * 100.0

    status = "Needs more data"
    reason = "This encode predates some of the diagnostic fields needed for a reliable recommendation."
    priority = 0.0

    training_eligible = False

    if completeness >= 75:
        if dest_codec not in ("hevc", "h265"):
            status = "No video encode"
            reason = "The task completed without producing HEVC video, so it is excluded from the NVENC training baseline."
            priority = 5.0
        elif source_codec == dest_codec:
            status = "Same-codec result"
            reason = "The source and output codecs match; keep this row for diagnostics but exclude it from the H.264-to-HEVC training baseline."
            priority = 10.0
        else:
            training_eligible = True

        if training_eligible and audio_share is not None and audio_share >= 45:
            status = "Audio-limited"
            reason = "Video compressed substantially, but audio is now a large share of the final bitrate."
            priority = 35.0
        elif training_eligible and saved_pct is not None and video_reduction is not None and saved_pct >= 45 and video_reduction >= 45:
            status = "Good compression"
            reason = "Both total file size and video bitrate dropped strongly at the current NVENC settings."
            priority = 10.0
        elif training_eligible and source_bpppf is not None and source_bpppf <= 0.055:
            status = "Already efficient"
            reason = "The source video bitrate is already low for its resolution and frame rate."
            priority = 15.0
        elif training_eligible and video_reduction is not None and video_reduction < 25:
            status = "Sample-test candidate"
            reason = "The video bitrate did not fall much; a controlled QP sample test may find additional savings."
            priority = 80.0
        elif training_eligible and saved_pct is not None and saved_pct < 25:
            status = "Sample-test candidate"
            reason = "Overall storage savings were modest; the source is worth profiling before a full retry."
            priority = 70.0
        elif training_eligible:
            status = "Worth profiling"
            reason = "The encode is usable, but sample testing could determine whether a higher QP remains acceptable."
            priority = 50.0

    # Prefer examining large outputs when two rows have the same diagnosis.
    if dest_size:
        priority += min(25.0, dest_size / (1024 ** 3) * 2.5)

    return {
        "id": r.get("id"),
        "file_name": r.get("file_name"),
        "library_name": r.get("library_name"),
        "finish_time": r.get("finish_time"),
        "source_size": r.get("source_size"),
        "dest_size": r.get("dest_size"),
        "percent_saved": saved_pct,
        "source_total_bitrate": r.get("source_total_bitrate"),
        "dest_total_bitrate": r.get("dest_total_bitrate"),
        "source_video_bitrate": source_video,
        "dest_video_bitrate": dest_video,
        "source_audio_bitrate": r.get("source_audio_bitrate"),
        "dest_audio_bitrate": r.get("dest_audio_bitrate"),
        "video_reduction": video_reduction,
        "audio_reduction": audio_reduction,
        "audio_share": audio_share,
        "encode_speed": speed,
        "source_bpppf": source_bpppf,
        "dest_bpppf": dest_bpppf,
        "encoder_name": r.get("encoder_name"),
        "encoder_rate_control": r.get("encoder_rate_control"),
        "encoder_quality": r.get("encoder_quality"),
        "encoder_preset": r.get("encoder_preset"),
        "encoder_tune": r.get("encoder_tune"),
        "encoder_lookahead": r.get("encoder_lookahead"),
        "encoder_spatial_aq": r.get("encoder_spatial_aq"),
        "encoder_aq_strength": r.get("encoder_aq_strength"),
        "source_width": r.get("source_width"),
        "source_height": r.get("source_height"),
        "source_fps": r.get("source_fps"),
        "source_bit_depth": r.get("source_bit_depth"),
        "dest_bit_depth": r.get("dest_bit_depth"),
        "source_path": r.get("source_path"),
        "dest_path": r.get("dest_path"),
        "diagnosis": status,
        "reason": reason,
        "completeness": completeness,
        "priority": priority,
        "training_eligible": training_eligible,
    }



def _current_media_identity(path):
    if not path or not os.path.exists(path):
        return {"exists": False}
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=size,duration:stream=codec_type,codec_name,width,height",
        "-of", "json", path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
        if proc.returncode:
            return {"exists": True, "probe_error": (proc.stderr or "").strip()[:500]}
        payload = json.loads(proc.stdout or "{}")
        streams = payload.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        fmt = payload.get("format") or {}
        return {
            "exists": True,
            "codec": video.get("codec_name"),
            "width": _int(video.get("width")),
            "height": _int(video.get("height")),
            "size": _int(fmt.get("size")),
            "duration": _float(fmt.get("duration")),
        }
    except Exception as exc:
        logger.exception("Unable to inspect current media path for adaptive planning")
        return {"exists": True, "probe_error": str(exc)}


def _sample_timestamps(duration, sample_length, sample_count=4):
    duration = _float(duration)
    sample_count = max(1, min(8, _int(sample_count) or 4))
    if not duration or duration <= sample_length + 20:
        return []

    # Spread samples through the interior of the runtime while avoiding intros,
    # credits and seek-edge behavior. Four samples produce 10/35/60/85%-ish
    # coverage similar to the original hand-picked plan.
    if sample_count == 1:
        positions = [0.50]
    else:
        low, high = 0.10, 0.85
        step = (high - low) / float(sample_count - 1)
        positions = [low + step * i for i in range(sample_count)]

    starts = []
    edge = min(60.0, max(10.0, duration * 0.03))
    latest = max(edge, duration - sample_length - edge)
    for pos in positions:
        center = duration * pos
        start = max(edge, min(latest, center - sample_length / 2.0))
        rounded = round(start, 1)
        if rounded not in starts:
            starts.append(rounded)
    return starts



def _capture_reference_segment(source_path, start, length, output_path):
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(start),
        "-i", source_path,
        "-t", str(length),
        "-map", "0:v:0",
        "-an", "-sn", "-dn",
        "-c:v", "copy",
        "-avoid_negative_ts", "make_zero",
        output_path,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max(60, int(length * 3)),
        check=False,
    )
    if proc.returncode != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
        except OSError:
            pass
        return {
            "success": False,
            "error": (proc.stderr or proc.stdout or "Reference capture failed.").strip()[-1200:],
        }

    identity = _current_media_identity(output_path)
    return {
        "success": True,
        "duration": _float(identity.get("duration")) or _float(length),
        "codec": identity.get("codec"),
        "bytes": os.path.getsize(output_path),
        "command": cmd,
    }


def _capture_preencode_references(data, setting_obj):
    source_path = data.get("file_in") or data.get("original_file_path")
    original_path = data.get("original_file_path") or source_path
    worker_log = data.get("worker_log")
    task_id = _int(data.get("task_id"))
    library_id = _int(data.get("library_id"))

    if not source_path or not os.path.isfile(source_path):
        _append_worker_log(worker_log, "Reference capture skipped: source file is not available.")
        return None

    # This runner must execute before the video transcoder so that file_in still
    # points at the untouched library source rather than a cache artifact created
    # by an earlier processing plugin.
    try:
        same_source = os.path.realpath(source_path) == os.path.realpath(original_path)
    except Exception:
        same_source = os.path.abspath(source_path) == os.path.abspath(original_path)
    if not same_source:
        _append_worker_log(
            worker_log,
            "Reference capture skipped because Adaptive NVENC Optimizer is not first in the worker flow. "
            "Move it before Transcode Video Files.",
        )
        return None

    identity = _current_media_identity(source_path)
    if identity.get("probe_error"):
        _append_worker_log(worker_log, "Reference capture skipped: source probe failed.")
        return None

    source_codec = str(identity.get("codec") or "").lower()
    if not source_codec:
        _append_worker_log(worker_log, "Reference capture skipped: no video stream was detected.")
        return None
    if source_codec in ("hevc", "h265", "av1"):
        _append_worker_log(
            worker_log,
            "Reference capture skipped: source video is already {}.".format(source_codec),
        )
        return None

    duration = _float(identity.get("duration"))
    if not duration:
        _append_worker_log(worker_log, "Reference capture skipped: media duration is unavailable.")
        return None

    # Avoid duplicating captures if Unmanic retries the same task runner.
    if task_id is not None:
        with _optimizer_db() as conn:
            existing = conn.execute(
                """
                SELECT * FROM reference_captures
                WHERE task_id=? AND source_path=? AND status IN ('capturing','ready','retained','tested')
                ORDER BY created DESC LIMIT 1
                """,
                (task_id, source_path),
            ).fetchone()
        existing_capture = _capture_record(existing)
        if existing_capture and existing_capture.get("available"):
            _append_worker_log(worker_log, "Pre-encode reference clips already exist for this task.")
            return existing_capture

    sample_count, sample_length = _sampling_values(setting_obj, duration)
    starts = _sample_timestamps(duration, sample_length, sample_count)
    if not starts:
        _append_worker_log(worker_log, "Reference capture skipped: media is too short for the configured sample duration.")
        return None

    keep_files = bool(setting_obj.get_setting("keep_sample_files"))
    retention_hours = max(
        1.0,
        min(24.0 * 30.0, _float(setting_obj.get_setting("reference_retention_hours")) or 72.0),
    )
    created = time.time()
    expires = None if keep_files else created + retention_hours * 3600.0
    capture_id = "{}-{}".format(task_id if task_id is not None else "source", uuid.uuid4().hex[:10])
    capture_dir = os.path.join(_reference_root(), capture_id)
    os.makedirs(capture_dir, exist_ok=False)

    with _optimizer_db() as conn:
        conn.execute(
            """
            INSERT INTO reference_captures(
                id, task_id, library_id, source_path, file_name, source_codec,
                source_size, created, expires, sample_length, sample_count,
                directory, status, keep_files, manifest_json, error
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                capture_id,
                task_id,
                library_id,
                source_path,
                os.path.basename(source_path),
                source_codec,
                _int(identity.get("size")),
                created,
                expires,
                sample_length,
                len(starts),
                capture_dir,
                "capturing",
                1 if keep_files else 0,
                None,
                None,
            ),
        )

    _append_worker_log(
        worker_log,
        "Capturing {} pre-encode reference clips before the video transcode.".format(len(starts)),
    )

    clips = []
    errors = []
    for index, start in enumerate(starts, 1):
        output_path = os.path.join(capture_dir, "reference_{:02d}.mkv".format(index))
        result = _capture_reference_segment(source_path, start, sample_length, output_path)
        if not result.get("success"):
            errors.append("sample {}: {}".format(index, result.get("error") or "capture failed"))
            _append_worker_log(worker_log, "Reference clip {} failed; continuing.".format(index))
            continue

        clips.append({
            "index": index,
            "requested_start": start,
            "requested_length": sample_length,
            "duration": result.get("duration"),
            "path": output_path,
            "file_name": os.path.basename(output_path),
            "bytes": result.get("bytes"),
            "codec": result.get("codec"),
        })

    manifest = {
        "capture_id": capture_id,
        "task_id": task_id,
        "library_id": library_id,
        "source_path": source_path,
        "source_codec": source_codec,
        "source_size": _int(identity.get("size")),
        "source_duration": duration,
        "sample_length": sample_length,
        "sample_starts": starts,
        "clips": clips,
        "created": created,
        "expires": expires,
        "errors": errors,
    }

    if not clips:
        try:
            shutil.rmtree(capture_dir)
        except Exception:
            pass
        with _optimizer_db() as conn:
            conn.execute(
                """
                UPDATE reference_captures
                SET status='failed', error=?, manifest_json=?
                WHERE id=?
                """,
                (
                    "; ".join(errors)[:3000] or "No reference clips were captured.",
                    json.dumps(manifest, default=str),
                    capture_id,
                ),
            )
        _append_worker_log(worker_log, "Reference capture failed; normal Unmanic processing will continue.")
        return None

    manifest_path = os.path.join(capture_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    with _optimizer_db() as conn:
        conn.execute(
            """
            UPDATE reference_captures
            SET status='ready', sample_count=?, manifest_json=?, error=?
            WHERE id=?
            """,
            (
                len(clips),
                json.dumps(manifest, default=str),
                "; ".join(errors)[:3000] if errors else None,
                capture_id,
            ),
        )

    _append_worker_log(
        worker_log,
        "Captured {} reference clips. Normal video processing can continue.".format(len(clips)),
    )
    capture = _reference_capture_by_id(capture_id)
    _cleanup_reference_captures(setting_obj)
    return capture


def on_worker_process(data):
    """Capture lightweight stream-copy references before the normal video transcoder."""
    data["exec_command"] = []
    data["repeat"] = False

    try:
        setting_obj = _library_settings(data.get("library_id"))
        if not bool(setting_obj.get_setting("capture_reference_clips")):
            return

        _cleanup_reference_captures(setting_obj)
        _capture_preencode_references(data, setting_obj)
    except Exception as exc:
        # Calibration must never prevent the user's normal media job from running.
        logger.exception("Pre-encode reference capture failed")
        _append_worker_log(
            data.get("worker_log"),
            "Reference capture encountered an error and was skipped: {}".format(exc),
        )
    return


def _sample_plan(arguments):
    metric_id = _int(_arg(arguments, "id", 0))
    if not metric_id:
        return {"success": False, "message": "A metrics record ID is required."}

    conn = _metrics_db()
    if conn is None:
        return {"success": False, "message": "File Size Metrics Plus database was not found."}

    try:
        row = conn.execute("SELECT * FROM metrics WHERE id=?", (metric_id,)).fetchone()
        if row is None:
            return {"success": False, "message": "Metrics record was not found."}

        diagnosed = _diagnose(row)
        r = dict(row)
        source_path = r.get("source_path")
        identity = _current_media_identity(source_path)

        stored_source_codec = str(r.get("source_codec") or "").lower()
        current_codec = str(identity.get("codec") or "").lower()
        stored_source_size = _float(r.get("source_size"))
        current_size = _float(identity.get("size"))

        codec_matches = bool(stored_source_codec and current_codec and stored_source_codec == current_codec)
        size_ratio = (
            current_size / stored_source_size
            if current_size and stored_source_size else None
        )
        size_matches = bool(size_ratio is not None and 0.90 <= size_ratio <= 1.10)
        original_available = bool(identity.get("exists") and codec_matches and size_matches)

        if not identity.get("exists"):
            source_state = "Source path is no longer present."
        elif identity.get("probe_error"):
            source_state = "Source path exists, but could not be probed safely."
        elif original_available:
            source_state = "The current file still appears to match the original source captured by Metrics Plus."
        elif stored_source_codec and current_codec and stored_source_codec != current_codec:
            source_state = (
                "The current file is now {} while the recorded source was {}; "
                "the original appears to have been replaced."
            ).format(current_codec, stored_source_codec)
        else:
            source_state = (
                "The current file no longer closely matches the recorded source size; "
                "the original may have been replaced."
            )

        duration = _float(r.get("source_duration")) or _float(identity.get("duration")) or _float(r.get("dest_duration"))
        sample_count = max(1, min(8, _int(settings.get_setting("sample_count")) or 4))
        short_length = max(10, min(120, _int(settings.get_setting("tv_sample_seconds")) or 30))
        long_length = max(10, min(180, _int(settings.get_setting("movie_sample_seconds")) or 45))
        sample_length = long_length if duration and duration >= 3600 else short_length
        starts = _sample_timestamps(duration, sample_length, sample_count)

        current_qp = _int(r.get("encoder_quality"))
        if current_qp is None:
            current_qp = 28
        qp_values = []
        for value in (current_qp, current_qp + 3, current_qp + 6, current_qp + 9):
            value = max(18, min(40, value))
            if value not in qp_values:
                qp_values.append(value)

        speed = _float(diagnosed.get("encode_speed"))
        total_test_video_seconds = len(starts) * sample_length * len(qp_values)
        estimated_encode_seconds = (
            total_test_video_seconds / speed
            if speed and speed > 0 else None
        )

        return {
            "success": True,
            "record": diagnosed,
            "source_check": {
                "path": source_path,
                "original_available": original_available,
                "message": source_state,
                "stored_codec": r.get("source_codec"),
                "current_codec": identity.get("codec"),
                "stored_size": r.get("source_size"),
                "current_size": identity.get("size"),
                "size_ratio": size_ratio,
            },
            "plan": {
                "sample_length": sample_length,
                "sample_starts": starts,
                "qp_values": qp_values,
                "sample_count": len(starts),
                "encode_variants": len(starts) * len(qp_values),
                "estimated_nvenc_seconds": estimated_encode_seconds,
                "quality_metrics": ["xpsnr", "ssim"],
                "can_execute_safely": original_available and bool(starts),
                "mode": "manual_test_available" if original_available and bool(starts) else "planning_only",
                "keep_sample_files": bool(settings.get_setting("keep_sample_files")),
            },
        }
    finally:
        conn.close()



def _job_update(job_id, **changes):
    with _sample_job_lock:
        job = _sample_jobs.get(job_id)
        if job is not None:
            job.update(changes)


def _command_value(command_text, names, default=None):
    if not command_text:
        return default
    try:
        import shlex
        tokens = shlex.split(command_text)
    except Exception:
        tokens = str(command_text).split()
    for i, token in enumerate(tokens[:-1]):
        for name in names:
            if token == name or token.startswith(name + ":"):
                return tokens[i + 1]
    return default


def _row_encoder_command(row):
    try:
        commands = json.loads(row.get("encoder_commands_json") or "[]")
    except Exception:
        commands = []
    for command in commands:
        if "nvenc" in str(command).lower():
            return str(command)
    return str(commands[0]) if commands else ""


def _build_sample_encode_command(row, source_path, start, length, qp, output_path, use_hw_decode=True):
    command_text = _row_encoder_command(row)
    preset = row.get("encoder_preset") or _command_value(command_text, ["-preset"], "p4")
    tune = row.get("encoder_tune") or _command_value(command_text, ["-tune"], "hq")
    profile = row.get("encoder_profile") or _command_value(command_text, ["-profile:v", "-profile"], "main10")
    rate_control = row.get("encoder_rate_control") or _command_value(command_text, ["-rc:v", "-rc"], "constqp")
    lookahead = _int(row.get("encoder_lookahead"))
    if lookahead is None:
        lookahead = _int(_command_value(command_text, ["-rc-lookahead:v", "-rc-lookahead"], 20))
    spatial_aq = _int(row.get("encoder_spatial_aq"))
    if spatial_aq is None:
        spatial_aq = _int(_command_value(command_text, ["-spatial-aq:v", "-spatial-aq"], 1))
    aq_strength = _int(row.get("encoder_aq_strength"))
    if aq_strength is None:
        aq_strength = _int(_command_value(command_text, ["-aq-strength:v", "-aq-strength"], 8))
    gpu = _int(_command_value(command_text, ["-gpu:v", "-gpu"], 0))
    if gpu is None:
        gpu = 0

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if use_hw_decode and str(row.get("encoder_hwaccel") or "").lower() == "cuda":
        cmd += ["-hwaccel", "cuda", "-hwaccel_device", str(gpu), "-hwaccel_output_format", "cuda"]

    cmd += [
        "-ss", str(start),
        "-i", source_path,
        "-t", str(length),
        "-map", "0:v:0",
        "-an", "-sn", "-dn",
        "-c:v", "hevc_nvenc",
        "-gpu", str(gpu),
        "-preset", str(preset),
        "-tune", str(tune),
        "-profile:v", str(profile),
        "-rc:v", str(rate_control),
        "-qp:v", str(qp),
    ]

    if lookahead is not None:
        cmd += ["-rc-lookahead:v", str(lookahead)]
    if spatial_aq is not None:
        cmd += ["-spatial-aq:v", "1" if spatial_aq else "0"]
    if aq_strength is not None and spatial_aq:
        cmd += ["-aq-strength:v", str(aq_strength)]

    cmd += [output_path]
    return cmd


def _run_sample_encode(row, source_path, start, length, qp, output_path):
    attempts = [True, False] if str(row.get("encoder_hwaccel") or "").lower() == "cuda" else [False]
    last_error = None
    used_hw_decode = False
    for hw_decode in attempts:
        cmd = _build_sample_encode_command(
            row, source_path, start, length, qp, output_path, use_hw_decode=hw_decode
        )
        started = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=max(120, int(length * 8)), check=False)
        elapsed = time.time() - started
        if proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            used_hw_decode = hw_decode
            return {
                "success": True,
                "elapsed": elapsed,
                "used_hw_decode": used_hw_decode,
                "command": cmd,
            }
        last_error = (proc.stderr or proc.stdout or "ffmpeg sample encode failed").strip()[-1800:]
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
        except OSError:
            pass

    return {"success": False, "error": last_error or "Sample encode failed."}


def _metric_from_log(text, metric):
    lines = [line.strip() for line in str(text or "").splitlines()]
    if metric == "ssim":
        for line in reversed(lines):
            if "SSIM" in line and "All:" in line:
                match = re.search(r"All:\s*([0-9.]+)", line)
                if match:
                    return _float(match.group(1))
    elif metric == "xpsnr":
        for line in reversed(lines):
            if "XPSNR" not in line.upper():
                continue
            # Y/luma is the primary value for YCbCr sources. If an FFmpeg
            # version formats it differently, fall back to the first number
            # after the XPSNR label.
            match = re.search(r"\b[yY]\s*:\s*([0-9.]+)", line)
            if match:
                return _float(match.group(1))
            tail = re.split(r"XPSNR", line, flags=re.IGNORECASE)[-1]
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)", tail)
            if match:
                return _float(match.group(1))
    return None


def _run_quality_metric(source_path, candidate_path, start, length, metric):
    filter_name = "xpsnr" if metric == "xpsnr" else "ssim"
    graph = (
        "[0:v:0]setpts=PTS-STARTPTS[ref];"
        "[1:v:0]setpts=PTS-STARTPTS[dist];"
        "[ref][dist]{}".format(filter_name)
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        "-ss", str(start), "-t", str(length), "-i", source_path,
        "-i", candidate_path,
        "-filter_complex", graph,
        "-an", "-shortest", "-f", "null", "-",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max(180, int(length * 12)),
        check=False,
    )
    combined = (proc.stderr or "") + "\n" + (proc.stdout or "")
    value = _metric_from_log(combined, metric)
    return {
        "success": proc.returncode == 0 and value is not None,
        "value": value,
        "error": None if value is not None else combined.strip()[-1600:],
    }


def _aggregate_qp_results(samples, sample_length):
    grouped = {}
    for sample in samples:
        qp = str(sample.get("qp"))
        grouped.setdefault(qp, []).append(sample)

    output = []
    for qp, rows in sorted(grouped.items(), key=lambda item: int(item[0])):
        xpsnr = [r.get("xpsnr") for r in rows if r.get("xpsnr") is not None]
        ssim = [r.get("ssim") for r in rows if r.get("ssim") is not None]
        bitrates = [r.get("video_bitrate") for r in rows if r.get("video_bitrate") is not None]
        output.append({
            "qp": int(qp),
            "samples": len(rows),
            "xpsnr": _mean(xpsnr),
            "ssim": _mean(ssim),
            "video_bitrate": _mean(bitrates),
            "encoded_bytes": sum(int(r.get("bytes") or 0) for r in rows),
            "encode_seconds": sum(float(r.get("encode_seconds") or 0) for r in rows),
            "quality_samples": min(len(xpsnr), len(ssim)),
        })
    return output


def _persist_sample_run(job):
    try:
        with _optimizer_db() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sample_runs(
                    id, metric_id, file_name, source_path, started, finished,
                    success, keep_files, error, result_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job.get("id"),
                    job.get("metric_id"),
                    job.get("file_name"),
                    job.get("source_path"),
                    job.get("started"),
                    job.get("finished"),
                    1 if job.get("status") == "completed" else 0,
                    1 if job.get("keep_files") else 0,
                    job.get("error"),
                    json.dumps(job.get("result") or {}, default=str),
                ),
            )
    except Exception:
        logger.exception("Unable to persist adaptive sample-test result")


def _sample_test_worker(job_id, metric_id):
    global _sample_active_job

    job_dir = None
    try:
        plan_data = _sample_plan({"id": metric_id})
        if not plan_data.get("success"):
            raise RuntimeError(plan_data.get("message") or "Unable to build sample plan.")
        plan = plan_data.get("plan") or {}
        check = plan_data.get("source_check") or {}
        if not plan.get("can_execute_safely") or not check.get("original_available"):
            raise RuntimeError("The original source is not safely available for a perceptual sample test.")

        conn = _metrics_db()
        if conn is None:
            raise RuntimeError("File Size Metrics Plus database was not found.")
        try:
            row_obj = conn.execute("SELECT * FROM metrics WHERE id=?", (metric_id,)).fetchone()
            if row_obj is None:
                raise RuntimeError("Metrics record was not found.")
            row = dict(row_obj)
        finally:
            conn.close()

        source_path = check.get("path")
        keep_files = bool(settings.get_setting("keep_sample_files"))
        starts = list(plan.get("sample_starts") or [])
        qps = list(plan.get("qp_values") or [])
        sample_length = _int(plan.get("sample_length")) or 30
        total = len(starts) * len(qps)
        if not total:
            raise RuntimeError("The sample plan did not contain any test variants.")

        job_dir = os.path.join(_sample_root(), job_id)
        os.makedirs(job_dir, exist_ok=False)

        _job_update(
            job_id,
            status="running",
            stage="encoding_and_quality",
            total=total,
            completed=0,
            keep_files=keep_files,
            sample_directory=job_dir if keep_files else None,
        )

        samples = []
        completed = 0
        for sample_index, start in enumerate(starts, 1):
            for qp in qps:
                filename = "sample_{:02d}_qp{}.mkv".format(sample_index, qp)
                output_path = os.path.join(job_dir, filename)
                _job_update(
                    job_id,
                    current="Sample {} at QP {}".format(sample_index, qp),
                    completed=completed,
                )

                encoded = _run_sample_encode(
                    row, source_path, start, sample_length, qp, output_path
                )
                if not encoded.get("success"):
                    raise RuntimeError(
                        "QP {} sample encode failed: {}".format(qp, encoded.get("error") or "unknown error")
                    )

                file_bytes = os.path.getsize(output_path)
                video_bitrate = (file_bytes * 8.0) / float(sample_length)

                xpsnr = _run_quality_metric(
                    source_path, output_path, start, sample_length, "xpsnr"
                )
                ssim = _run_quality_metric(
                    source_path, output_path, start, sample_length, "ssim"
                )

                samples.append({
                    "sample_index": sample_index,
                    "start": start,
                    "length": sample_length,
                    "qp": qp,
                    "file": filename if keep_files else None,
                    "bytes": file_bytes,
                    "video_bitrate": video_bitrate,
                    "encode_seconds": encoded.get("elapsed"),
                    "used_hw_decode": encoded.get("used_hw_decode"),
                    "xpsnr": xpsnr.get("value"),
                    "ssim": ssim.get("value"),
                    "xpsnr_error": xpsnr.get("error") if not xpsnr.get("success") else None,
                    "ssim_error": ssim.get("error") if not ssim.get("success") else None,
                })

                completed += 1
                _job_update(job_id, completed=completed, current=None)

        qp_summary = _aggregate_qp_results(samples, sample_length)
        quality_complete = sum(1 for r in samples if r.get("xpsnr") is not None and r.get("ssim") is not None)

        result = {
            "metric_id": metric_id,
            "source_path": source_path,
            "sample_length": sample_length,
            "sample_starts": starts,
            "qp_values": qps,
            "quality_metrics": ["xpsnr", "ssim"],
            "quality_complete": quality_complete,
            "variant_count": len(samples),
            "qp_summary": qp_summary,
            "samples": samples,
            "retained": keep_files,
            "sample_directory": job_dir if keep_files else None,
        }

        if keep_files:
            with open(os.path.join(job_dir, "result.json"), "w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2, default=str)

        finished = time.time()
        _job_update(
            job_id,
            status="completed",
            stage="done",
            finished=finished,
            result=result,
            completed=total,
            current=None,
        )
    except Exception as exc:
        logger.exception("Adaptive manual sample test failed")
        _job_update(
            job_id,
            status="failed",
            stage="failed",
            finished=time.time(),
            error=str(exc),
            current=None,
        )
    finally:
        with _sample_job_lock:
            snapshot = dict(_sample_jobs.get(job_id) or {})
            _sample_active_job = None
        _persist_sample_run(snapshot)
        keep = bool(snapshot.get("keep_files"))
        if job_dir and not keep:
            try:
                shutil.rmtree(job_dir)
            except Exception:
                logger.exception("Unable to remove temporary adaptive sample directory")


def _start_sample_test(arguments):
    global _sample_active_job

    metric_id = _int(_arg(arguments, "id", 0))
    if not metric_id:
        return {"success": False, "message": "A metrics record ID is required."}

    plan = _sample_plan({"id": metric_id})
    if not plan.get("success"):
        return plan
    if not (plan.get("plan") or {}).get("can_execute_safely"):
        return {
            "success": False,
            "message": (plan.get("source_check") or {}).get("message") or "Original source is not safely available.",
        }

    with _sample_job_lock:
        if _sample_active_job:
            active = _sample_jobs.get(_sample_active_job) or {}
            if active.get("status") in ("queued", "running"):
                return {
                    "success": False,
                    "message": "A sample test is already running.",
                    "job_id": _sample_active_job,
                }

        job_id = "{}-{}".format(metric_id, uuid.uuid4().hex[:10])
        record = plan.get("record") or {}
        job = {
            "id": job_id,
            "metric_id": metric_id,
            "file_name": record.get("file_name"),
            "source_path": (plan.get("source_check") or {}).get("path"),
            "status": "queued",
            "stage": "queued",
            "started": time.time(),
            "finished": None,
            "total": (plan.get("plan") or {}).get("encode_variants") or 0,
            "completed": 0,
            "current": None,
            "keep_files": bool(settings.get_setting("keep_sample_files")),
            "error": None,
            "result": None,
        }
        _sample_jobs[job_id] = job
        _sample_active_job = job_id

    thread = threading.Thread(
        target=_sample_test_worker,
        args=(job_id, metric_id),
        name="adaptive-sample-{}".format(job_id),
        daemon=True,
    )
    thread.start()

    return {"success": True, "job_id": job_id, "job": job}


def _sample_test_status(arguments):
    job_id = str(_arg(arguments, "job_id", "") or "").strip()
    if not job_id:
        return {"success": False, "message": "A sample-test job ID is required."}
    with _sample_job_lock:
        job = _sample_jobs.get(job_id)
        if job is None:
            return {"success": False, "message": "Sample-test job was not found in this plugin session."}
        return {"success": True, "job": dict(job)}


def _sample_test_settings():
    return {
        "success": True,
        "keep_sample_files": bool(settings.get_setting("keep_sample_files")),
        "sample_count": _int(settings.get_setting("sample_count")) or 4,
        "tv_sample_seconds": _int(settings.get_setting("tv_sample_seconds")) or 30,
        "movie_sample_seconds": _int(settings.get_setting("movie_sample_seconds")) or 45,
        "sample_root": _sample_root(),
    }


def _overview(arguments):
    conn = _metrics_db()
    if conn is None:
        return {
            "success": False,
            "connected": False,
            "message": "File Size Metrics Plus database was not found. Install and run File Size Metrics Plus first.",
            "metrics_db": _metrics_db_path(),
        }

    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(metrics)").fetchall()}
        required_columns = {
            "encoder_name", "source_total_bitrate", "dest_total_bitrate",
            "source_video_bitrate", "dest_video_bitrate", "encoder_quality",
        }
        missing = sorted(required_columns - columns)

        rows = conn.execute(
            """
            SELECT *
            FROM metrics
            WHERE success=1
              AND imported=0
              AND encoder_name IS NOT NULL
              AND LOWER(encoder_name) LIKE '%nvenc%'
            ORDER BY finish_time DESC, id DESC
            """
        ).fetchall()

        analyzed = [_diagnose(row) for row in rows]
        complete = [x for x in analyzed if x.get("training_eligible")]
        qps = [_float(x.get("encoder_quality")) for x in complete]
        reductions = [_float(x.get("percent_saved")) for x in complete]
        speeds = [_float(x.get("encode_speed")) for x in complete]

        qp_counts = {}
        for value in qps:
            if value is None:
                continue
            key = str(int(value) if float(value).is_integer() else value)
            qp_counts[key] = qp_counts.get(key, 0) + 1

        diagnosis_counts = {}
        for item in analyzed:
            diagnosis_counts[item["diagnosis"]] = diagnosis_counts.get(item["diagnosis"], 0) + 1

        minimum_training = 10
        readiness_count = len(complete)
        if missing:
            readiness = "Metrics Plus upgrade required"
        elif readiness_count >= 30:
            readiness = "Strong baseline"
        elif readiness_count >= minimum_training:
            readiness = "Baseline ready"
        else:
            readiness = "Collecting baseline"

        limit = max(10, min(250, _int(_arg(arguments, "limit", 100)) or 100))
        sort_mode = str(_arg(arguments, "sort", "newest") or "newest").strip().lower()
        if sort_mode == "priority":
            candidates = sorted(
                analyzed,
                key=lambda x: (x.get("priority") or 0, x.get("dest_size") or 0, x.get("finish_time") or 0),
                reverse=True,
            )[:limit]
        else:
            sort_mode = "newest"
            candidates = sorted(
                analyzed,
                key=lambda x: (x.get("finish_time") or 0, x.get("id") or 0),
                reverse=True,
            )[:limit]

        latest_finish = max(
            [x.get("finish_time") or 0 for x in analyzed] or [0]
        )
        try:
            db_mtime = os.path.getmtime(_metrics_db_path())
        except OSError:
            db_mtime = None
        wal_path = _metrics_db_path() + "-wal"
        try:
            wal_mtime = os.path.getmtime(wal_path)
        except OSError:
            wal_mtime = None

        return {
            "success": True,
            "connected": True,
            "metrics_db": _metrics_db_path(),
            "missing_columns": missing,
            "summary": {
                "nvenc_records": len(analyzed),
                "complete_records": len(complete),
                "minimum_training_records": minimum_training,
                "readiness": readiness,
                "average_reduction": _mean(reductions),
                "median_qp": _median(qps),
                "average_speed": _mean(speeds),
                "qp_counts": qp_counts,
                "diagnosis_counts": diagnosis_counts,
                "latest_finish_time": latest_finish or None,
                "metrics_db_mtime": db_mtime,
                "metrics_wal_mtime": wal_mtime,
                "sort_mode": sort_mode,
            },
            "candidates": candidates,
            "learning_mode": True,
        }
    finally:
        conn.close()


def _installed_plugin_record():
    try:
        records = PluginsHandler().get_plugin_list_filtered_and_sorted(plugin_id=PLUGIN_ID)
        for record in records or []:
            return {
                "success": True,
                "id": record.get("id"),
                "plugin_id": record.get("plugin_id"),
                "version": record.get("version"),
                "update_available": record.get("update_available"),
            }
    except Exception:
        logger.exception("Unable to find installed plugin record")
    return {"success": False, "message": "Installed plugin record was not found."}


def _refresh_custom_repo_cache_direct(force=False):
    global _last_direct_repo_refresh

    now = time.time()
    if not force and (now - _last_direct_repo_refresh) < _REPO_REFRESH_INTERVAL:
        return {"success": True, "skipped": True}

    handler = PluginsHandler()
    matching = []
    for repo in handler.get_plugin_repos():
        path = str(repo.get("path") or "")
        if CUSTOM_REPO_MATCH.lower() in path.lower():
            matching.append(path)

    if not matching:
        return {"success": False, "message": "Custom repository is not configured in Unmanic."}

    updated = []
    for repo_path in matching:
        separator = "&" if "?" in repo_path else "?"
        fetch_url = "{}{}adaptive_nvenc_cache_bust={}".format(repo_path, separator, int(now))
        response = requests.get(
            fetch_url,
            timeout=15,
            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        )
        response.raise_for_status()
        repo_data = response.json()

        plugins = repo_data.get("plugins") or []
        plugin_entry = next((p for p in plugins if p.get("id") == PLUGIN_ID), None)
        if not plugin_entry:
            raise RuntimeError("Repository JSON does not contain {}.".format(PLUGIN_ID))

        repo_id = handler.get_plugin_repo_id(repo_path)
        cache_file = handler.get_repo_cache_file(repo_id)
        tmp_file = cache_file + ".adaptive.tmp"
        with open(tmp_file, "w", encoding="utf-8") as fh:
            json.dump(repo_data, fh, indent=4)
        os.replace(tmp_file, cache_file)
        updated.append({
            "repo": repo_path,
            "repo_id": repo_id,
            "cache_file": cache_file,
            "version": plugin_entry.get("version"),
        })

    _last_direct_repo_refresh = now
    return {"success": True, "updated": updated}


def _self_update_worker(repo_id, requested_version):
    global _self_update_state
    try:
        # Let the HTTP response that scheduled this update complete before this
        # plugin's files/module are replaced and reloaded by Unmanic.
        time.sleep(1.0)
        success = PluginsHandler().install_plugin_by_id(PLUGIN_ID, repo_id=repo_id)
        with _self_update_lock:
            _self_update_state = {
                "running": False,
                "requested_version": requested_version,
                "error": None if success else "Unmanic returned False while installing the update.",
            }
    except Exception as exc:
        logger.exception("Background self-update failed")
        with _self_update_lock:
            _self_update_state = {
                "running": False,
                "requested_version": requested_version,
                "error": str(exc),
            }


def _start_self_update():
    global _self_update_state

    with _self_update_lock:
        if _self_update_state.get("running"):
            return {
                "success": True,
                "scheduled": True,
                "already_running": True,
                "version": _self_update_state.get("requested_version"),
            }

    refreshed = _refresh_custom_repo_cache_direct(force=True)
    if not refreshed.get("success"):
        return refreshed

    candidates = refreshed.get("updated") or []
    if not candidates:
        return {"success": False, "message": "Custom repository refresh returned no matching repository."}

    target = candidates[0]
    requested_version = target.get("version")
    repo_id = target.get("repo_id")

    with _self_update_lock:
        _self_update_state = {
            "running": True,
            "requested_version": requested_version,
            "error": None,
        }

    thread = threading.Thread(
        target=_self_update_worker,
        args=(repo_id, requested_version),
        name="{}-self-update".format(PLUGIN_ID),
        daemon=True,
    )
    thread.start()

    return {
        "success": True,
        "scheduled": True,
        "version": requested_version,
    }


def _self_update_status():
    record = _installed_plugin_record()
    with _self_update_lock:
        state = dict(_self_update_state)
    return {
        "success": True,
        "state": state,
        "installed": record,
    }


def render_frontend_panel(data):
    path = str(data.get("path") or "").strip("/")
    args = data.get("arguments") or {}

    if path == "":
        try:
            _refresh_custom_repo_cache_direct()
        except Exception:
            logger.exception("Direct custom repository refresh failed.")

    if path == "overview":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_overview(args), default=str)
        return data

    if path == "samplePlan":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_sample_plan(args), default=str)
        return data

    if path == "startSampleTest":
        try:
            result = _start_sample_test(args)
        except Exception as exc:
            logger.exception("Unable to start adaptive sample test")
            result = {"success": False, "message": str(exc)}
        data["content_type"] = "application/json"
        data["content"] = json.dumps(result, default=str)
        return data

    if path == "sampleTestStatus":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_sample_test_status(args), default=str)
        return data

    if path == "sampleSettings":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_sample_test_settings(), default=str)
        return data

    if path == "updateSelf":
        try:
            result = _start_self_update()
        except Exception as exc:
            logger.exception("Unable to schedule self-update")
            result = {"success": False, "message": str(exc)}
        data["content_type"] = "application/json"
        data["content"] = json.dumps(result, default=str)
        return data

    if path == "updateStatus":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_self_update_status(), default=str)
        return data

    if path == "selfRecord":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_installed_plugin_record(), default=str)
        return data

    if path == "refreshRepo":
        try:
            result = _refresh_custom_repo_cache_direct(force=True)
        except Exception as exc:
            logger.exception("Direct custom repository refresh failed.")
            result = {"success": False, "message": str(exc)}
        data["content_type"] = "application/json"
        data["content"] = json.dumps(result, default=str)
        return data

    static_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(static_path, "r", encoding="utf-8") as fh:
        data["content_type"] = "text/html"
        data["content"] = fh.read()
    return data
