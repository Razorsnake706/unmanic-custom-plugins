# Installation and Setup

## Add the custom repository

In Unmanic, open:

~~~text
Plugins -> Plugin Repositories
~~~

Add:

~~~text
https://raw.githubusercontent.com/Razorsnake706/unmanic-custom-plugins/repo/repo-v2.json
~~~

Then refresh plugin repositories.

## Install the plugins

Install:

~~~text
File Size Metrics Plus
Adaptive NVENC Optimizer
~~~

Metrics Plus should be installed first so it can begin collecting data immediately.

The optimizer can be installed at any time. It reads whatever compatible history is already present.

## Why repo-v2.json is preferred

During development, Unmanic's remote custom-repository fetch path was observed returning stale repository metadata. A restart and normal repository refresh did not always resolve it.

The project therefore uses repo-v2.json as the preferred stable repository identity.

Both plugins also implement a direct GitHub cache refresh for their own update checks.

## Existing File Size Metrics history

Metrics Plus can import history from the official File Size Metrics plugin. Imported rows are marked as legacy/imported because the old database does not contain all of the richer encoder metadata collected by Metrics Plus.

## Reference NVENC baseline used during development

~~~text
Video codec:       HEVC/H.265
Encoder:           hevc_nvenc
GPU:               Quadro P1000
Hardware decode:   NVDEC/CUDA
Preset:            P4 / Medium
Tune:              HQ
Requested profile: Main10
Rate control:      CQP / constqp
QP:                28
Lookahead:         20
Spatial AQ:        enabled
AQ strength:       8
Container:         keep existing
~~~

This is a reference baseline, not a requirement for other users.

## Verify Metrics Plus collection

After a completely new task is scheduled and completed, open the row in Metrics Plus.

A modern record should ideally include both input and output values for FPS, bit depth, total/video/audio bitrate, media duration, encoder settings and the FFmpeg command.

If input fields are blank but output fields are populated, the task may have been scheduled before Metrics Plus was upgraded.

## Verify Adaptive NVENC Optimizer

Open the optimizer data panel.

It should display NVENC record count, training-ready count, average reduction, median QP, average encode speed, baseline status, diagnosis counts and an Encode Advisor table.

The optimizer remains read-only until later adaptive phases are deliberately enabled.
