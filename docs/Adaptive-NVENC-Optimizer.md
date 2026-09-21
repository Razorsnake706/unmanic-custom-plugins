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

## Browser-compatible review workspace

Calibration Review is rendered inline on the Adaptive page rather than as a second modal dialog. This avoids Chromium/Opera GX behavior where transitioning directly from the sample-test dialog to another modal could leave the review invisible.

Each retained run has two explicit actions: **Open review** and **Download ZIP**. Open review scrolls to the judging workspace with Candidate A/B/C/D rating buttons. Download ZIP downloads the complete blind clip set in one archive. Individual Reference/Candidate download buttons remain available inside the workspace.

## Calibration Review modal and ZIP progress

Calibration Review is now opened from a dedicated button in the Adaptive page header. Advisor rows with retained calibration clips also display their own **Calibration Review** button, allowing a review to open directly for that show.

The review uses a browser-safe custom modal overlay rather than relying on chained HTML `<dialog>` transitions. The modal contains the retained-run list, blind Candidate A/B/C/D quality controls, individual clip downloads, revealed results after rating, and retained-file cleanup.

Blind ZIP bundles are built as background jobs. While the bundle is assembled, the modal shows a progress bar with the number of files already added and the current archive entry. Once ready, the browser download begins automatically. The completed ZIP is cached for that retained run until its calibration files are cleaned up.

## Unsuitable calibration sources

If a source does not provide a confident subjective comparison, use **Discard as unsuitable source** in Calibration Review instead of guessing Candidate A/B/C/D ratings. A discarded run is excluded from learned subjective quality thresholds and future model training. Its sample-test history is retained so the system knows the run was intentionally rejected, while retained video clips and the cached ZIP are removed.

Examples include material where the source itself makes compression differences unusually hard to judge, or where the reviewer would effectively be guessing rather than making a confident visual assessment.

## Automatic calibration ZIP preparation

For retained human-calibration runs, the blind ZIP now starts building automatically as soon as GPU candidate generation finishes. Calibration Review shows the archive state as pending, building, or ready, including a live file-count progress bar while it is being assembled. Older retained runs without a ZIP also start archive preparation when Calibration Review data is loaded. Clicking **Download ZIP** uses the prepared archive when it is ready rather than starting the build from scratch.

## Coarse-to-fine quality boundary search

The first subjective calibration round now uses a deliberately wider QP spread. For the normal QP 28 baseline, the initial ladder is **28 / 34 / 40 / 46** instead of 28 / 31 / 34 / 37. The goal is not to rank four almost-identical encodes; it is to find the approximate point where visible degradation first appears.

If all blind candidates genuinely look indistinguishable from the reference, use **All candidates look indistinguishable** rather than guessing. Adaptive records every candidate as indistinguishable and treats that run as evidence that the visible quality boundary lies above the highest tested QP for that source. Objective scoring then targets the highest tested candidate so the subjective observation is still paired with a measured result.

Future rounds can use the stored boundary-search metadata to narrow between the highest acceptable and first unacceptable QPs, or extend upward toward QP 51 when no visible boundary is found.

## Review persistence and finalization

Sample generation now has an explicit **finalizing** stage. The job is not reported as complete until its retained calibration run has been written to `adaptive_optimizer.db`, reference retention has been updated, and automatic ZIP preparation has been started. This prevents the Review retained clips action from racing ahead of the saved review record.

Calibration Review reloads preserve all existing retained runs and ratings. A previously fixed loader regression could fail after ratings were present; it did not delete the underlying review data.

## Finishing a calibration review

After all blind candidates are rated, Adaptive may still need the retained Reference/Candidate clips for targeted XPSNR/SSIM scoring. During that period the review shows that the ratings are saved and keeps the cleanup action locked.

When objective scoring finishes, use **Finish review & delete clips**. This removes the temporary retained reference clips, candidate clips, and cached ZIP while preserving the subjective ratings, revealed Candidate-to-QP mapping, bitrate measurements, and objective quality results in the optimizer history.

For **All candidates look indistinguishable**, the review immediately records all blind candidates as indistinguishable and targets the highest tested QP for objective scoring. The Finish action becomes available once that scoring pass completes.

## Per-sample subjective review

Calibration Review now rates every sample position independently rather than asking for one overall Candidate A/B/C/D judgment across the entire episode. Each sample has its own Reference download, Candidate A/B/C/D downloads, rating controls, and **All candidates in this sample look indistinguishable** shortcut.

Ratings are saved as drafts immediately. They do not affect learned thresholds and do not start objective scoring until the user presses **Submit ratings**. The review shows a live `rated / required` counter and keeps a sticky Submit ratings control visible at the top of the modal. Submission is enabled only when every candidate in every sample has a rating.

After submission, the per-sample ratings are locked. For the current boundary-selection algorithm, Adaptive derives one conservative candidate rating using the worst reviewable sample across the episode: `indistinguishable < acceptable < borderline < unacceptable`. A sample marked `unreviewable` is excluded from that aggregation unless every sample for the candidate is unreviewable. The original per-sample ratings remain stored separately for future content-aware learning.

The blind Candidate-to-QP mapping is revealed only after submission. Targeted XPSNR/SSIM scoring then runs as before, followed by **Finish review & delete clips** once objective scoring is complete.
