#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Manual One-Off Queue for Unmanic.

Provides an Unmanic data panel for browsing a configured library, choosing a
single media file, selecting installed processing plugins, and force-queueing
that file for a one-off run.

The queued task must be assigned to a dedicated scanner-disabled "manual"
library where this controller is the only worker.process plugin. The controller
then dispatches only the plugins selected for that task. Selected plugins read
settings using the source/settings library ID so existing TV/Movie plugin
configuration can be reused without changing the normal library flow.
"""

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from unmanic.libs.library import Library
from unmanic.libs.plugins import PluginsHandler
from unmanic.libs.unplugins import PluginExecutor
from unmanic.libs.unplugins.settings import PluginSettings
from unmanic.webserver.helpers import pending_tasks


PLUGIN_ID = "manual_oneoff_queue"
PLUGIN_NAME = "Manual One-Off Queue"
VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".ts", ".m2ts",
    ".webm", ".mpg", ".mpeg", ".flv", ".ogm", ".vob"
}
DISPATCHABLE_STAGES = {
    "worker.process",
    "postprocessor.file_move",
    "postprocessor.task_result",
}

logger = logging.getLogger("Unmanic.Plugin.manual_oneoff_queue")
_state_lock = threading.RLock()


class Settings(PluginSettings):
    """Settings container used primarily to obtain the plugin profile path."""

    settings = {}


def _profile_dir():
    settings = Settings()
    path = settings.get_profile_directory()
    os.makedirs(path, exist_ok=True)
    return path


def _state_path():
    return os.path.join(_profile_dir(), "manual_jobs.json")


def _empty_state():
    return {"jobs": {}, "pending_paths": {}}


def _load_state():
    with _state_lock:
        path = _state_path()
        if not os.path.exists(path):
            return _empty_state()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return _empty_state()
            data.setdefault("jobs", {})
            data.setdefault("pending_paths", {})
            return data
        except Exception:
            logger.exception("Unable to read manual queue state")
            return _empty_state()


def _save_state(state):
    with _state_lock:
        path = _state_path()
        fd, tmp = tempfile.mkstemp(prefix="manual_jobs_", suffix=".json", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _decode_argument(value, default=None):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        if not value:
            return default
        value = value[0]
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value


def _argument(data, name, default=None):
    return _decode_argument((data.get("arguments") or {}).get(name), default)


def _json_body(data):
    body = data.get("body", b"")
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if not body:
        return {}
    if isinstance(body, dict):
        return body
    return json.loads(body)


def _library_dict(library_id):
    lib = Library(int(library_id))
    source = next((x for x in Library.get_all_libraries() if int(x.get("id")) == int(library_id)), None)
    if source is None:
        source = {
            "id": lib.get_id(),
            "name": lib.get_name(),
            "path": lib.get_path(),
            "enable_scanner": False,
            "enable_inotify": False,
            "tags": [],
        }
    return source


def _plugin_types(plugin_id, executor=None):
    executor = executor or PluginExecutor()
    try:
        return executor.get_all_plugin_types_in_plugin(plugin_id) or []
    except Exception:
        logger.exception("Unable to inspect plugin types for %s", plugin_id)
        return []


def _installed_dispatchable_plugins():
    handler = PluginsHandler()
    executor = PluginExecutor()
    results = []
    try:
        rows = list(handler.get_plugin_list_filtered_and_sorted(order=[{"column": "name", "dir": "asc"}]))
    except Exception:
        logger.exception("Unable to list installed plugins")
        rows = []

    for row in rows:
        plugin_id = row.get("plugin_id")
        if not plugin_id or plugin_id == PLUGIN_ID:
            continue
        stages = _plugin_types(plugin_id, executor=executor)
        dispatchable = [stage for stage in stages if stage in DISPATCHABLE_STAGES]
        if not dispatchable:
            continue
        results.append({
            "plugin_id": plugin_id,
            "name": row.get("name") or plugin_id,
            "description": row.get("description") or "",
            "version": row.get("version") or "",
            "stages": dispatchable,
        })
    return results


def _manual_library_status(library_id):
    lib = Library(int(library_id))
    flow = lib.get_plugin_flow() or {}
    worker_flow = flow.get("worker.process", []) or []
    worker_ids = [p.get("plugin_id") for p in worker_flow if p.get("plugin_id")]
    enabled_ids = [p.get("plugin_id") for p in lib.get_enabled_plugins()]
    config = _library_dict(library_id)

    issues = []
    if PLUGIN_ID not in enabled_ids:
        issues.append("Manual One-Off Queue is not enabled on this library.")
    if worker_ids != [PLUGIN_ID]:
        issues.append(
            "For task-specific plugin selection, Manual One-Off Queue must be the only worker-process plugin in this library."
        )
    if config.get("enable_scanner"):
        issues.append("Disable the library scanner for the manual library.")
    if config.get("enable_inotify"):
        issues.append("Disable filesystem monitoring/inotify for the manual library.")

    return {
        "safe": not issues,
        "issues": issues,
        "worker_plugins": worker_ids,
    }


def _safe_join(root, relative):
    root_real = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root_real, relative or ""))
    try:
        common = os.path.commonpath([root_real, target])
    except ValueError:
        raise ValueError("Invalid path")
    if common != root_real:
        raise ValueError("Path escapes the selected library")
    return target


def _find_job(data):
    task_id = data.get("task_id")
    original_path = data.get("original_file_path") or data.get("source_data", {}).get("abspath")
    state = _load_state()
    job = None
    job_key = None

    if task_id is not None:
        job_key = str(task_id)
        job = state.get("jobs", {}).get(job_key)

    if job is None and original_path:
        provisional = state.get("pending_paths", {}).get(os.path.abspath(original_path))
        if provisional:
            job = provisional
            job_key = str(task_id) if task_id is not None else None
            if job_key:
                state["jobs"][job_key] = dict(provisional)
                state["jobs"][job_key]["task_id"] = task_id
                state["pending_paths"].pop(os.path.abspath(original_path), None)
                _save_state(state)

    return state, job_key, job


def _set_worker_index(task_id, original_path, index):
    state = _load_state()
    key = str(task_id) if task_id is not None else None
    if key and key in state.get("jobs", {}):
        state["jobs"][key]["worker_index"] = int(index)
    elif original_path and os.path.abspath(original_path) in state.get("pending_paths", {}):
        state["pending_paths"][os.path.abspath(original_path)]["worker_index"] = int(index)
    _save_state(state)


def _delete_job(task_id, original_path=None):
    state = _load_state()
    if task_id is not None:
        state.get("jobs", {}).pop(str(task_id), None)
    if original_path:
        state.get("pending_paths", {}).pop(os.path.abspath(original_path), None)
    _save_state(state)


def _dispatch_plugin(data, plugin_id, plugin_type, source_library_id):
    manual_library_id = data.get("library_id")
    executor = PluginExecutor()
    try:
        # Make the selected plugin read the same per-library settings it would use
        # in the user's normal TV/Movie library.
        data["library_id"] = int(source_library_id)
        return executor.execute_plugin_runner(data, plugin_id, plugin_type)
    finally:
        data["library_id"] = manual_library_id


def on_worker_process(data):
    """Dispatch only the worker plugins selected for this one-off task."""
    state, job_key, job = _find_job(data)
    if not job:
        logger.error("No manual queue metadata found for task %s", data.get("task_id"))
        raise RuntimeError("No Manual One-Off Queue metadata found for this task")

    selected = job.get("plugin_ids", [])
    executor = PluginExecutor()
    worker_plugins = [pid for pid in selected if "worker.process" in _plugin_types(pid, executor=executor)]
    index = int(job.get("worker_index", 0))

    if not worker_plugins:
        data["worker_log"].append("\nManual One-Off Queue: no worker-process plugins selected; nothing to execute.\n")
        data["repeat"] = False
        return

    if index >= len(worker_plugins):
        data["repeat"] = False
        return

    plugin_id = worker_plugins[index]
    data["worker_log"].append("\nManual One-Off Queue: dispatching '{}' ({}/{})\n".format(
        plugin_id, index + 1, len(worker_plugins)
    ))

    success = _dispatch_plugin(data, plugin_id, "worker.process", job.get("source_library_id"))
    if not success:
        raise RuntimeError("Selected plugin '{}' failed to execute".format(plugin_id))

    delegated_repeat = bool(data.get("repeat"))
    if not delegated_repeat:
        index += 1
        _set_worker_index(data.get("task_id"), data.get("original_file_path"), index)

    # Keep the controller alive until the delegated plugin is finished and all
    # selected worker plugins have been dispatched.
    data["repeat"] = delegated_repeat or index < len(worker_plugins)


def _dispatch_postprocessor_stage(data, plugin_type):
    state, job_key, job = _find_job(data)
    if not job:
        logger.warning("No manual queue metadata found for postprocessor task %s", data.get("task_id"))
        return

    selected = job.get("plugin_ids", [])
    executor = PluginExecutor()
    for plugin_id in selected:
        if plugin_type not in _plugin_types(plugin_id, executor=executor):
            continue
        success = _dispatch_plugin(data, plugin_id, plugin_type, job.get("source_library_id"))
        if not success:
            raise RuntimeError("Selected postprocessor plugin '{}' failed at '{}'".format(plugin_id, plugin_type))


def on_postprocessor_file_movement(data):
    """Delegate file-movement postprocessor hooks from selected plugins."""
    _dispatch_postprocessor_stage(data, "postprocessor.file_move")


def on_postprocessor_task_results(data):
    """Delegate task-result hooks, then remove the stored one-off task metadata."""
    try:
        _dispatch_postprocessor_stage(data, "postprocessor.task_result")
    finally:
        original_path = data.get("original_file_path") or data.get("source_data", {}).get("abspath")
        _delete_job(data.get("task_id"), original_path)


def render_frontend_panel(data):
    """Serve the Manual One-Off Queue panel."""
    index = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(index, "r", encoding="utf-8") as handle:
        data["content"] = handle.read()
    data["content_type"] = "text/html"


def _api_bootstrap(data):
    libraries = Library.get_all_libraries()
    plugin_list = _installed_dispatchable_plugins()
    manual_status = {}
    for lib in libraries:
        try:
            manual_status[str(lib.get("id"))] = _manual_library_status(lib.get("id"))
        except Exception as exc:
            manual_status[str(lib.get("id"))] = {"safe": False, "issues": [str(exc)], "worker_plugins": []}

    data["content"] = {
        "success": True,
        "libraries": libraries,
        "plugins": plugin_list,
        "manual_library_status": manual_status,
        "controller_plugin_id": PLUGIN_ID,
    }


def _api_browse(data):
    library_id = int(_argument(data, "library_id"))
    relative = _argument(data, "path", "") or ""
    lib = Library(library_id)
    root = lib.get_path()
    target = _safe_join(root, relative)
    if not os.path.isdir(target):
        raise ValueError("Browse target is not a directory")

    entries = []
    try:
        names = sorted(os.listdir(target), key=lambda x: x.lower())
    except PermissionError:
        raise ValueError("Unmanic cannot read this directory")

    for name in names:
        full = os.path.join(target, name)
        rel = os.path.relpath(full, root)
        if rel == ".":
            rel = ""
        if os.path.isdir(full):
            entries.append({"name": name, "type": "directory", "relative_path": rel})
        elif os.path.isfile(full) and Path(name).suffix.lower() in VIDEO_EXTENSIONS:
            entries.append({
                "name": name,
                "type": "file",
                "relative_path": rel,
                "absolute_path": os.path.abspath(full),
                "size": os.path.getsize(full),
            })

    parent = ""
    if relative:
        parent = os.path.dirname(relative.rstrip("/"))
        if parent == ".":
            parent = ""

    data["content"] = {
        "success": True,
        "library_id": library_id,
        "root": root,
        "relative_path": relative,
        "parent": parent,
        "entries": entries,
    }


def _api_queue(data):
    payload = _json_body(data)
    path = os.path.abspath(payload.get("path") or "")
    source_library_id = int(payload.get("source_library_id"))
    manual_library_id = int(payload.get("manual_library_id"))
    plugin_ids = payload.get("plugin_ids") or []
    priority_score = int(payload.get("priority_score", 0))

    if not path or not os.path.isfile(path):
        raise ValueError("Selected media file does not exist")

    source_lib = Library(source_library_id)
    source_root = os.path.realpath(source_lib.get_path())
    path_real = os.path.realpath(path)
    if os.path.commonpath([source_root, path_real]) != source_root:
        raise ValueError("Selected file is outside the source/settings library")

    manual_status = _manual_library_status(manual_library_id)
    if not manual_status.get("safe"):
        raise ValueError("Manual library is not safe: " + " ".join(manual_status.get("issues", [])))

    installed = {p["plugin_id"]: p for p in _installed_dispatchable_plugins()}
    clean_plugins = []
    for plugin_id in plugin_ids:
        if plugin_id == PLUGIN_ID:
            continue
        if plugin_id not in installed:
            raise ValueError("Plugin '{}' is not installed or has no supported processing stage".format(plugin_id))
        if plugin_id not in clean_plugins:
            clean_plugins.append(plugin_id)

    if not clean_plugins:
        raise ValueError("Select at least one processing plugin")

    if pending_tasks.check_if_task_exists_matching_path(path):
        raise ValueError("A task already exists for this file in Unmanic")

    provisional = {
        "task_id": None,
        "path": path,
        "source_library_id": source_library_id,
        "manual_library_id": manual_library_id,
        "plugin_ids": clean_plugins,
        "worker_index": 0,
    }

    # Write a path-keyed record before creating the task. This closes the tiny
    # race where an idle worker could collect the task before we have its ID.
    state = _load_state()
    state["pending_paths"][path] = provisional
    _save_state(state)

    try:
        task_info = pending_tasks.create_task(
            path,
            library_id=manual_library_id,
            task_type="local",
            priority_score=priority_score,
        )
        if not task_info:
            raise RuntimeError("Unmanic failed to create the pending task")

        task_id = task_info.get("id")
        state = _load_state()
        final = dict(state.get("pending_paths", {}).get(path, provisional))
        final["task_id"] = task_id
        state["jobs"][str(task_id)] = final
        state["pending_paths"].pop(path, None)
        _save_state(state)

        data["content"] = {
            "success": True,
            "task": task_info,
            "selected_plugins": clean_plugins,
            "source_library_id": source_library_id,
            "manual_library_id": manual_library_id,
        }
    except Exception:
        state = _load_state()
        state.get("pending_paths", {}).pop(path, None)
        _save_state(state)
        raise


def _api_jobs(data):
    state = _load_state()
    data["content"] = {"success": True, "jobs": state.get("jobs", {})}


def render_plugin_api(data):
    """REST-style API used by the embedded data panel."""
    try:
        action = _argument(data, "action", "bootstrap")
        method = (data.get("method") or "GET").upper()

        if action == "bootstrap" and method == "GET":
            _api_bootstrap(data)
        elif action == "browse" and method == "GET":
            _api_browse(data)
        elif action == "queue" and method == "POST":
            _api_queue(data)
        elif action == "jobs" and method == "GET":
            _api_jobs(data)
        else:
            data["status"] = 404
            data["content"] = {"success": False, "error": "Unknown API action"}
    except ValueError as exc:
        data["status"] = 400
        data["content"] = {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("Manual One-Off Queue API failure")
        data["status"] = 500
        data["content"] = {"success": False, "error": str(exc)}
