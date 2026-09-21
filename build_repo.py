#!/usr/bin/env python3
import hashlib, json, pathlib, shutil, zipfile

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
for plugin_dir in sorted(p for p in SRC.iterdir() if p.is_dir()):
    info = json.loads((plugin_dir / "info.json").read_text())
    plugin_id = info["id"]
    version = info["version"]
    target = DIST / plugin_id
    target.mkdir()
    for name in ("info.json", "description.md", "changelog.md"):
        if (plugin_dir / name).exists():
            shutil.copy2(plugin_dir / name, target / name)
    zip_path = target / f"{plugin_id}-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(plugin_dir.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            z.write(path, path.relative_to(plugin_dir))
    plugins.append(info)

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
