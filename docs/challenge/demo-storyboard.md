# Demo storyboard

> A plan for a short demo video. Scenes 1–3 can be recorded with what exists today.
> Scenes 4–7 depend on roadmap milestones M1–M4 and **must not be recorded with mocked or
> invented numbers**. If a scene's feature is not built, cut the scene. The cloud scenes
> have their own script: [Phase 2 demo](phase2-demo.md).

Target length: about three minutes. Screen recording with voiceover.

| # | Scene | On screen | Narration | Needs |
|---|---|---|---|---|
| 1 | The gap | Overview page: cloud and local poles, nine-stage pipeline | Large models do not fit on local hardware. Antar measures what it takes to close that gap. | Built |
| 2 | This device | Hardware page with live detection | Antar starts from the real machine: its processor, memory, and accelerators. | Built |
| 3 | What can run here | Models page filtered by modality; capability matrix | Lemonade already serves these models locally. Antar reads its catalog and states plainly what each backend can and cannot do. | Built |
| 4 | Baseline | Terminal: benchmark command; Benchmarks page with a real record | First, measure the unoptimized model on this device through Lemonade. | M1 |
| 5 | Optimize | Optimization page; job running against the AMD GPU host | The heavy work runs on AMD GPUs through ROCm. | M2–M3 |
| 6 | Compare | Benchmarks page: change from baseline per metric | Every candidate is measured the same way. Here is what each one cost in quality and gained in speed and memory. | M2 |
| 7 | Deploy | Deployments page: selected configuration and exported manifest | Antar selects the configuration that meets the constraints and exports a manifest that reproduces it. | M4 |
| 8 | Close | Repository page | Open source, MIT licensed, reproducible from a config file. | Built |

## Recording notes

- Record on real hardware with a real Lemonade server; name the hardware on screen.
- Turn the mock backend off (`ANTAR_ENABLE_MOCK_BACKEND=false`) so nothing simulated
  appears.
- Show the experiment record file for at least one result, so viewers can see it is data,
  not a slide.
- Do not speed up footage of measurements without saying so.
- State limitations in the video, not only in the write-up.
