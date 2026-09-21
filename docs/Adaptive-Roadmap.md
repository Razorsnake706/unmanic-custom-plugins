# Adaptive Encoding Roadmap

The optimizer is being built in stages so bad assumptions cannot immediately affect an entire library.

## Phase 1 — Telemetry and baseline learning

Status: **baseline threshold reached; collection continues**

Metrics Plus records the real inputs, outputs and encoder settings. Adaptive NVENC Optimizer reads those results and learns what normal P1000/NVENC behavior looks like.

No media modifications.

## Phase 2 — Diagnostic engine

Status: **in progress**

Improve explanations of completed encodes: good compression, audio-limited, already efficient, worth profiling, and similar categories. The advisor now also builds non-destructive sample-test plans and verifies whether a historical row still has access to its original source.

## Phase 3 — Automated sample extraction

Status: **manual execution enabled for safely available originals**

The optimizer calculates representative sample positions and a bounded QP ladder. When the recorded original still exists, a manual test can now execute those short HEVC/NVENC variants without replacing the real media file. XPSNR and SSIM results are persisted for later calibration.

Select multiple short clips rather than encoding the whole file repeatedly. The sampler should eventually prefer varied scenes such as low motion, high motion, dark content, detailed scenes and grain/noise when detected.

The original source is used whenever possible.

## Phase 4 — GPU QP search

Encode the short samples with the same NVENC pipeline but different QP values.

~~~text
QP 28
QP 32
QP 36
        |
        v
quality boundary found
        |
        v
QP 34
QP 35
~~~

A bounded/binary-style search minimizes test work.

## Phase 5 — Objective quality scoring

Compare each encoded sample against the source using XPSNR and SSIM initially. VMAF may be added later.

No single metric should be blindly treated as perfect; calibration ties scores to an acceptable visual threshold.

## Phase 6 — Human calibration

A small calibration set is reviewed manually.

The user should only need to answer questions such as:

~~~text
A: indistinguishable
B: acceptable
C: starting to look worse
D: unacceptable
~~~

The system then maps objective scores to that tolerance. This is a small calibration task, not a per-show workflow.

## Phase 7 — Dynamic QP selection

For each file:

~~~text
predict starting QP from history
        |
        v
sample-test
        |
        v
move QP up/down until quality target is met
        |
        v
choose highest acceptable QP
~~~

Hard safety bounds cap the QP range even if a prediction is wrong.

## Phase 8 — Storage ROI decision

Before a full encode, estimate expected output size, GB saved, processing time and quality confidence.

Skip work that is not worthwhile.

## Phase 9 — Automatic Unmanic integration

Once earlier phases are validated:

~~~text
new media arrives
      |
      v
adaptive analysis/sample test
      |
      v
worth encoding? -- no --> skip
      |
     yes
      |
      v
choose QP automatically
      |
      v
full GPU encode once
      |
      v
Metrics Plus records actual result
      |
      v
model learns from prediction error
~~~

## Safety principles

- Keep full encodes on the GPU unless explicitly configured otherwise.
- Prefer testing the original source rather than re-encoding an already-lossy derivative.
- Use bounded QP ranges.
- Skip when confidence is poor.
- Never use storage savings alone as the quality criterion.
- Keep Metrics Plus history independent from optimizer decisions.
