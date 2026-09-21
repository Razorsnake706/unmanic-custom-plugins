# Architecture

## Components

### File Size Metrics Plus

Metrics Plus is the telemetry and history layer.

It hooks into Unmanic task lifecycle events, probes source/output media with FFprobe, captures the actual FFmpeg command used by the worker, and stores results in its own SQLite database.

Important recorded data for newer jobs includes:

- source and destination file size;
- source/output video codec, profile, resolution, pixel format and bit depth;
- media duration and frame rate;
- effective total bitrate;
- video and audio bitrate where available or estimable;
- audio/subtitle stream counts;
- HDR/color metadata;
- worker and library;
- processing duration;
- actual FFmpeg command;
- NVENC encoder, rate control, QP/CQ, preset, tune, profile, lookahead, AQ settings and hardware decode mode.

Older/imported records remain valid but may have blank values for fields that did not exist when they were collected.

### Adaptive NVENC Optimizer

The optimizer is a separate plugin and opens the Metrics Plus SQLite database in **read-only mode**.

It does not own or copy the Metrics Plus history.

Current responsibilities:

- locate successful NVENC records;
- measure telemetry completeness;
- calculate derived compression metrics;
- classify completed jobs;
- rank useful future sample-test candidates;
- track whether enough baseline data exists.

Future responsibilities include representative scene selection, short GPU test encodes, objective image-quality comparison, QP search, storage-ROI decisions and automatic integration into the Unmanic worker pipeline.

## Data flow

~~~text
Source file
   |
   v
Unmanic task scheduled
   |
   +-- Metrics Plus probes source
   |
   v
Unmanic worker
   |
   +-- video/audio processing
   +-- FFmpeg command executes
   +-- Metrics Plus captures worker command metadata
   |
   v
Post-processing complete
   |
   +-- Metrics Plus probes output
   +-- calculates before/after savings
   +-- writes metrics_plus.db
            |
            v
Adaptive NVENC Optimizer
   +-- reads database
   +-- derives diagnostics
   +-- later learns encoding decisions
~~~

## Database location

Metrics Plus uses Unmanic's plugin userdata directory:

~~~text
<Unmanic userdata>/file_size_metrics_plus/metrics_plus.db
~~~

Inside a container this is beneath Unmanic's mapped configuration/home directory. The exact host path depends on the Docker mapping.

The optimizer resolves the path through Unmanic's own configuration API rather than hard-coding /config.

## Why bitrate needs sanity checking

Matroska files can contain per-stream BPS metadata. After a stream is re-encoded, stale metadata may sometimes survive in tags even though it no longer represents the actual stream bitrate.

Both plugins therefore treat impossible values as stale. For example, an output video stream cannot realistically report 9 Mbps when the entire output file averages only 3 Mbps.

When this happens, the collector/advisor falls back to a residual estimate:

~~~text
estimated video bitrate ~= total bitrate - known audio bitrate
~~~

This is one reason the system stores both raw probe data and derived values.

## Plugin independence

Metrics Plus should never require Adaptive NVENC Optimizer.

Adaptive NVENC Optimizer **does** require Metrics Plus history for its learning functions. If Metrics Plus is absent, the optimizer displays a missing-database message rather than creating its own duplicate history.
