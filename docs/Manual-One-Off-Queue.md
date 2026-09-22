# Manual One-Off Queue

Manual One-Off Queue is the repository's task-specific processing controller. It is intended for experiments, calibration runs, troubleshooting, and any case where you want to process **one specific movie or episode** with a manually selected plugin chain without changing the normal TV/Movie library flow.

## What it does

The data panel lets you:

- choose a source/settings library;
- browse that library to a specific media file;
- choose a dedicated manual-processing library;
- select exactly which installed worker/postprocessor plugins should participate;
- drag plugins up or down to control their order;
- keep using the up/down buttons for precise ordering;
- force-queue only the selected file.

The selected plugins reuse the per-library settings from the chosen source/settings library.

## Recommended library layout

Create a dedicated Unmanic library such as:

~~~text
Name: Manual
Path: /library
Scanner: disabled
Filesystem/inotify monitoring: disabled
~~~

The Manual One-Off Queue controller should be the **only worker-processing plugin** enabled on this manual library.

This is important. The manual library is intentionally a dispatch container, not another normal scanning library.

A typical setup is:

~~~text
Manual processing library
  Manual — /library

Source/settings library
  TV Shows — /library/tv-shows
  Movies GPU — /library/movies
  Movies CPU — /library/movies
~~~

The selected media file stays in its real library path. The manual task simply borrows the chosen source library's plugin settings while the controller dispatches the plugins selected for that one job.

## Plugin ordering

Worker-processing plugins execute in the order shown in the panel.

You can reorder them by dragging a plugin row. The arrow buttons remain available as a keyboard/mouse-friendly fallback.

For example:

~~~text
Adaptive NVENC Optimizer
        |
        v
Transcode Video Files
        |
        v
Transcode Audio
~~~

That ordering is useful for calibration because Adaptive can inspect/capture the untouched source before the video transcoder replaces it.

## Persistent panel choices

Version 0.2.0 and newer remembers panel state in the browser using local storage.

The panel persists:

- manual-processing library;
- source/settings library;
- last browsed folder;
- plugin order;
- checked plugins.

For example, if the source/settings library is /library/tv-shows and you last browsed into a show's season folder, reopening the panel returns to the same source library and folder when that path still exists.

Persistence is browser/profile-specific. Opening Unmanic in another browser or clearing site data resets the remembered choices.

## Dark-theme dropdowns

Version 0.2.0 explicitly styles select controls and their option list for both dark and light system themes. This avoids browser-native white dropdown option panels when Unmanic itself is using a dark theme.

## Safety checks

The plugin refuses to queue a task through a manual library it considers unsafe.

The manual library should have:

- scanner disabled;
- inotify/filesystem monitoring disabled;
- Manual One-Off Queue enabled;
- no other worker-processing plugins enabled directly on that library.

Those checks protect the normal media libraries from being accidentally processed with a temporary one-off configuration.

## Intended uses

Good uses include:

- testing video-only versus video+audio transcoding;
- manually testing Adaptive NVENC calibration candidates;
- troubleshooting one troublesome episode;
- comparing encoder settings;
- manually running cleanup/remux plugins on one file;
- validating a new plugin before enabling it across a library.

It is not intended to replace the normal Unmanic library scanner for everyday bulk processing.
