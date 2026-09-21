# Adaptive NVENC Optimizer

Adaptive NVENC Optimizer is a separate companion plugin for **File Size Metrics Plus**.

Its long-term goal is to make Unmanic's GPU video encoding self-tuning: analyze the source, learn from previous P1000/NVENC encodes, sample-test candidate QP values, measure visual quality, estimate storage savings, and automatically choose the most aggressive acceptable GPU encode without requiring per-file manual decisions.

## Current phase

Version 0.1.0 is intentionally **learning / observation only**.

It reads the File Size Metrics Plus SQLite database in read-only mode and:

- identifies successful NVENC training records;
- measures data completeness;
- summarizes observed QP, compression ratio, and encode speed;
- diagnoses common outcomes such as good compression, audio-limited output, already-efficient sources, and files worth future sample testing;
- ranks useful sample-test candidates;
- never changes media files or encoder settings yet.

Future phases will add XPSNR/SSIM calibration, GPU sample encodes, dynamic QP selection, storage-ROI decisions, and eventually automatic worker integration.

File Size Metrics Plus remains the history/telemetry plugin. Adaptive NVENC Optimizer remains the decision-making plugin.
