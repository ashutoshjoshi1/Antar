# AMD Lemonade Developer Challenge — submission outline

> A working outline, not a final submission. **Check the official challenge page for the
> current rules, categories, judging criteria, deadlines, and required deliverables**
> before relying on anything here; this document was written without access to them and
> must be reconciled with them. Nothing here predicts an outcome.

## One-line description

Antar measures what it costs to bring a large model down to local hardware, and exports a
reproducible configuration that runs on Lemonade.

## Problem

Developers can run models locally with Lemonade, but choosing *which* variant to run is
still guesswork. Quantization levels, smaller distilled models, and adapters each trade
quality for speed and memory differently on each machine, and the trade is rarely measured
consistently.

## What Antar adds to Lemonade

Antar does not replace or duplicate Lemonade. Lemonade serves models; Antar decides, with
evidence, which model configuration is worth serving on a given device.

- Uses Lemonade's documented API for discovery today, and for inference and measurement next.
- Treats Lemonade as the deployment target whose measured behaviour defines success.
- Uses AMD GPUs through ROCm for the compute-heavy steps that do not fit locally.

## What exists at the time of writing

- Lemonade connectivity and model discovery, verified against a real Lemonade server.
- Local hardware detection and a capability matrix that states what each backend can and
  cannot do.
- Typed, validated formats for optimization jobs, benchmarks, experiment records, and
  deployment manifests.
- A dashboard showing all of the above from live data.
- Text and image-understanding inference and performance benchmarks through Lemonade,
  verified on a real server.
- Cloud inference through vLLM on AMD GPUs, reference-answer scoring, and a
  local-versus-cloud comparison: implemented with mocked tests, **not yet run on real AMD
  hardware**. See [Phase 2](../phase2-amd-cloud.md).

## What must exist before submitting

Tracked in [the roadmap](../ROADMAP.md). At minimum, milestones M1 and M2:

- [x] Text inference through Lemonade.
- [x] A performance benchmark producing real reports (none are published yet).
- [ ] Live verification of the cloud path on a real AMD GPU host, and a first real
      local-versus-cloud report.
- [ ] A quality evaluator on a pinned, licensed dataset. (Reference-answer scoring on small
      prompt sets written for Antar exists.)
- [ ] One complete baseline-versus-optimized comparison, reproducible from a config file.
- [ ] Results recorded on named hardware, with methodology.

## Deliverables to prepare

- [ ] Public repository with installation instructions that work from a clean machine.
- [ ] Demo video — see [the storyboard](demo-storyboard.md) and the
      [Phase 2 demo script](phase2-demo.md).
- [ ] Written description: problem, approach, how Lemonade is used, limitations.
- [ ] Evaluation write-up — see [the methodology](evaluation-methodology.md).
- [ ] Whatever else the official rules require.

## Limitations to state openly

- Which modalities were actually exercised.
- Hardware the results were measured on, and that they may not transfer.
- Anything simulated or not yet implemented.
