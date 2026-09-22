# Razorsnake706 Unmanic Custom Plugins

A custom Unmanic plugin repository focused on **media-size analytics, NVENC quality calibration, and controlled one-off processing**.

The project currently contains three plugins:

| Plugin | Purpose | Current role |
| --- | --- | --- |
| **File Size Metrics Plus** | Records detailed before/after processing telemetry and provides a searchable history dashboard. | Data collection, history, diagnostics, export |
| **Adaptive NVENC Optimizer** | Captures pre-encode references, reads Metrics Plus history, and measures NVENC quality/efficiency. | Reference capture + calibration/review workflow; bounded automatic tuning is still under development |
| **Manual One-Off Queue** | Lets you browse to one movie/episode and choose the exact processing plugins for that task. | One-off testing, calibration runs, troubleshooting, and manual plugin-chain execution |

The long-term goal is to let Unmanic automatically decide **whether a file is worth encoding and how aggressively the GPU should encode it**, without requiring a fixed quality setting for every show or movie.

## Install this repository in Unmanic

Add this URL under **Unmanic → Plugins → Plugin Repositories**:

```text
https://raw.githubusercontent.com/Razorsnake706/unmanic-custom-plugins/repo/repo-v2.json
```

Then refresh plugin repositories and install the plugins you want.

> **Why `repo-v2.json`?** During development, Unmanic's remote custom-repository proxy was observed serving stale metadata. The v2 repository URL gives this project a stable cache-busted repository identity, and the plugins also contain a direct GitHub repository-refresh fallback.

## How the plugins work together

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
  • pre-encode reference capture
  • manual XPSNR/SSIM sample tests
  • future dynamic QP selection
        │
        ▼
Future automated GPU encode decision
```

**Metrics Plus is the memory. Adaptive NVENC Optimizer is the quality/calibration layer. Manual One-Off Queue is the controlled execution tool.** They intentionally remain separate plugins.

## Current project status

Adaptive NVENC Optimizer is currently in the **pre-encode reference capture + manual calibration** phase.

When enabled in a GPU video library **before Transcode Video Files**, Adaptive stream-copies a few short video-only sections from the untouched source. The normal Unmanic HEVC/NVENC encode then continues exactly as before. Those small reference clips survive long enough for the optimizer to run manual QP tests and calculate XPSNR/SSIM even though the full original file has already been replaced.

The optimizer still does **not** automatically choose or change the full-file QP. The next major milestone is converting the saved calibration results into a trustworthy quality threshold and then using that threshold to make bounded per-file QP decisions.

For normal operation, **Keep calibration/test sample files can stay OFF**. Temporary reference/test clips are cleaned up after successful calibration or when retention/cache limits are reached, while numerical calibration results remain in the optimizer database.

## Documentation / project wiki

The project documentation is stored in the repository so it is versioned and backed up with the source:

- [Wiki Home](docs/Home.md)
- [Architecture](docs/Architecture.md)
- [Installation and Setup](docs/Installation.md)
- [File Size Metrics Plus](docs/File-Size-Metrics-Plus.md)
- [Adaptive NVENC Optimizer](docs/Adaptive-NVENC-Optimizer.md)
- [Manual One-Off Queue](docs/Manual-One-Off-Queue.md)
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
│   ├── adaptive_nvenc_optimizer/
│   └── manual_oneoff_queue/
├── docs/
├── build_repo.py
└── .github/workflows/publish.yml

repo
├── repo.json
├── repo-v2.json
├── file_size_metrics_plus/
├── adaptive_nvenc_optimizer/
├── manual_oneoff_queue/
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


## Manual one-off processing

Manual One-Off Queue is designed for tasks where you do **not** want to change a whole library's plugin configuration. Create a dedicated scanner-disabled manual library, browse a normal source/settings library, select one media file, choose the plugins for that task, then queue it.

Version 0.2.0 adds drag-and-drop plugin ordering, dark-theme dropdown fixes, and persistence for the selected libraries, browse path, plugin order, and checked plugins.

See [Manual One-Off Queue](docs/Manual-One-Off-Queue.md) for the recommended safe setup.
