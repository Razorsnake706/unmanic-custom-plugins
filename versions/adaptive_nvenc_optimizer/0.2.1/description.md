# Adaptive NVENC Optimizer

Adaptive NVENC Optimizer is a separate companion plugin for **File Size Metrics Plus**.

Its long-term goal is to make Unmanic's GPU video encoding self-tuning: analyze the source, learn from previous P1000/NVENC encodes, sample-test candidate QP values, measure visual quality, estimate storage savings, and automatically choose the most aggressive acceptable GPU encode without requiring per-file manual decisions.

## Current phase

Current releases have moved beyond observation into **manual calibration testing**. Full automatic encoding is still disabled.

It reads the File Size Metrics Plus SQLite database in read-only mode and:

- identifies successful NVENC training records;
- measures data completeness;
- summarizes observed QP, compression ratio, and encode speed;
- diagnoses common outcomes such as good compression, audio-limited output, already-efficient sources, and files worth future sample testing;
- ranks useful sample-test candidates;
- can manually run short HEVC/NVENC QP test ladders when the original source is still safely available;
- measures the samples with XPSNR + SSIM;
- stores calibration results for later model training;
- never replaces the real media file or changes the normal Unmanic encoder settings in this phase.

Future phases will add XPSNR/SSIM calibration, GPU sample encodes, dynamic QP selection, storage-ROI decisions, and eventually automatic worker integration.

File Size Metrics Plus remains the history/telemetry plugin. Adaptive NVENC Optimizer remains the decision-making plugin.
