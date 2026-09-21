# Project Wiki

Welcome to the documentation for **Razorsnake706 Unmanic Custom Plugins**.

This repository contains two cooperating Unmanic plugins designed to make media compression measurable first and adaptive later.

## The short version

**File Size Metrics Plus** records what happened during processing.

**Adaptive NVENC Optimizer** reads that history, explains the results, and is being developed toward automatically choosing per-file GPU quality settings.

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
5. [Adaptive Encoding Roadmap](Adaptive-Roadmap.md)
6. [Troubleshooting and Recovery](Troubleshooting-and-Recovery.md)
7. [Development and Releases](Development-and-Releases.md)

## Preferred Unmanic repository URL

~~~text
https://raw.githubusercontent.com/Razorsnake706/unmanic-custom-plugins/repo/repo-v2.json
~~~

Use repo-v2.json rather than the original repo.json when setting up a fresh installation.

## Current adaptive state

The optimizer is still in **learning mode**. It reads Metrics Plus data and produces diagnoses, but does not alter files or encoder settings.

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
