# Razorsnake706 Unmanic Custom Plugins

Custom Unmanic plugins used on Coruscant.

## Add this repository to Unmanic

Paste this URL into **Unmanic → Plugins → Plugin Repositories**:

```text
https://raw.githubusercontent.com/Razorsnake706/unmanic-custom-plugins/repo/repo.json
```

The `main` branch contains plugin source. GitHub Actions packages every release and publishes the installable Unmanic repository to the `repo` branch.

## Releases and rollback

Every plugin version is also published as a GitHub Release with its installable ZIP. The `repo` branch keeps version-pinned repository indexes under:

```text
versions/<plugin_id>/<version>/repo.json
```

For example, File Size Metrics Plus 0.1.1 can be pinned with:

```text
https://raw.githubusercontent.com/Razorsnake706/unmanic-custom-plugins/repo/versions/file_size_metrics_plus/0.1.1/repo.json
```

This lets an older version remain available even after the main repository moves forward.

## Plugins

### File Size Metrics Plus

Filterable completion analytics with before/after size, source/output codec, library, worker, date, success/failure, percent saved, detailed task inspection, CSV export, visual size comparisons, customizable columns, optional grouping of repeated video/audio processing passes, per-media processing history, and import of the official File Size Metrics history database.
