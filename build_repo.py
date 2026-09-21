#!/usr/bin/env python3
import hashlib
import json
import pathlib
import shutil
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "source"
DIST = ROOT / "dist"
OWNER = "Razorsnake706"
REPO = "unmanic-custom-plugins"
BRANCH = "repo"

if DIST.exists():
    shutil.rmtree(DIST)
DIST.mkdir()

plugins = []
release_manifest = []

for plugin_dir in sorted(p for p in SRC.iterdir() if p.is_dir()):
    info = json.loads((plugin_dir / "info.json").read_text())
    plugin_id = info["id"]
    version = info["version"]

    target = DIST / plugin_id
    target.mkdir(parents=True, exist_ok=True)
    for name in ("info.json", "description.md", "changelog.md"):
        if (plugin_dir / name).exists():
            shutil.copy2(plugin_dir / name, target / name)

    zip_name = f"{plugin_id}-{version}.zip"
    zip_path = target / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(plugin_dir.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            z.write(path, path.relative_to(plugin_dir))

    plugins.append(info)

    version_target = DIST / "versions" / plugin_id / version
    version_target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(zip_path, version_target / zip_name)
    for name in ("info.json", "description.md", "changelog.md"):
        if (plugin_dir / name).exists():
            shutil.copy2(plugin_dir / name, version_target / name)

    version_repo_url = (
        f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/"
        f"versions/{plugin_id}/{version}/"
    )
    version_repo = {
        "repo": {
            "id": f"repository.{OWNER.lower()}.{plugin_id}.{version}",
            "name": f"{info.get('name', plugin_id)} {version} (pinned)",
            "icon": "",
            "repo_data_directory": version_repo_url,
            "repo_data_url": version_repo_url + "repo.json",
        },
        "plugins": [info],
    }
    version_text = json.dumps(version_repo, indent=4) + "\n"
    (version_target / "repo.json").write_text(version_text)
    (version_target / "repo.json.md5").write_text(
        hashlib.md5(version_text.encode()).hexdigest()
    )

    release_manifest.append({
        "plugin_id": plugin_id,
        "name": info.get("name", plugin_id),
        "version": version,
        "tag": f"{plugin_id}-v{version}",
        "zip": str(zip_path.relative_to(DIST)),
        "changelog": str((plugin_dir / "changelog.md").relative_to(ROOT))
            if (plugin_dir / "changelog.md").exists() else "",
        "pinned_repo": version_repo_url + "repo.json",
    })

repo = {
    "repo": {
        "id": f"repository.{OWNER.lower()}",
        "name": f"{OWNER} Unmanic Custom Plugins",
        "icon": "",
        "repo_data_directory": f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/",
        "repo_data_url": f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/repo.json",
    },
    "plugins": plugins,
}

text = json.dumps(repo, indent=4) + "\n"
(DIST / "repo.json").write_text(text)
(DIST / "repo.json.md5").write_text(hashlib.md5(text.encode()).hexdigest())
(DIST / "release-manifest.json").write_text(json.dumps(release_manifest, indent=2) + "\n")
