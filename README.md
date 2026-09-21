# Razorsnake706 Unmanic Custom Plugins

A custom Unmanic plugin repository focused on **media-size analytics, NVENC telemetry, and eventually fully automated GPU quality tuning**.

The project currently contains two separate but cooperating plugins:

| Plugin | Purpose | Current role |
| --- | --- | --- |
| **File Size Metrics Plus** | Records detailed before/after processing telemetry and provides a searchable history dashboard. | Data collection, history, diagnostics, export |
| **Adaptive NVENC Optimizer** | Reads Metrics Plus history and learns how well NVENC performs on different media. | Read-only learning/analysis; automatic tuning is under development |

The long-term goal is to let Unmanic automatically decide **whether a file is worth encoding and how aggressively the GPU should encode it**, without requiring a fixed quality setting for every show or movie.

## Install this repository in Unmanic

Add this URL under **Unmanic → Plugins → Plugin Repositories**:

```text
https://raw.githubusercontent.com/Razorsnake706/unmanic-custom-plugins/repo/repo-v2.json
```

Then refresh plugin repositories and install the plugins you want.

> **Why `repo-v2.json`?** During development, Unmanic's remote custom-repository proxy was observed serving stale metadata. The v2 repository URL gives this project a stable cache-busted repository identity, and the plugins also contain a direct GitHub repository-refresh fallback.

## How the two plugins work together

```text
Unmanic processing job
        │
        ▼
File Size Metrics Plus
  • source/output FFprobe data
  • real FFmpeg command
  • NVENC QP / preset / AQ / lookahead
  • size and bitrate changes
  • worker/library/timing
        │
        ▼
metrics_plus.db
        │  read-only
        ▼
Adaptive NVENC Optimizer
  • baseline learning
  • compression diagnosis
  • candidate ranking
  • future XPSNR/SSIM sample tests
  • future dynamic QP selection
        │
        ▼
Future automated GPU encode decision
```

**Metrics Plus is the memory. Adaptive NVENC Optimizer is the decision-maker.** They intentionally remain separate plugins.

## Current project status

Adaptive NVENC Optimizer is currently in **Phase 1: Learning Mode**. It does not modify media files or encoder settings. It reads successful NVENC records from Metrics Plus and classifies results such as:

- **Good compression** — video and total size fell strongly.
- **Audio-limited** — video compressed well, but copied audio now dominates the output size.
- **Already efficient** — source bitrate is already low for its resolution/frame rate.
- **Worth profiling** — likely useful for future sample tests.
- **Needs more data** — the encode predates newer telemetry fields.

The planned next phases add automated representative clip selection, GPU sample encodes at multiple QP values, XPSNR/SSIM quality scoring, calibration against a chosen visual-quality threshold, storage-ROI checks, and eventually automatic per-file NVENC settings.

## Documentation / project wiki

The project documentation is stored in the repository so it is versioned and backed up with the source:

- [Wiki Home](docs/Home.md)
- [Architecture](docs/Architecture.md)
- [Installation and Setup](docs/Installation.md)
- [File Size Metrics Plus](docs/File-Size-Metrics-Plus.md)
- [Adaptive NVENC Optimizer](docs/Adaptive-NVENC-Optimizer.md)
- [Adaptive Encoding Roadmap](docs/Adaptive-Roadmap.md)
- [Troubleshooting and Recovery](docs/Troubleshooting-and-Recovery.md)
- [Development and Release Process](docs/Development-and-Releases.md)

## Source, packages, and releases

The `main` branch contains plugin source. GitHub Actions packages releases and publishes the installable Unmanic repository to the `repo` branch.

Every plugin version is also published as a GitHub Release with its installable ZIP.

The repository layout is broadly:

```text
main
├── source/
│   ├── file_size_metrics_plus/
│   └── adaptive_nvenc_optimizer/
├── docs/
├── build_repo.py
└── .github/workflows/publish.yml

repo
├── repo.json
├── repo-v2.json
├── file_size_metrics_plus/
├── adaptive_nvenc_optimizer/
└── versions/
```

## Updates

Both plugins include an **Update plugin** button in their data panels. The updater:

1. refreshes this custom repository directly from GitHub;
2. asks the plugin backend for its exact installed Unmanic database row;
3. calls Unmanic's normal installed-plugin update route;
4. verifies the installed version after the update.

The normal Unmanic Plugins page remains the recovery path if an older plugin version contains a broken self-updater.

## Safety philosophy

Adaptive tuning is being introduced in stages. The optimizer stays **read-only** until enough telemetry exists and the quality-measurement workflow is validated. Automatic tuning will also use hard safety bounds rather than giving the predictor unrestricted control over encoder settings.

See the [Adaptive Encoding Roadmap](docs/Adaptive-Roadmap.md) for the planned progression.
