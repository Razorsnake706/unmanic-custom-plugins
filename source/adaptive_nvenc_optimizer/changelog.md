# Changelog

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
