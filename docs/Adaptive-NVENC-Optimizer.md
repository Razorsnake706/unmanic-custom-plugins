# Adaptive NVENC Optimizer

## Goal

Adaptive NVENC Optimizer is intended to replace the idea of one fixed quality setting for every file.

Instead of:

~~~text
every file -> QP 28
~~~

the future system should:

~~~text
analyze source
    |
    v
predict useful QP range
    |
    v
test short representative samples on GPU
    |
    v
measure quality automatically
    |
    v
choose highest-compression acceptable QP
    |
    v
estimate storage savings
    |
    v
encode only if worthwhile
~~~

The full encode remains GPU-first.

## Current phase: Learning + calibration preparation

Current releases are deliberately read-only. The reference system has crossed the initial 10-record baseline threshold, so the optimizer now also builds sample-test plans without executing them.

The optimizer reads successful NVENC records from File Size Metrics Plus and calculates telemetry completeness, storage reduction, observed QP, encode speed, output audio share, video bitrate change and candidate priority.

## Current diagnoses

### Good compression

The total file size and video bitrate both dropped strongly.

### Audio-limited

The video compressed well, but audio is now a large fraction of the output bitrate.

Example:

~~~text
input video:   4.76 Mbps
output video:  1.93 Mbps
output audio:  1.92 Mbps
~~~

The video encoder is not the main reason the final file remains large; copied audio is.

### Already efficient

The source begins with a relatively low video bitrate for its resolution and frame rate. Re-encoding may offer little storage benefit relative to quality loss and GPU time.

### Worth profiling

The result is acceptable but a controlled sample test may show that a higher QP can remain visually acceptable.

### Sample-test candidate

The encode appears to have relatively low compression efficiency and is a useful target for future automated QP tests.

### Needs more data

The row predates newer Metrics Plus fields or otherwise lacks enough diagnostic telemetry.

## Baseline readiness

The first development threshold is at least 10 complete NVENC records. This is only enough to begin calibration work; a larger and more diverse history improves later predictions.

## Objective quality tools

The FFmpeg build used during development exposes PSNR, SSIM and XPSNR, but not libvmaf.

The planned first quality loop therefore uses **XPSNR + SSIM**. VMAF may be added later if the FFmpeg environment gains libvmaf.

## Sample-test planning

Clicking an Encode Advisor row now builds a read-only plan containing:

- whether the current path still appears to contain the original source;
- four representative sample positions across the runtime;
- a bounded QP ladder beginning at the observed QP;
- the number of short GPU variants that would be encoded;
- an estimated NVENC test duration based on measured encode speed;
- the planned objective quality metrics (XPSNR + SSIM).

Historical rows often point to files that Unmanic has already replaced with their HEVC outputs. Those rows are useful for learning compression behavior but are **not safe sources for perceptual calibration**, because the original reference frames no longer exist. Testing confirmed both states in practice: some no-op/failed video jobs still leave the original H.264 source available, while successful H.264→HEVC jobs generally leave only the HEVC replacement. This source-availability check is why sample execution is not enabled yet.

## Adjustable advisor columns

Advisor column widths can be dragged directly from the header. Widths are stored in browser local storage and can be restored with **Reset column widths**.

## Automatic decisions are not enabled yet

Learning mode does not re-encode files, change QP, change the video-transcoder plugin, delete media or modify Metrics Plus history.

## No-op video tasks

A successful Unmanic task is not automatically a successful video transcode. Rows that finish with the source codec unchanged (for example H.264 → H.264 with zero or tiny size change) are now labeled **No video encode** and excluded from the adaptive training baseline. They may still be useful as calibration sources when the original file remains present.
