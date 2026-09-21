# Changelog

## 0.8.0

- Changed Calibration Review from one overall rating per Candidate A/B/C/D to **separate ratings for every candidate in every sample position**.
- Each retained sample now contains its own Reference/Candidate downloads, independent A/B/C/D rating controls, and a per-sample **All candidates in this sample look indistinguishable** shortcut.
- Added draft rating storage in `calibration_sample_ratings`; clicking a rating saves the draft immediately but does **not** start threshold learning or objective scoring.
- Added an explicit **Submit ratings** step. Submission is disabled until every candidate in every sample has a rating, then locks the review and starts targeted objective scoring.
- Added a sticky **Submit ratings** button at the top of the review modal plus a detailed progress box showing how many sample ratings are complete, so the confirmation action is always visible while reviewing.
- On submission, Adaptive derives the current conservative overall rating for each QP from the **worst reviewable sample**. `Unreviewable` samples are ignored unless every sample for that candidate is unreviewable.
- Candidate-to-QP mapping remains hidden until Submit ratings is pressed.
- Existing completed reviews from the old overall-rating workflow remain readable as **legacy reviews** and are not rewritten.
- Per-sample ratings are retained for future content-aware learning even though current boundary selection still uses the conservative aggregate rating.

## 0.7.2

- Added an explicit **Finish review & delete clips** step after subjective review is complete.
- Clicking **All candidates look indistinguishable** now gives immediate visible feedback that the review was saved and that Adaptive is objectively scoring the highest tested QP.
- While targeted XPSNR/SSIM scoring is running, the review explains that temporary clips must remain available and that the Finish action will unlock afterward.
- Once scoring completes, Finish review removes the retained Reference/Candidate clips and cached ZIP while keeping ratings, revealed QP mapping, bitrate data, and objective quality results.
- If objective scoring fails, the saved ratings remain intact and the user can either finish/clean up or keep clips for troubleshooting.
- Renamed the previous low-level **Delete retained files** action to the clearer review-completion workflow.

## 0.7.1

- Fixed a Calibration Review backend crash that occurred after ratings were saved. A stale `excluded_run_ids` reference could make the review list fail to reload, which made other retained reviews appear to disappear and could leave refresh actions looking broken.
- Existing calibration runs/ratings are not deleted by this bug; the fixed review loader reads them normally again.
- Fixed a race where the sample-test job reported `completed` before its retained run had actually been persisted to `adaptive_optimizer.db`.
- Sample tests now report a short **finalizing** stage while the retained run is saved, reference state is updated, and automatic ZIP preparation is started.
- The UI now waits for Calibration Review data to refresh after finalization before presenting the retained-review action as ready.
- This makes **Review retained clips** reliably find a newly completed episode instead of occasionally opening before the review record existed.

## 0.7.0

- Replaced the narrow first-pass calibration ladder with a **coarse boundary-search ladder**. A typical QP 28 source now tests QP 28 / 34 / 40 / 46 instead of 28 / 31 / 34 / 37.
- The wider ladder is designed to make at least one candidate visibly worse on ordinary 1080p material, making subjective calibration easier and reducing guesswork.
- Added **All candidates look indistinguishable** to Calibration Review. This records the result directly instead of forcing the reviewer to invent differences that are not visible.
- When every candidate is marked indistinguishable, Adaptive treats the run as **no visible boundary found yet** and targets the highest tested QP for objective XPSNR/SSIM scoring.
- Added boundary-search strategy metadata to sample plans so future calibration rounds can narrow or extend the QP range intelligently.
- Kept the maximum calibration QP bounded at 51.

## 0.6.1

- Added **Discard as unsuitable source** inside Calibration Review for media that is a poor subjective test source, such as material where the candidates are too visually similar to judge confidently.
- Discarded runs are permanently excluded from subjective threshold/model learning while the historical sample-test record is kept for audit/history.
- Discarding an unsuitable run removes its retained reference/candidate clips and cached ZIP so weak calibration material does not keep consuming storage.
- Added a **Discarded sources** counter to Calibration Review.
- Calibration ZIP creation now starts **automatically as soon as retained candidate generation finishes** instead of waiting for Download ZIP to be clicked.
- Existing retained runs that do not yet have a ZIP automatically start one the next time Calibration Review data is loaded.
- Automatic ZIP preparation is shown in the review modal with live file-count/current-file progress, and retained-run cards show ZIP pending/building/ready state.
- Download ZIP now uses the already-prepared cached archive whenever available.

## 0.6.0

- Moved Calibration Review into a prominent **modal workspace** opened from a new button in the page header, so retained reviews are no longer hidden at the bottom of the dashboard.
- Added per-show **Calibration Review** buttons directly in the Encode Advisor for rows with retained calibration clips.
- The review modal opens immediately and can show the retained-run list or jump directly into a show's blind A/B/C/D judging controls.
- Reworked blind ZIP downloads into a background build job instead of compiling the archive synchronously inside the browser request.
- Added a real ZIP build progress bar showing files completed, total files, and the current archive entry while the server prepares the bundle.
- Completed ZIPs are cached for the retained run so repeat downloads do not have to rebuild the archive.
- Clicking Download ZIP from the retained-run list now opens the review modal first, making bundle-build progress visible instead of appearing to do nothing.
- Existing individual Reference/Candidate clip downloads remain available inside each show's review.

## 0.5.2

- Replaced the Calibration Review modal with an **inline review workspace** to avoid Opera GX/Chromium dialog-transition issues where Open Calibration Review / Review retained clips only closed the sample-test dialog.
- Open review now scrolls directly to the persistent review workspace containing the subjective quality buttons and clip controls.
- Retained-run cards now have separate **Open review** and **Download ZIP** buttons.
- Added a blind **Download all clips (.zip)** bundle containing `Reference.mkv` and Candidate A/B/C/D for every sample position.
- Individual calibration clip downloads now use an explicit browser Blob download path for better Chromium/Opera compatibility.
- Reopening a retained run never requires rerunning the GPU candidates; existing clips remain linked to the Metrics Plus record until reviewed/cleaned up.

## 0.5.1

- Fixed retained calibration runs disappearing from the user's workflow after closing the pre-encode/sample-test dialog. Reopening the same advisor row now detects an existing retained run and offers **Open Calibration Review** instead of making the clips be generated again.
- Reopening a row while its sample generation is still running now reconnects to the active background job and resumes progress polling.
- Prevented accidental duplicate sample generation when a retained calibration run already exists for the same Metrics Plus record.
- Added reliable browser downloads using Blob-based download handling for retained MKV reference/candidate clips.
- Added **Download all clips (.zip)**, which packages the blind Reference + Candidate A/B/C/D files into per-sample folders without revealing the QP mapping.
- Moved the subjective quality controls to the top of Calibration Review under a dedicated **Judge candidate quality** section, with explicit Indistinguishable / Acceptable / Borderline / Unacceptable / Unreviewable buttons.
- Added clearer **Watch the clips** controls and download labels so the review workflow is visible without scrolling past the clips first.
- Fast retained calibration results no longer show the QP table immediately after generation, preserving the blind Candidate A/B/C/D review.

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
