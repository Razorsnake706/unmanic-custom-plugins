# Changelog

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
