# Changelog

## 0.1.0

- Initial learning-mode release.
- Added a separate dashboard backed by File Size Metrics Plus history.
- Added NVENC baseline readiness tracking and training-record counts.
- Added average storage reduction, median observed QP, and average encode-speed analytics.
- Added first-pass diagnoses: Good compression, Audio-limited, Already efficient, Sample-test candidate, Worth profiling, and Needs more data.
- Added candidate ranking for future adaptive sample testing.
- Reads the Metrics Plus database read-only and does not modify media or encoder settings.
- Added direct repository refresh and an **Update plugin** button using Unmanic's normal installed-plugin update route.
