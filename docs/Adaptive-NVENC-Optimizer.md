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

## Current phase: Pre-encode reference capture + manual calibration

Adaptive NVENC Optimizer now has a Worker Processing runner. When it is enabled in a GPU video library **before Transcode Video Files**, it captures small video-only reference clips from the untouched source and then lets the normal Unmanic pipeline continue. Manual calibration can later use those clips even though the full original has already been replaced.

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

Historical rows often point to files that Unmanic has already replaced with their HEVC outputs. Those rows are useful for learning compression behavior but are **not safe sources for perceptual calibration**, because the original reference frames no longer exist. Manual sample execution is therefore enabled only when the current file still matches the recorded original source closely enough in codec and size.

## Adjustable advisor columns

Advisor column widths can be dragged directly from the header. Widths are stored in browser local storage and can be restored with **Reset column widths**.

## Automatic decisions are not enabled yet

Learning mode does not re-encode files, change QP, change the video-transcoder plugin, delete media or modify Metrics Plus history.

## No-op video tasks

A successful Unmanic task is not automatically a successful video transcode. Rows that finish with the source codec unchanged (for example H.264 → H.264 with zero or tiny size change) are now labeled **No video encode** and excluded from the adaptive training baseline. They may still be useful as calibration sources when the original file remains present.

## Manual sample tests

When **Run sample test** is pressed on a safe source, the optimizer runs the displayed QP ladder across the representative sample positions using HEVC/NVENC. The real episode/movie is never replaced.

Each encoded sample is compared back to the original source segment with XPSNR and SSIM. The optimizer stores the resulting per-QP summaries in its own `adaptive_optimizer.db` for later calibration/model training.

The plugin settings now include:

- Keep calibration/test sample files (default OFF)
- Representative samples per file (default 4)
- TV/short-form sample duration (default 30 seconds)
- Movie/long-form sample duration (default 45 seconds)

With sample retention disabled, temporary clips are removed after their objective scores are saved. With retention enabled, the clips and a `result.json` remain in the plugin userdata sample directory for manual inspection.

Only one sample-test job is allowed at a time. For the cleanest timing measurements, avoid deliberately starting one while the normal Unmanic video worker is already saturating the same GPU.

## Pre-encode reference capture

Enable Adaptive NVENC Optimizer in the same GPU video libraries as the normal video transcoder and place it **before Transcode Video Files** in the Worker Processing flow.

The capture step does not transcode the episode. It stream-copies short video-only sections from the original into the plugin userdata area, so the reference keeps the exact source-compressed frames without creating another lossy generation. Audio/subtitles are not copied because objective video calibration does not need them.

Default capture settings:

- Capture pre-encode reference clips: ON
- Reference clips per file: 4
- TV/short-form duration: 30 seconds
- Movie/long-form duration: 45 seconds
- Untested reference retention: 72 hours
- Reference cache soft cap: 10 GB
- Keep calibration/test sample files: OFF

If reference capture fails for any reason, Adaptive logs the problem and returns control to Unmanic. The normal video task is never intentionally failed just because calibration data could not be captured.

After a successful manual calibration with retention OFF, both the temporary QP test clips and the consumed pre-encode reference clips are removed. The XPSNR/SSIM result remains stored in `adaptive_optimizer.db`.

## Calibration Review

When `Keep calibration/test sample files` is ON, a successful manual sample test appears in the **Calibration Review** section of the Adaptive data panel.

The review is intentionally blind. QP values and objective XPSNR/SSIM scores are hidden behind Candidate A/B/C/D until every candidate has been rated. This reduces the chance that seeing a higher QP or lower metric score biases the visual judgment.

For each retained sample position the panel provides downloads for the source **Reference** clip and every candidate clip. Review a candidate across all retained positions, then assign one overall rating:

- Indistinguishable
- Acceptable
- Borderline
- Unacceptable
- Unreviewable

After all candidates are rated, the panel reveals the real QP, XPSNR, SSIM and bitrate for each candidate. Those subjective ratings are stored alongside the objective sample-test results in `adaptive_optimizer.db`.

After review, **Delete retained files** removes the reference/candidate video files while keeping the numerical results and ratings. This prevents calibration media from accumulating indefinitely.

The panel also shows observed quality ranges from reviewed candidates. These are diagnostic ranges only; automatic QP selection will not use a learned threshold until enough diverse reviewed runs exist.

## Fast calibration mode

When `Keep calibration/test sample files` is ON, candidate generation now prioritizes getting the clips ready for human review quickly. The P1000 generates the QP candidates first and **does not** run XPSNR/SSIM across all 16 variants before the review starts.

Open **Calibration Review** (or click **Review retained clips** immediately after generation). Each sample position has explicit **Download Reference** and **Download Candidate A/B/C/D** buttons. The files download to the browser's normal download location and should be viewed in VLC or another player with reliable HEVC/MKV support.

After every blind candidate has an overall rating, Adaptive reveals the Candidate-to-QP mapping and schedules objective quality scoring in the background. To reduce CPU work, it measures only the useful subjective boundary: the highest Indistinguishable/Acceptable QP, the first Unacceptable QP, and any Borderline QPs. XPSNR and SSIM are calculated together in one FFmpeg comparison pass.

This changes the calibration sequence to:

~~~text
GPU candidate generation
        |
        v
clips ready for blind review
        |
        v
human A/B/C/D ratings
        |
        v
targeted boundary XPSNR + SSIM
        |
        v
saved subjective/objective calibration data
~~~

The objective-scoring stage remains CPU-heavy, but it now runs after the clips are available and usually evaluates far fewer candidate variants than the original all-QP/all-metric implementation.

## Persistent Calibration Review and clip downloads

Retained calibration clips are tied to the Metrics Plus record that produced them. Closing the sample-test dialog or navigating away from the Adaptive page does **not** require regenerating those clips. Reopening the same advisor row shows **Open Calibration Review** when a retained run already exists. If candidate generation is still running, reopening the row reconnects to the active job and resumes progress display.

Calibration Review now starts with the subjective rating controls, followed by the clip downloads. Each sample position has **Download Reference** and **Download Candidate A/B/C/D** buttons, and the review also has **Download all clips (.zip)**. The ZIP keeps the review blind and uses folders such as `Sample 01/Reference.mkv` and `Sample 01/Candidate A.mkv`; it does not include the Candidate-to-QP mapping.

The rating buttons are:

- Indistinguishable
- Acceptable
- Borderline
- Unacceptable
- Unreviewable

Rate each candidate once after comparing it against the reference across all sample positions. The real QP mapping remains hidden until all candidates have ratings.
