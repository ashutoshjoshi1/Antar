# Proposed evaluation methodology for the challenge submission

> A proposal. No evaluation has been run and there are no results. The general rules are in
> [the benchmark methodology](../benchmarks/methodology.md); this page applies them to one
> concrete demonstration.

## Question

For one text model and one local device: which configuration gives the best quality that
fits within a stated memory and latency budget, and how much quality does it cost relative
to the unoptimized baseline?

## Setup to be fixed in advance

| Item | To decide and record |
|---|---|
| Model | One open-weight text model, pinned to a revision, with its license |
| Task | One task with an objective metric (for example, multiple-choice accuracy) |
| Dataset | Public, pinned version, license recorded, fixed evaluation subset and seed |
| Local hardware | The device Lemonade runs on, captured as a `HardwareProfile` |
| Cloud hardware | The AMD GPU instance actually provisioned, as declared in the profile |
| Constraints | Memory limit and latency limit, chosen before any measurement |

Choosing the constraints and the dataset subset before measuring matters: selecting them
afterwards would let the result be tuned to look good.

## Procedure

1. **Baseline.** Measure the reference configuration for quality and performance.
2. **Candidates.** Produce each optimized variant, recording technique parameters.
3. **Measure candidates** on the local device through Lemonade, with the identical
   procedure used for the baseline.
4. **Select** the best-quality candidate that satisfies the constraints.
5. **Report every candidate**, including those that failed the constraints or lost quality.

## What to report

- Quality metric with the number of samples and a confidence interval.
- Time to first token and tokens per second: median and spread over the measured runs.
- Peak memory and where the figure came from.
- For each candidate, the change from baseline for every metric.
- Full experiment records, so the numbers can be regenerated.

## Threats to validity

- A small evaluation subset gives wide confidence intervals; differences inside them are
  not findings.
- Results on one device do not generalize to other hardware.
- Thermal throttling and background load affect latency; record conditions and repeat runs.
- A single task does not represent a model's general quality.
- Quantized and full-precision models may differ in ways the chosen metric does not capture.

## What will not be claimed

- Improvements that were not measured.
- Generality beyond the tested model, task, and hardware.
- Support for modalities that were not exercised end to end.
