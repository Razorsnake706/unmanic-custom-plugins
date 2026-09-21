#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import datetime as dt
import io
import json
import os
import sqlite3
import subprocess
import time
import uuid

import requests

from unmanic.libs.library import Library
from unmanic.libs.logs import UnmanicLogging
from unmanic.libs.plugins import PluginsHandler
from unmanic.libs.unplugins.settings import PluginSettings

PLUGIN_ID = "file_size_metrics_plus"
logger = UnmanicLogging.get_logger(name="Unmanic.Plugin.file_size_metrics_plus")


class Settings(PluginSettings):
    settings = {}


settings = Settings()
PROFILE = settings.get_profile_directory()
DB_PATH = os.path.join(PROFILE, "metrics_plus.db")
CUSTOM_REPO_MATCH = "Razorsnake706/unmanic-custom-plugins"
_REPO_REFRESH_INTERVAL = 300
_last_direct_repo_refresh = 0.0


def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS pending (
      task_key TEXT PRIMARY KEY, task_id INTEGER, library_id INTEGER,
      source_path TEXT, source_size INTEGER, source_probe TEXT,
      worker TEXT, started REAL
    );
    CREATE TABLE IF NOT EXISTS metrics (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      task_key TEXT UNIQUE, task_id INTEGER, library_id INTEGER, library_name TEXT,
      file_name TEXT, success INTEGER NOT NULL DEFAULT 0,
      start_time REAL, finish_time REAL, duration REAL, worker TEXT,
      source_path TEXT, dest_path TEXT, source_size INTEGER, dest_size INTEGER,
      bytes_saved INTEGER, percent_saved REAL,
      source_codec TEXT, dest_codec TEXT,
      source_profile TEXT, dest_profile TEXT,
      source_width INTEGER, source_height INTEGER,
      dest_width INTEGER, dest_height INTEGER,
      source_pix_fmt TEXT, dest_pix_fmt TEXT,
      source_audio TEXT, dest_audio TEXT,
      imported INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_metrics_finish ON metrics(finish_time);
    CREATE INDEX IF NOT EXISTS idx_metrics_library ON metrics(library_id);
    CREATE INDEX IF NOT EXISTS idx_metrics_codecs ON metrics(source_codec, dest_codec);
    """)
    return conn


def _num(v):
    try:
        return int(v) if v is not None and str(v) != "" else None
    except Exception:
        return None


def _float(v):
    try:
        return float(v) if v is not None and str(v) != "" else None
    except Exception:
        return None


def _size(path):
    try:
        return os.path.getsize(path) if path and os.path.exists(path) else None
    except OSError:
        return None


def _key(data):
    task_id = data.get("task_id")
    library_id = data.get("library_id")
    path = (data.get("source_data") or {}).get("abspath") or ""
    return f"{task_id}|{library_id}|{path}"


def _library_name(library_id):
    try:
        return Library(int(library_id)).get_name() if library_id is not None else None
    except Exception:
        return f"Library {library_id}" if library_id is not None else None


def _probe(path):
    if not path or not os.path.exists(path):
        return {}
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        if p.returncode:
            return {}
        payload = json.loads(p.stdout or "{}")
    except Exception:
        logger.exception("ffprobe failed for %s", path)
        return {}
    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audios = []
    for s in streams:
        if s.get("codec_type") != "audio":
            continue
        label = s.get("codec_name") or "unknown"
        if s.get("profile") and str(s.get("profile")).lower() not in ("unknown", "none"):
            label += f" {s.get('profile')}"
        if s.get("channels"):
            label += f" {s.get('channels')}ch"
        bit_rate = _num(s.get("bit_rate"))
        if bit_rate:
            label += f" {round(bit_rate / 1000)}kbps"
        lang = (s.get("tags") or {}).get("language")
        if lang:
            label += f" {lang}"
        audios.append(label)
    return {
        "codec": video.get("codec_name"),
        "profile": video.get("profile"),
        "width": _num(video.get("width")),
        "height": _num(video.get("height")),
        "pix_fmt": video.get("pix_fmt"),
        "audio": ", ".join(audios) if audios else None,
    }


def emit_task_scheduled(data, task_data_store=None, file_metadata=None):
    try:
        source = (data.get("source_data") or {}).get("abspath")
        remote = data.get("remote_installation_info") or {}
        worker = remote.get("address") or remote.get("uuid") or "local"
        with _db() as conn:
            conn.execute("""
              INSERT INTO pending(task_key,task_id,library_id,source_path,source_size,source_probe,worker,started)
              VALUES(?,?,?,?,?,?,?,?)
              ON CONFLICT(task_key) DO UPDATE SET
                source_path=excluded.source_path, source_size=excluded.source_size,
                source_probe=excluded.source_probe, worker=excluded.worker, started=excluded.started
            """, (
                _key(data), _num(data.get("task_id")), _num(data.get("library_id")),
                source, _size(source), json.dumps(_probe(source)), worker, dt.datetime.now().timestamp(),
            ))
    except Exception:
        logger.exception("Unable to capture source metrics")


def _record_completion(data, worker_override=None, success_override=None):
    key = _key(data)
    source = (data.get("source_data") or {}).get("abspath")
    with _db() as conn:
        pending = conn.execute("SELECT * FROM pending WHERE task_key=?", (key,)).fetchone()
        source_size = pending["source_size"] if pending else _size(source)
        try:
            source_probe = json.loads(pending["source_probe"] or "{}") if pending else _probe(source)
        except Exception:
            source_probe = {}
        worker = worker_override or (pending["worker"] if pending else None) or "local"

        dest = None
        for candidate in data.get("destination_files") or []:
            if candidate and os.path.exists(candidate):
                dest = os.path.abspath(candidate)
                break
        if not dest:
            candidate = data.get("final_cache_path")
            if candidate and os.path.exists(candidate):
                dest = os.path.abspath(candidate)
        dest_size = _size(dest)
        dest_probe = _probe(dest)

        success = success_override
        if success is None:
            processing = data.get("task_processing_success")
            movement = data.get("file_move_processes_success")
            success = bool(processing) and movement is not False
        start = _float(data.get("start_time"))
        finish = _float(data.get("finish_time")) or dt.datetime.now().timestamp()
        duration = max(0.0, finish - start) if start is not None else None
        saved = source_size - dest_size if source_size is not None and dest_size is not None else None
        pct = (saved / source_size * 100.0) if saved is not None and source_size else None
        file_name = os.path.basename(dest or source or "UNKNOWN")
        library_id = _num(data.get("library_id"))

        values = (
            key, _num(data.get("task_id")), library_id, _library_name(library_id), file_name,
            1 if success else 0, start, finish, duration, worker,
            source, dest, source_size, dest_size, saved, pct,
            source_probe.get("codec"), dest_probe.get("codec"),
            source_probe.get("profile"), dest_probe.get("profile"),
            source_probe.get("width"), source_probe.get("height"),
            dest_probe.get("width"), dest_probe.get("height"),
            source_probe.get("pix_fmt"), dest_probe.get("pix_fmt"),
            source_probe.get("audio"), dest_probe.get("audio"), 0,
        )
        conn.execute("""
          INSERT INTO metrics(
            task_key,task_id,library_id,library_name,file_name,success,start_time,finish_time,duration,worker,
            source_path,dest_path,source_size,dest_size,bytes_saved,percent_saved,
            source_codec,dest_codec,source_profile,dest_profile,source_width,source_height,dest_width,dest_height,
            source_pix_fmt,dest_pix_fmt,source_audio,dest_audio,imported
          ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(task_key) DO UPDATE SET
            library_name=excluded.library_name,file_name=excluded.file_name,success=excluded.success,
            start_time=excluded.start_time,finish_time=excluded.finish_time,duration=excluded.duration,
            worker=excluded.worker,source_path=excluded.source_path,dest_path=excluded.dest_path,
            source_size=excluded.source_size,dest_size=excluded.dest_size,bytes_saved=excluded.bytes_saved,
            percent_saved=excluded.percent_saved,source_codec=excluded.source_codec,dest_codec=excluded.dest_codec,
            source_profile=excluded.source_profile,dest_profile=excluded.dest_profile,
            source_width=excluded.source_width,source_height=excluded.source_height,
            dest_width=excluded.dest_width,dest_height=excluded.dest_height,
            source_pix_fmt=excluded.source_pix_fmt,dest_pix_fmt=excluded.dest_pix_fmt,
            source_audio=excluded.source_audio,dest_audio=excluded.dest_audio
        """, values)
        conn.execute("DELETE FROM pending WHERE task_key=?", (key,))


def on_postprocessor_task_results(data, task_data_store=None, file_metadata=None):
    try:
        _record_completion(data)
    except Exception:
        logger.exception("Unable to record completion metrics")


def emit_postprocessor_complete(data, task_data_store=None, file_metadata=None):
    try:
        key = _key(data)
        worker = data.get("processed_by_worker")
        success = data.get("task_success")
        with _db() as conn:
            row = conn.execute("SELECT id FROM metrics WHERE task_key=?", (key,)).fetchone()
            if row:
                if worker is not None or success is not None:
                    conn.execute(
                        "UPDATE metrics SET worker=COALESCE(?,worker), success=COALESCE(?,success) WHERE task_key=?",
                        (worker, None if success is None else (1 if success else 0), key),
                    )
                return
        _record_completion(data, worker_override=worker, success_override=success)
    except Exception:
        logger.exception("Unable to update completion event metrics")


def _arg(arguments, name, default=""):
    value = (arguments or {}).get(name, default)
    if isinstance(value, list):
        value = value[0] if value else default
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return value


def _date_ts(value, end=False):
    if not value:
        return None
    try:
        d = dt.datetime.strptime(str(value), "%Y-%m-%d")
        if end:
            d = d + dt.timedelta(days=1) - dt.timedelta(microseconds=1)
        return d.timestamp()
    except Exception:
        return None


def _where(arguments):
    clauses, params = [], []
    search = str(_arg(arguments, "search", "")).strip()
    if search:
        clauses.append("(file_name LIKE ? OR source_path LIKE ? OR dest_path LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    status = str(_arg(arguments, "status", "all"))
    if status == "success":
        clauses.append("success=1")
    elif status == "failed":
        clauses.append("success=0")
    library = _arg(arguments, "library", "")
    if library not in (None, ""):
        clauses.append("library_id=?")
        params.append(_num(library))
    for key, col in (("source_codec", "source_codec"), ("dest_codec", "dest_codec"), ("worker", "worker")):
        value = str(_arg(arguments, key, "")).strip()
        if value:
            clauses.append(f"{col}=?")
            params.append(value)
    change = str(_arg(arguments, "change", "all"))
    if change == "saved":
        clauses.append("bytes_saved>0")
    elif change == "grew":
        clauses.append("bytes_saved<0")
    elif change == "same":
        clauses.append("bytes_saved=0")
    from_ts = _date_ts(_arg(arguments, "date_from", ""))
    to_ts = _date_ts(_arg(arguments, "date_to", ""), end=True)
    if from_ts is not None:
        clauses.append("finish_time>=?")
        params.append(from_ts)
    if to_ts is not None:
        clauses.append("finish_time<=?")
        params.append(to_ts)
    min_pct = _float(_arg(arguments, "min_percent", ""))
    max_pct = _float(_arg(arguments, "max_percent", ""))
    if min_pct is not None:
        clauses.append("percent_saved>=?")
        params.append(min_pct)
    if max_pct is not None:
        clauses.append("percent_saved<=?")
        params.append(max_pct)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _rowdict(row):
    return dict(row) if row else None


def _norm_path(value):
    if not value:
        return None
    try:
        return os.path.normcase(os.path.normpath(str(value))).replace("\\", "/").rstrip("/")
    except Exception:
        return str(value).replace("\\", "/").rstrip("/").lower()


def _row_tokens(row):
    """Return stable identity tokens for linking multiple processing passes."""
    tokens = set()
    source = _norm_path(row["source_path"] if isinstance(row, sqlite3.Row) else row.get("source_path"))
    dest = _norm_path(row["dest_path"] if isinstance(row, sqlite3.Row) else row.get("dest_path"))
    if source:
        tokens.add("path:" + source)
    if dest:
        tokens.add("path:" + dest)
    if not tokens:
        library_id = row["library_id"] if isinstance(row, sqlite3.Row) else row.get("library_id")
        file_name = row["file_name"] if isinstance(row, sqlite3.Row) else row.get("file_name")
        tokens.add("name:{}:{}".format(library_id or "", str(file_name or "").lower()))
    return tokens


def _classify_pass(row):
    data = dict(row) if isinstance(row, sqlite3.Row) else row
    video_changed = any([
        data.get("source_codec") and data.get("dest_codec") and data.get("source_codec") != data.get("dest_codec"),
        data.get("source_profile") and data.get("dest_profile") and data.get("source_profile") != data.get("dest_profile"),
        data.get("source_pix_fmt") and data.get("dest_pix_fmt") and data.get("source_pix_fmt") != data.get("dest_pix_fmt"),
        data.get("source_width") and data.get("dest_width") and data.get("source_width") != data.get("dest_width"),
        data.get("source_height") and data.get("dest_height") and data.get("source_height") != data.get("dest_height"),
    ])
    audio_changed = bool(
        data.get("source_audio") and data.get("dest_audio")
        and data.get("source_audio") != data.get("dest_audio")
    )
    if video_changed and audio_changed:
        return "Video + Audio"
    if video_changed:
        return "Video"
    if audio_changed:
        return "Audio"
    if data.get("imported"):
        return "Legacy"
    return "Other"


def _group_rows(rows):
    """Group task rows when their source/destination paths form the same media chain."""
    rows = [dict(r) if isinstance(r, sqlite3.Row) else dict(r) for r in rows]
    if not rows:
        return []

    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    token_owner = {}
    for i, row in enumerate(rows):
        for token in _row_tokens(row):
            if token in token_owner:
                union(i, token_owner[token])
            else:
                token_owner[token] = i

    buckets = {}
    for i, row in enumerate(rows):
        buckets.setdefault(find(i), []).append(row)

    groups = []
    for members in buckets.values():
        members.sort(key=lambda r: (r.get("finish_time") or 0, r.get("id") or 0))
        first, last = members[0], members[-1]

        source_size = next((m.get("source_size") for m in members if m.get("source_size") is not None), None)
        dest_size = next((m.get("dest_size") for m in reversed(members) if m.get("dest_size") is not None), None)
        saved = source_size - dest_size if source_size is not None and dest_size is not None else None
        pct = (saved / source_size * 100.0) if saved is not None and source_size else None

        source_codec = next((m.get("source_codec") for m in members if m.get("source_codec")), None)
        dest_codec = next((m.get("dest_codec") for m in reversed(members) if m.get("dest_codec")), None)
        source_audio = next((m.get("source_audio") for m in members if m.get("source_audio")), None)
        dest_audio = next((m.get("dest_audio") for m in reversed(members) if m.get("dest_audio")), None)

        libraries = []
        workers = []
        pass_types = []
        for m in members:
            if m.get("library_name") and m.get("library_name") not in libraries:
                libraries.append(m.get("library_name"))
            if m.get("worker") and m.get("worker") not in workers:
                workers.append(m.get("worker"))
            ptype = _classify_pass(m)
            if ptype not in pass_types:
                pass_types.append(ptype)

        combined = dict(last)
        combined.update({
            "id": last.get("id"),
            "grouped": 1,
            "pass_count": len(members),
            "pass_types": pass_types,
            "file_name": last.get("file_name") or first.get("file_name"),
            "success": 1 if all(bool(m.get("success")) for m in members) else 0,
            "start_time": next((m.get("start_time") for m in members if m.get("start_time") is not None), first.get("start_time")),
            "finish_time": last.get("finish_time"),
            "duration": sum(float(m.get("duration") or 0) for m in members),
            "library_name": libraries[0] if len(libraries) == 1 else ("{} libraries".format(len(libraries)) if libraries else None),
            "worker": workers[0] if len(workers) == 1 else ("{} workers".format(len(workers)) if workers else None),
            "source_path": first.get("source_path") or first.get("dest_path"),
            "dest_path": last.get("dest_path") or last.get("source_path"),
            "source_size": source_size,
            "dest_size": dest_size,
            "bytes_saved": saved,
            "percent_saved": pct,
            "source_codec": source_codec,
            "dest_codec": dest_codec,
            "source_audio": source_audio,
            "dest_audio": dest_audio,
            "imported": 1 if all(bool(m.get("imported")) for m in members) else 0,
            "group_ids": [m.get("id") for m in members],
        })
        groups.append(combined)
    return groups


def _sort_items(items, sort, direction):
    reverse = direction == "DESC"

    def key(row):
        value = row.get(sort)
        if value is None:
            return (1, "")
        if isinstance(value, str):
            return (0, value.lower())
        return (0, value)

    return sorted(items, key=key, reverse=reverse)


def _summary_for_items(items):
    source = sum(int(x.get("source_size") or 0) for x in items)
    dest = sum(int(x.get("dest_size") or 0) for x in items)
    return {
        "count": len(items),
        "passes": sum(int(x.get("pass_count") or 1) for x in items),
        "success": sum(1 for x in items if x.get("success")),
        "failed": sum(1 for x in items if not x.get("success")),
        "source": source,
        "dest": dest,
        "saved": sum(int(x.get("bytes_saved") or 0) for x in items),
        "percent": ((source - dest) / source * 100.0) if source else None,
        "duration": sum(float(x.get("duration") or 0) for x in items),
    }


def _related_history(conn, row):
    if not row:
        return []
    all_rows = [dict(r) for r in conn.execute("SELECT * FROM metrics ORDER BY finish_time ASC, id ASC").fetchall()]
    target_tokens = set(_row_tokens(dict(row)))
    related = []
    changed = True
    while changed:
        changed = False
        for item in all_rows:
            if item in related:
                continue
            tokens = _row_tokens(item)
            if tokens & target_tokens:
                related.append(item)
                before = len(target_tokens)
                target_tokens.update(tokens)
                changed = changed or len(target_tokens) != before
    related.sort(key=lambda r: (r.get("finish_time") or 0, r.get("id") or 0))
    for item in related:
        item["pass_type"] = _classify_pass(item)
    return related


def _available_options(conn):
    """Return filter values independently of the current table filters.

    Libraries come from Unmanic itself so the dropdown is populated even before
    this plugin has recorded a task for every library. Codec/worker values are
    merged from all stored metrics, including records outside the current filter.
    """
    libraries_by_id = {}
    try:
        for lib in Library.get_all_libraries():
            lib_id = _num(lib.get("id"))
            if lib_id is None:
                continue
            libraries_by_id[lib_id] = {
                "id": lib_id,
                "name": lib.get("name") or f"Library {lib_id}",
            }
    except Exception:
        logger.exception("Unable to read Unmanic library list for metrics filters.")

    for row in conn.execute(
        "SELECT DISTINCT library_id id, COALESCE(library_name,'Library '||library_id) name "
        "FROM metrics WHERE library_id IS NOT NULL"
    ).fetchall():
        row = dict(row)
        if row.get("id") is not None and row.get("id") not in libraries_by_id:
            libraries_by_id[row["id"]] = row

    codecs = [r[0] for r in conn.execute(
        "SELECT codec FROM (SELECT source_codec codec FROM metrics UNION SELECT dest_codec codec FROM metrics) "
        "WHERE codec IS NOT NULL AND TRIM(codec)<>'' ORDER BY codec"
    ).fetchall()]
    workers = [r[0] for r in conn.execute(
        "SELECT DISTINCT worker FROM metrics WHERE worker IS NOT NULL AND TRIM(worker)<>'' ORDER BY worker"
    ).fetchall()]

    return {
        "libraries": sorted(libraries_by_id.values(), key=lambda x: str(x.get("name", "")).lower()),
        "codecs": codecs,
        "workers": workers,
    }


def _list_data(arguments):
    where, params = _where(arguments)
    sort_map = {
        "finish_time": "finish_time", "file_name": "file_name", "library_name": "library_name",
        "source_codec": "source_codec", "dest_codec": "dest_codec", "source_size": "source_size",
        "dest_size": "dest_size", "bytes_saved": "bytes_saved", "percent_saved": "percent_saved",
        "duration": "duration", "worker": "worker",
    }
    sort = sort_map.get(str(_arg(arguments, "sort", "finish_time")), "finish_time")
    direction = "ASC" if str(_arg(arguments, "dir", "desc")).lower() == "asc" else "DESC"
    page = max(1, _num(_arg(arguments, "page", 1)) or 1)
    size = min(250, max(10, _num(_arg(arguments, "page_size", 50)) or 50))

    with _db() as conn:
        filtered_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM metrics" + where, params
        ).fetchall()]
        options = _available_options(conn)

    items = _sort_items(filtered_rows, sort, direction)
    total = len(items)
    start_index = (page - 1) * size
    page_items = items[start_index:start_index + size]
    summary = _summary_for_items(items)

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "pages": max(1, (total + size - 1) // size),
        "page_size": size,
        "summary": summary,
        "options": options,
    }


def _to_ts(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    try:
        return float(text)
    except Exception:
        pass
    try:
        return dt.datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def _import_legacy():
    legacy = os.path.join(os.path.dirname(PROFILE), "file_size_metrics", "history.db")
    if not os.path.exists(legacy):
        return {"success": False, "message": "Official File Size Metrics history.db was not found."}
    imported = 0
    try:
        old = sqlite3.connect(legacy)
        old.row_factory = sqlite3.Row
        tasks = old.execute("SELECT * FROM historictasks").fetchall()
        with _db() as conn:
            for task in tasks:
                probes = old.execute(
                    "SELECT * FROM historictaskprobe WHERE historictask_id=? ORDER BY id", (task["id"],)
                ).fetchall()
                source = next((p for p in probes if p["type"] == "source"), None)
                dest = next((p for p in probes if p["type"] == "destination"), None)
                if not source and not dest:
                    continue
                source_size = _num(source["size"]) if source else None
                dest_size = _num(dest["size"]) if dest else None
                saved = source_size - dest_size if source_size is not None and dest_size is not None else None
                pct = saved / source_size * 100.0 if saved is not None and source_size else None
                start = _to_ts(task["start_time"])
                finish = _to_ts(task["finish_time"])
                duration = finish - start if start is not None and finish is not None else None
                cur = conn.execute("""
                  INSERT OR IGNORE INTO metrics(
                    task_key,file_name,success,start_time,finish_time,duration,source_path,dest_path,
                    source_size,dest_size,bytes_saved,percent_saved,imported
                  ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)
                """, (
                    f"legacy:{task['id']}", task["task_label"], 1 if task["task_success"] else 0,
                    start, finish, duration, source["abspath"] if source else None, dest["abspath"] if dest else None,
                    source_size, dest_size, saved, pct,
                ))
                imported += cur.rowcount
        old.close()
        return {"success": True, "message": f"Imported {imported} legacy records. Existing imports were skipped."}
    except Exception as exc:
        logger.exception("Legacy import failed")
        return {"success": False, "message": f"Legacy import failed: {exc}"}


def _matching_ids(arguments):
    where, params = _where(arguments)
    with _db() as conn:
        rows = conn.execute(
            "SELECT id FROM metrics" + where + " ORDER BY finish_time DESC, id DESC",
            params,
        ).fetchall()
    ids = [int(row["id"]) for row in rows]
    return {
        "success": True,
        "count": len(ids),
        "ids": ids,
    }


def _delete_entries(arguments):
    raw = str(_arg(arguments, "ids", "")).strip()
    ids = []
    for value in raw.split(","):
        value = value.strip()
        if not value:
            continue
        parsed = _num(value)
        if parsed is not None and parsed > 0:
            ids.append(parsed)

    # Preserve order while removing duplicate IDs.
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {"success": False, "deleted": 0, "message": "No valid metric entry IDs were provided."}

    placeholders = ",".join("?" for _ in ids)
    with _db() as conn:
        before = conn.total_changes
        conn.execute("DELETE FROM metrics WHERE id IN ({})".format(placeholders), ids)
        deleted = conn.total_changes - before

    return {
        "success": True,
        "deleted": deleted,
        "message": "Deleted {} metric entr{}.".format(
            deleted, "y" if deleted == 1 else "ies"
        ),
    }


def _csv(arguments):
    where, params = _where(arguments)
    with _db() as conn:
        rows = conn.execute("SELECT * FROM metrics" + where + " ORDER BY finish_time DESC", params).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    cols = [
        "finish_time", "file_name", "library_name", "success", "worker", "source_codec", "dest_codec",
        "source_size", "dest_size", "bytes_saved", "percent_saved", "duration", "source_path", "dest_path", "imported",
    ]
    w.writerow(cols)
    for row in rows:
        w.writerow([row[c] for c in cols])
    return out.getvalue()


def _refresh_custom_repo_cache_direct(force=False):
    """Refresh this custom repo directly from GitHub.

    Unmanic normally proxies repository metadata through the Unmanic API before
    writing its local repo cache. That proxy can serve stale metadata for custom
    repositories. Once this plugin is installed, bypass that proxy for this
    repository and replace only its local cache with the current raw GitHub JSON.
    """
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
        fetch_url = "{}{}fsmplus_cache_bust={}".format(repo_path, separator, int(now))
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
        tmp_file = cache_file + ".fsmplus.tmp"
        with open(tmp_file, "w", encoding="utf-8") as fh:
            json.dump(repo_data, fh, indent=4)
        os.replace(tmp_file, cache_file)
        updated.append({
            "repo": repo_path,
            "cache_file": cache_file,
            "version": plugin_entry.get("version"),
        })

    _last_direct_repo_refresh = now
    return {"success": True, "updated": updated}


def render_frontend_panel(data):
    path = str(data.get("path") or "").strip("/")
    args = data.get("arguments") or {}

    if path == "":
        try:
            _refresh_custom_repo_cache_direct()
        except Exception:
            logger.exception("Direct custom repository refresh failed.")
    if path == "list":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_list_data(args), default=str)
        return data
    if path == "details":
        with _db() as conn:
            row = conn.execute(
                "SELECT * FROM metrics WHERE id=?", (_num(_arg(args, "id", 0)) or 0,)
            ).fetchone()
            history = _related_history(conn, row) if row else []
        combined = _group_rows(history)[0] if history else _rowdict(row)
        data["content_type"] = "application/json"
        data["content"] = json.dumps({
            "item": _rowdict(row),
            "combined": combined,
            "history": history,
        }, default=str)
        return data
    if path == "export":
        data["content_type"] = "text/csv; charset=utf-8"
        data["content"] = _csv(args)
        return data
    if path == "importLegacy":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_import_legacy())
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
    if path == "matchingIds":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_matching_ids(args))
        return data
    if path == "delete":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_delete_entries(args))
        return data
    static = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(static, "r", encoding="utf-8") as f:
        data["content"] = f.read().replace("{cache_buster}", str(uuid.uuid4()))
    return data
