#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import datetime as dt
import io
import json
import os
import sqlite3
import subprocess
import uuid

from unmanic.libs.library import Library
from unmanic.libs.logs import UnmanicLogging
from unmanic.libs.unplugins.settings import PluginSettings

PLUGIN_ID = "file_size_metrics_plus"
logger = UnmanicLogging.get_logger(name="Unmanic.Plugin.file_size_metrics_plus")


class Settings(PluginSettings):
    settings = {}


settings = Settings()
PROFILE = settings.get_profile_directory()
DB_PATH = os.path.join(PROFILE, "metrics_plus.db")


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
        if s.get("channels"):
            label += f" {s.get('channels')}ch"
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
        total = conn.execute("SELECT COUNT(*) FROM metrics" + where, params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM metrics{where} ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size],
        ).fetchall()
        summary = conn.execute(
            "SELECT COUNT(*) c, SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) ok, "
            "SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) fail, SUM(source_size) src, SUM(dest_size) dst, "
            "SUM(bytes_saved) saved, SUM(duration) dur FROM metrics" + where,
            params,
        ).fetchone()
        libraries = [dict(r) for r in conn.execute(
            "SELECT DISTINCT library_id id, COALESCE(library_name,'Library '||library_id) name FROM metrics "
            "WHERE library_id IS NOT NULL ORDER BY name"
        ).fetchall()]
        codecs = [r[0] for r in conn.execute(
            "SELECT codec FROM (SELECT source_codec codec FROM metrics UNION SELECT dest_codec codec FROM metrics) "
            "WHERE codec IS NOT NULL AND codec<>'' ORDER BY codec"
        ).fetchall()]
        workers = [r[0] for r in conn.execute(
            "SELECT DISTINCT worker FROM metrics WHERE worker IS NOT NULL AND worker<>'' ORDER BY worker"
        ).fetchall()]
    src = summary["src"] or 0
    dst = summary["dst"] or 0
    return {
        "items": [dict(r) for r in rows], "total": total, "page": page,
        "pages": max(1, (total + size - 1) // size), "page_size": size,
        "summary": {
            "count": summary["c"] or 0, "success": summary["ok"] or 0, "failed": summary["fail"] or 0,
            "source": src, "dest": dst, "saved": summary["saved"] or 0,
            "percent": ((src - dst) / src * 100.0) if src else None, "duration": summary["dur"] or 0,
        },
        "options": {"libraries": libraries, "codecs": codecs, "workers": workers},
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


def render_frontend_panel(data):
    path = str(data.get("path") or "").strip("/")
    args = data.get("arguments") or {}
    if path == "list":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_list_data(args), default=str)
        return data
    if path == "details":
        with _db() as conn:
            row = conn.execute(
                "SELECT * FROM metrics WHERE id=?", (_num(_arg(args, "id", 0)) or 0,)
            ).fetchone()
        data["content_type"] = "application/json"
        data["content"] = json.dumps({"item": _rowdict(row)}, default=str)
        return data
    if path == "export":
        data["content_type"] = "text/csv; charset=utf-8"
        data["content"] = _csv(args)
        return data
    if path == "importLegacy":
        data["content_type"] = "application/json"
        data["content"] = json.dumps(_import_legacy())
        return data
    static = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(static, "r", encoding="utf-8") as f:
        data["content"] = f.read().replace("{cache_buster}", str(uuid.uuid4()))
    return data
