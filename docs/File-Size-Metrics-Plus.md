# File Size Metrics Plus

## Purpose

File Size Metrics Plus is an enhanced Unmanic data panel for answering:

- How much space did Unmanic actually save?
- Which files compressed well or poorly?
- Which worker/library produced the result?
- What codecs and settings were involved?
- Did the same media file later receive another processing pass?
- What exact FFmpeg command produced a result?

It also acts as the telemetry source for Adaptive NVENC Optimizer.

## Main dashboard

The top summary shows aggregate task count, before size, after size, saved space, reduction percentage and processing time.

When rows are selected, the summary temporarily switches to the **selected entries**. Clearing the selection restores the normal filtered summary.

## Filters

Filters apply automatically. Dropdown/date filters update immediately. Text and numeric filters use a short debounce while typing.

## Selection tools

Metrics Plus supports individual selection, current-page select all, Select all matching, Quick select and bulk history deletion.

Quick select can target legacy rows, success/failure, size-change category, library, worker, input codec and output codec.

Bulk delete removes **Metrics Plus history only**. It does not delete media files.

## Per-file details

Clicking a row opens detailed metadata for the selected processing pass.

The panel also traverses related source/destination paths and shows the processing history for the same media file. This makes separate video and audio passes visible without combining them into one main-table row.

## Diagnostic telemetry

Newer jobs collect data used by the adaptive project:

~~~text
source/output bitrate
video/audio bitrate
FPS
bit depth
HDR/color metadata
container
stream counts
actual encoder command
NVENC QP/CQ
preset/tune/profile
lookahead
spatial/temporal AQ
AQ strength
hardware decode mode
~~~

Metrics Plus also keeps the full source/output FFprobe JSON for future diagnostics.

## Legacy history

Imported official File Size Metrics rows often lack encoder, bitrate, worker, library or audio details. These rows remain useful for historical space-savings totals but should not be treated as complete adaptive-training samples.

## Update button

The panel includes **Update plugin**.

The updater refreshes the custom repo directly, asks its backend for the exact installed Unmanic database row, calls Unmanic's normal installed-plugin update endpoint, verifies the installed version and reloads the panel.

If a very old version contains a broken updater, update once from the normal Unmanic Plugins page and then resume using the in-panel updater.
