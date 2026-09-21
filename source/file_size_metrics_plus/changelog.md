# Changelog

## 0.1.12

- Fixed direct self-update again by using the same installed-plugin update route that Unmanic's normal Plugins page uses.
- The updater now looks up File Size Metrics Plus' installed database-table ID and calls `/api/v2/plugins/update` with that ID.
- This avoids using the install-by-plugin-ID endpoint for an already installed plugin, which was producing a Tornado traceback during self-update.
- Kept post-update version verification so a transient response during plugin reload is not reported as a failure when the update actually completed.

## 0.1.11

- Improved bitrate collection for MKV/Matroska streams where ffprobe does not populate `stream.bit_rate`.
- Metrics Plus now reads common per-stream `BPS` tags and can estimate stream bitrate from `NUMBER_OF_BYTES` plus duration.
- This improves aggregate audio bitrate and derived video-bitrate estimates for files with multiple copied audio tracks.
- No encoding behavior changed.

## 0.1.10

- Fixed the **Update plugin** button on current Unmanic builds.
- Switched self-update installation from the legacy v1 form endpoint to Unmanic's v2 JSON plugin-install API.
- The updater no longer blindly parses every install response as JSON, preventing the `Unexpected token 'T' / Traceback is not valid JSON` browser error.
- Added a post-install version verification fallback because updating File Size Metrics Plus can reload its own Python module while the install request is still completing.
- Repository refresh behavior remains unchanged.

## 0.1.9

- Expanded Metrics Plus into the data-collection foundation for the planned adaptive NVENC optimizer.
- New jobs now record source/output duration, effective total bitrate, video bitrate when available/estimable, audio bitrate, FPS, bit depth, container, HDR flag, color metadata, audio stream count, and subtitle stream count.
- Added full source/output probe JSON for future diagnostics and model training without needing another database migration for every FFprobe field.
- Added worker-runner and actual FFmpeg command capture from Unmanic's worker completion log.
- Added structured encoder metadata extracted from the real FFmpeg command, including encoder, rate-control mode, QP/CQ value, preset, tune, profile, lookahead, spatial/temporal AQ, AQ strength, and hardware decode mode.
- Existing Metrics Plus databases are upgraded in place; historical rows are preserved and simply have blank values for fields that were not recorded at the time.
- The per-file details page now shows the new adaptive-encoding diagnostics and the captured encoder command.
- CSV export now includes the new diagnostic fields.
- No encoding behavior is changed in this release; this phase is observation-only so we can collect trustworthy baseline data before enabling automatic quality decisions.

## 0.1.8

- Added an **Update plugin** button directly to the File Size Metrics Plus page.
- The update button refreshes the custom repository cache directly from GitHub, checks the latest version, installs the update through Unmanic, and reloads the panel after a successful update.
- When one or more history entries are selected, the summary cards at the top now switch to the selected entries instead of the active table filters.
- The total before/after size chart also switches to the selected entries.
- Clearing the selection immediately restores the normal filtered summary.
- Selection summaries work across pages and with Select all matching / Quick select selections.

## 0.1.7

- Added a **Quick select** menu for mass-selecting useful groups without changing the visible table filters first.
- Quick select includes Legacy/imported, Failed, Successful, Smaller, Larger, and No-size-change entries.
- Added dynamic quick-select groups for every configured Library, recorded Worker, Input codec, and Output codec.
- Quick selections are additive to the existing selection.
- Current filters remain active; when choosing a library/worker/codec/status/size group, that quick-select choice replaces only the matching filter dimension while preserving the other active filters.
- **Select all matching** remains available as a one-click option.

## 0.1.6

- Added **Select all matching** to select every record that matches the currently active filters, not just the 50 rows on the visible page.
- The selection count updates to the full matching count and visible matching rows highlight immediately.
- Bulk deletion now processes selected IDs in safe batches, so deleting hundreds or thousands of selected history entries does not run into URL/SQLite parameter limits.
- Existing page-level Select All, Clear selection, and manual row selection remain available.

## 0.1.5

- Added a direct GitHub repository refresh path that bypasses Unmanic's upstream custom-repository proxy cache.
- File Size Metrics Plus now refreshes its configured custom-repo cache directly from GitHub when the panel opens.
- Added **Check plugin updates** to force a direct repository refresh from the panel.
- This is intended to prevent future releases from getting stuck on stale versions even when Unmanic's normal Refresh Repositories action does not update the custom repo.

## 0.1.4

- Removed the **Combine repeat passes** option from the main table.
- Kept the richer per-file processing history view, so clicking a task still shows linked video/audio passes for that media file.
- Added multi-select checkboxes and a page-level Select All checkbox.
- Added **Delete selected** for bulk removal of metrics history entries; deleting history never deletes media files.
- Added **Clear selection** and persistent selection while paging through results.
- Filters now apply automatically:
  - dropdown/date changes apply immediately;
  - search and numeric percentage filters use a short debounce while typing.
- Removed the Apply button and renamed Reset to **Reset filters**.
- Added stale-request protection so quickly changing filters cannot let an older response overwrite a newer one.

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
