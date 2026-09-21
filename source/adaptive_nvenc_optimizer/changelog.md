# Changelog

## 0.5.0

- Added **fast calibration mode** for retained human-review runs: generate the NVENC candidate clips first and defer expensive CPU quality scoring until after blind review.
- XPSNR and SSIM are now calculated together in a single FFmpeg comparison pass instead of decoding each candidate twice.
- After all blind ratings are submitted, objective scoring is limited to the useful subjective boundary: the highest accepted candidate, the first unacceptable candidate, plus any explicitly borderline candidates.
- Added background targeted quality scoring with live progress in Calibration Review, so the review UI remains usable while CPU metrics run.
- Added a direct **Review retained clips** button after candidate generation completes.
- Made the per-sample **Download Reference** and **Download Candidate A/B/C/D** controls explicit. Downloaded MKVs can be watched locally in VLC or another HEVC-capable player.
- Candidate QP mappings remain hidden until all candidates are rated; objective scores may continue calculating afterward without blocking the human review.
- Retained calibration files cannot be deleted while targeted objective scoring is still running.
- Non-retained technical tests still calculate objective metrics immediately, but use the new combined XPSNR+SSIM pass.

## 0.4.0

- Added a **Calibration Review** section to the Adaptive data panel.
- Retained calibration runs are reviewed blind as Candidate A/B/C/D so QP values and objective scores do not bias the subjective rating.
- Added downloadable reference and candidate MKV clips for every retained sample position.
- Added subjective ratings: Indistinguishable, Acceptable, Borderline, Unacceptable, and Unreviewable.
- Candidate-to-QP mappings and XPSNR/SSIM/bitrate results are revealed only after every candidate in the run has been rated.
- Added persistent subjective rating storage in `adaptive_optimizer.db` and early observed accepted/rejected quality ranges for future threshold learning.
- Added a cleanup button that deletes retained video files after review while preserving objective results and subjective ratings.
- Updated the sample-retention setting text to clarify that it should be enabled during human calibration.

## 0.3.0

- Added a real Unmanic `on_worker_process` runner so Adaptive NVENC Optimizer can be enabled in GPU video libraries.
- Added automatic **pre-encode reference capture**. When Adaptive runs before Transcode Video Files, it saves short video-only stream-copy clips from the untouched source before the full HEVC encode replaces it.
- Added persistent reference-capture tracking linked to Metrics Plus by task ID/source path.
- Manual GPU calibration can now use captured reference clips even after the full original file has been replaced by HEVC.
- Added reference-capture badges/counts to the Adaptive dashboard and sample-plan dialog.
- Added `Capture pre-encode reference clips` (default ON), reference retention (default 72 hours), and a soft reference-cache cap (default 10 GB).
- `Keep calibration/test sample files` can remain OFF. Successful calibration consumes/deletes temporary reference and QP-test clips after objective results are saved; enabling it retains them for visual review.
- Reference capture failures never fail the normal Unmanic media task; the regular video encode continues.
- Added automatic cleanup for expired/old reference captures.
- GitHub releases now show only the changelog section for that specific version instead of the entire project changelog.

## 0.2.1

- Fixed the Adaptive dashboard appearing stale after new encodes completed.
- The advisor had been sorted by test priority, so older high-priority rows stayed at the top even after fresh Metrics Plus records arrived. The default is now **Newest first**.
- Added an **Advisor order** selector so you can switch between **Newest first** and **Best test candidates** without losing the ranking view.
- Added a Metrics Plus feed status banner showing the newest NVENC record timestamp and total NVENC record count.
- The **Refresh data** button now visibly enters a Refreshing state, bypasses browser caching, updates the feed timestamp, and reports the newest record it read.
- Exposed Metrics Plus database/WAL modification timestamps in the backend for refresh diagnostics.
- Manual sample testing remains unchanged.

## 0.2.0

- Added the first real **manual GPU sample-test** workflow.
- For a row whose original source is still safely available, the optimizer can now run the planned short HEVC/NVENC variants at the QP ladder shown in the dialog.
- Sample tests run in a background thread so the panel request stays responsive.
- Added objective quality measurement using the FFmpeg build's **XPSNR + SSIM** filters.
- Added per-QP result summaries showing average XPSNR, SSIM, sample video bitrate, relative bitrate, GPU encode time, and completed quality samples.
- Added persistent sample-test history in `adaptive_optimizer.db` for future calibration/model training.
- Added plugin settings for sample count, short-form sample duration, long-form sample duration, and **Keep calibration/test sample files**.
- Sample retention defaults to OFF. When disabled, temporary encoded clips are deleted automatically after their scores are recorded. When enabled, clips plus a `result.json` are kept under the plugin userdata sample directory.
- The manual test never replaces or modifies the real media file.
- Only one manual sample test runs at a time to avoid stacking multiple calibration jobs on the GPU.
- Hardware decoding is attempted when the recorded encode used CUDA; if that sample decode fails, the test retries with CPU decode while keeping NVENC for the actual sample encode.
- Full automatic per-file QP selection is still disabled; this release is for validating the calibration pipeline first.

## 0.1.3

- Reworked the in-panel updater so the plugin no longer replaces/reloads itself inside the same Tornado API request.
- Self-updates are now scheduled in a short-delay background thread after the panel request has returned; the UI polls the installed version until the update is complete.
- Added update-status endpoints and retained direct GitHub repository refresh before scheduling an update.
- Added a **No video encode** diagnosis and excluded tasks that did not actually produce HEVC video from the adaptive training baseline.
- This prevents successful/no-op H.264→H.264 tasks from being treated as valid NVENC compression training records.
- Sample planning and resizable columns remain unchanged.

## 0.1.2

- Added draggable, persistent advisor column widths with a **Reset column widths** control.
- Clicking an Encode Advisor row now builds a read-only sample-test plan.
- Sample planning checks whether the original source still appears to exist at the recorded path before allowing future quality comparisons.
- Added representative sample positions across the media runtime and a bounded QP ladder based on the observed encode QP.
- Added an estimated NVENC sample-test duration using the file's measured encode speed.
- Added XPSNR + SSIM as the planned first objective quality metrics.
- This release still does not run sample encodes or alter media/encoder settings; it establishes the calibration workflow safely first.

## 0.1.1

- Fixed the plugin self-update lookup by querying Unmanic's installed-plugin database directly from the plugin backend.
- Expanded the advisor table and gave filenames a dedicated wide column with full wrapping, preventing long release names from spilling into the Diagnosis column.
- Added fixed column widths and horizontal scrolling for the advisor so filenames and explanations remain readable on narrower screens.
- Added bitrate sanity checks in the advisor so stale/inherited Matroska `BPS` metadata cannot falsely report no video bitrate reduction after a successful encode.
- Learning mode remains read-only; no media files or encoder settings are changed.

## 0.1.0

- Initial learning-mode release.
- Added a separate dashboard backed by File Size Metrics Plus history.
- Added NVENC baseline readiness tracking and training-record counts.
- Added average storage reduction, median observed QP, and average encode-speed analytics.
- Added first-pass diagnoses: Good compression, Audio-limited, Already efficient, Sample-test candidate, Worth profiling, and Needs more data.
- Added candidate ranking for future adaptive sample testing.
- Reads the Metrics Plus database read-only and does not modify media or encoder settings.
- Added direct repository refresh and an **Update plugin** button using Unmanic's normal installed-plugin update route.
