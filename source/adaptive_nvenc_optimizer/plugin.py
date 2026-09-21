#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import os
import sqlite3
import statistics
import subprocess
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


class Settings(PluginSettings):
    settings = {}


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

    if completeness >= 75:
        if audio_share is not None and audio_share >= 45:
            status = "Audio-limited"
            reason = "Video compressed substantially, but audio is now a large share of the final bitrate."
            priority = 35.0
        elif saved_pct is not None and video_reduction is not None and saved_pct >= 45 and video_reduction >= 45:
            status = "Good compression"
            reason = "Both total file size and video bitrate dropped strongly at the current NVENC settings."
            priority = 10.0
        elif source_bpppf is not None and source_bpppf <= 0.055:
            status = "Already efficient"
            reason = "The source video bitrate is already low for its resolution and frame rate."
            priority = 15.0
        elif video_reduction is not None and video_reduction < 25:
            status = "Sample-test candidate"
            reason = "The video bitrate did not fall much; a controlled QP sample test may find additional savings."
            priority = 80.0
        elif saved_pct is not None and saved_pct < 25:
            status = "Sample-test candidate"
            reason = "Overall storage savings were modest; the source is worth profiling before a full retry."
            priority = 70.0
        else:
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


def _sample_timestamps(duration, sample_length):
    duration = _float(duration)
    if not duration or duration <= sample_length + 20:
        return []
    positions = (0.10, 0.35, 0.60, 0.85)
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
        sample_length = 45 if duration and duration >= 3600 else 30
        starts = _sample_timestamps(duration, sample_length)

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
                "mode": "planning_only",
            },
        }
    finally:
        conn.close()


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
        complete = [x for x in analyzed if x["completeness"] >= 75]
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
        candidates = sorted(
            analyzed,
            key=lambda x: (x.get("priority") or 0, x.get("dest_size") or 0),
            reverse=True,
        )[:limit]

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
