# Troubleshooting and Recovery

This page is intended to make the project recoverable after a long break, a rebuilt Unmanic container, or a future development restart.

## Preferred repository URL

~~~text
https://raw.githubusercontent.com/Razorsnake706/unmanic-custom-plugins/repo/repo-v2.json
~~~

If plugins stop appearing, first confirm this exact repository URL is configured in Unmanic.

## Repository refresh appears stale

The project originally used repo.json. Unmanic's custom-repository fetch path was observed serving stale metadata during development.

The preferred repo-v2.json URL was introduced to avoid that stale identity.

Both plugin panels also contain a direct repository-refresh mechanism.

## In-panel Update plugin fails

Recovery path:

~~~text
Unmanic -> Plugins
        |
        v
refresh repositories
        |
        v
update plugin from the normal Plugins page
~~~

Once a fixed release is installed, the in-panel updater can be used again.

Modern plugin releases refresh the custom repo, then schedule their own installation in a short-delay background thread after the current panel request has already returned. The UI polls the installed version until the reload is complete. This avoids Tornado errors caused by replacing/reloading a plugin while its own HTTP update request is still executing.

## Metrics Plus database missing

Adaptive NVENC Optimizer expects:

~~~text
<Unmanic userdata>/file_size_metrics_plus/metrics_plus.db
~~~

If the optimizer says Metrics Plus is missing, confirm Metrics Plus is installed, open it at least once, let a task complete, and verify the Unmanic config/userdata volume is persistent.

Do not create a blank database manually.

## Old records have blank input fields

This can happen when the record was imported from the official plugin, the task was already scheduled before a telemetry upgrade, or the older plugin version did not collect that field.

A newly scheduled job is the correct test.

## Impossible video bitrate

Symptoms can look like:

~~~text
File shrank 65%
but
video bitrate 9.43 Mbps -> 9.43 Mbps
~~~

or an output stream bitrate larger than the entire output file bitrate.

Cause: stale Matroska BPS stream metadata.

Current collectors/advisors sanity-check those values and fall back to total bitrate minus known audio bitrate when needed.

## Backup before experimenting

The most important persistent state is the Unmanic configuration/userdata volume, especially the Metrics Plus database.

A useful backup target is the directory containing:

~~~text
.unmanic/userdata/file_size_metrics_plus/
~~~

The GitHub repository itself contains source and release history.

## Reconstructing the project after a restart

If all conversational context is lost:

~~~text
1. Read README.md
2. Read docs/Architecture.md
3. Read docs/Adaptive-Roadmap.md
4. Check current versions in source/*/info.json
5. Check plugin.py and static/index.html for all current plugins
6. Read recent changelogs
7. Verify repo-v2.json on the repo branch
8. Inspect .github/workflows/publish.yml
~~~

That is enough to understand what exists, what is safe, and what phase the adaptive project is in.


## Manual One-Off Queue says the manual library is unsafe

Verify the dedicated manual library has both scanning and filesystem/inotify monitoring disabled.

Its worker-processing flow should contain only:

~~~text
Manual One-Off Queue
~~~

The video/audio plugins you want for an individual task are selected inside the panel; they should not also be enabled directly on the Manual library's worker flow.

## Manual One-Off Queue forgets the selected TV/movie folder

Version 0.2.0 and newer stores the selected manual library, source/settings library, last browse path, plugin order, and checked plugins in browser local storage.

If those settings reset, check whether the browser is clearing site data, running in a private session, or using a different browser/profile. If the stored folder no longer exists, return to the library root and browse to a valid folder.

## Manual One-Off Queue dropdown is white in dark mode

Upgrade to version 0.2.0 or newer. That release explicitly styles both the select control and its option list for dark and light themes.
