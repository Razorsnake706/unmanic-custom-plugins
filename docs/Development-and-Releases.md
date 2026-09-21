# Development and Release Process

## Branches

### main

Contains source and documentation.

~~~text
source/file_size_metrics_plus/
source/adaptive_nvenc_optimizer/
docs/
~~~

### repo

Generated installable Unmanic repository containing repository metadata and packaged ZIP files.

## Build system

build_repo.py discovers source plugins, reads info.json, syntax-checks plugin.py, creates plugin ZIP packages, builds repository indexes and prepares release metadata.

## Publishing

The workflow is:

~~~text
.github/workflows/publish.yml
~~~

Normal development flow:

~~~text
edit source
   |
   v
test/review
   |
   v
update changelog
   |
   v
bump info.json version last
   |
   v
workflow builds release
   |
   v
verify workflow success
   |
   v
verify repo-v2.json version
~~~

Bumping info.json last is intentional because version metadata is the deliberate release trigger.

## Package shape

Unmanic expects plugin files at the ZIP root:

~~~text
info.json
plugin.py
description.md
changelog.md
static/
~~~

Do not wrap them in an extra plugin-name directory.

## Repository indexes

Generated indexes include:

~~~text
repo.json
repo-v2.json
~~~

repo-v2.json is the recommended user-facing URL.

## Versioning

Each plugin has an independent version. A Metrics Plus release does not require an Adaptive Optimizer release, and vice versa.

## Rollback

GitHub Releases preserve installable ZIPs for previous versions.

The generated repo branch also contains version directories, but GitHub Release assets are the most trustworthy manual rollback artifact if a pinned repository layout is ever in doubt.

## Documentation maintenance

When architecture or the adaptive phase changes, update the README and the relevant docs pages. The goal is for source control, not chat history, to be sufficient to resume development later.
