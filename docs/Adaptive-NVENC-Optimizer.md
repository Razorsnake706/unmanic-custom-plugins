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

## Current phase: Learning Mode

Current releases are deliberately read-only.

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

## Automatic decisions are not enabled yet

Learning mode does not re-encode files, change QP, change the video-transcoder plugin, delete media or modify Metrics Plus history.
