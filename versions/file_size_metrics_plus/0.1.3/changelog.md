# Changelog

## 0.1.3

- Added an optional **Combine repeat passes** view that groups repeated processing of the same media file into one row.
- Combined rows show the total before/after size across all linked passes and a summary such as Video + Audio.
- Clicking any file now shows the complete processing history for that media item, including each library, worker, video change, audio change, size change, and path.
- Kept the original one-row-per-task view as the default so no existing workflow is lost.
- Improved audio-change detection for new tasks by recording audio profile and bitrate when FFprobe reports them.
- Fixed hidden table columns still reserving width, which caused blank space after the Worker column.
- Refined the default column widths and made the visible columns fill the available panel width more naturally.
- Added a publish-time Python syntax check for the plugin.

## 0.1.2

- Fixed dark-theme text colours in the individual file details dialog.
- Added a before/after size comparison bar chart to the individual file details view.
- Added a total before/after size comparison chart to the main panel; it follows the active filters.
- Added a universal Columns picker so table fields can be shown/hidden and saved per browser.
- Added Default, Space + codecs, Paths, and All column presets.
- Added optional Source folder and Destination folder columns.
- Added click-outside-to-close support for the individual file dialog.
- Added automatic Unmanic plugin-repository refresh when the panel is opened, so future updates are discovered sooner.
- Added GitHub Releases and version-pinned Unmanic repository URLs for rollback.
- Preserved historical plugin ZIPs on the repo branch so older versions remain installable.

## 0.1.1

- Fixed filter dropdown population and now reads the configured Unmanic libraries directly.
- Added resizable table columns with persistent widths and a reset button.
- Added before/after size bars similar to the original File Size Metrics panel.
- Combined before/after into one compact visual size column to reduce horizontal clipping.
- Added horizontal scrolling as a fallback on narrow panels.
- Added clear row hover/click affordances so file details are discoverable.
- Improved responsive layout and full-width use of the data panel.

## 0.1.0

- Initial release.
- Filterable and sortable completion history.
- Summary totals and percentage saved.
- Codec, worker, resolution, audio, duration, and size metadata.
- Per-task details and CSV export.
- Idempotent import from the official File Size Metrics plugin.
