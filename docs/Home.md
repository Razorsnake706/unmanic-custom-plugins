# Project Wiki

Welcome to the documentation for **Razorsnake706 Unmanic Custom Plugins**.

This repository contains three complementary Unmanic plugins for measurable compression, NVENC calibration, and controlled one-off processing.

## The short version

**File Size Metrics Plus** records what happened during processing.

**Adaptive NVENC Optimizer** reads that history, captures references, runs/reviews calibration tests, and is being developed toward bounded per-file GPU quality decisions.

**Manual One-Off Queue** lets you select one media file and manually choose the plugin chain used for that single task.

~~~text
media file
   |
   v
Unmanic
   |
   +-- File Size Metrics Plus ---> metrics_plus.db
   |                                 |
   |                                 v
   +------------------------ Adaptive NVENC Optimizer
                                     |
                                     +-- diagnose
                                     +-- learn
                                     +-- sample-test (planned)
                                     +-- choose QP automatically (planned)
~~~

The plugins are intentionally separate. Metrics Plus remains useful even if the adaptive optimizer is never enabled.

## Recommended reading order

1. [Installation](Installation.md)
2. [Architecture](Architecture.md)
3. [File Size Metrics Plus](File-Size-Metrics-Plus.md)
4. [Adaptive NVENC Optimizer](Adaptive-NVENC-Optimizer.md)
5. [Manual One-Off Queue](Manual-One-Off-Queue.md)
6. [Adaptive Encoding Roadmap](Adaptive-Roadmap.md)
7. [Troubleshooting and Recovery](Troubleshooting-and-Recovery.md)
8. [Development and Releases](Development-and-Releases.md)

## Preferred Unmanic repository URL

~~~text
https://raw.githubusercontent.com/Razorsnake706/unmanic-custom-plugins/repo/repo-v2.json
~~~

Use repo-v2.json rather than the original repo.json when setting up a fresh installation.

## Current adaptive state

The optimizer is in the **reference capture + calibration/review** phase. It can prepare and evaluate short test samples while the normal full-file encoder remains under explicit user control. The long-term automatic decision path is still being introduced conservatively.

The intended progression is deliberately conservative:

~~~text
collect trustworthy telemetry
        |
        v
explain existing encodes
        |
        v
sample-test short clips
        |
        v
measure objective quality
        |
        v
calibrate acceptable quality
        |
        v
predict useful QP range
        |
        v
automatically choose QP
        |
        v
automatically decide encode vs skip
~~~

This staged approach prevents an experimental predictor from immediately controlling full-library transcodes.
