# Phase 2 demo script

> Scenes 1–6 can be recorded today with no cloud host. Scenes 7–11 need a real AMD GPU
> instance and **must not be recorded with mocked or invented numbers**. A simulated
> comparison may be shown only with its "Simulated" label on screen. If a scene's
> prerequisite is not met, cut the scene.

Target length: about four minutes. Screen recording with voiceover.

## Recordable today, offline

| # | Scene | On screen | Narration | Needs |
|---|---|---|---|---|
| 1 | Two places to run a model | Models page with the location filter | Every model says where it actually runs: on this machine, or on a cloud GPU. | Built |
| 2 | Nothing connected, said plainly | AMD Cloud page with no endpoint configured | With no cloud host, Antar says so. No placeholder GPU, no fake status. | Built |
| 3 | Will it fit? | Feasibility calculator: Qwen3 32B on one 192 GB GPU, then on one 48 GB GPU | Before downloading sixty gigabytes, Antar works out the memory budget from the model's published size and shape. It is arithmetic, and it says so. | Built |
| 4 | Credits are finite | Cost panel: enter a price and a credit balance, press "now" | Antar has no billing API. You enter the price; it shows elapsed time and an estimate, and warns as the credit runs down. | Built |
| 5 | Lemonade can route to it | Settings: register the provider with a real Lemonade; Models page shows `antaramd.*` | Lemonade has experimental cloud routing. Antar can register its endpoint there, and Lemonade's own warnings are shown as they are. | A running Lemonade, and an OpenAI-compatible endpoint |
| 6 | The comparison pipeline | Comparison Lab with the two mock models; the report with the **Simulated** label visible | This run uses the mock backend, so it is labelled simulated everywhere. It shows the shape of a report, not a result. | Built |

For scene 5, state on screen what the endpoint is. On 2026-11-18 this was checked against
Lemonade 2026.46.2 with a stand-in server, not vLLM.

## Needs a live AMD host

| # | Scene | On screen | Narration | Needs |
|---|---|---|---|---|
| 7 | Check the machine | `uv run antar cloud-preflight` against the real host | Antar checks the host before anything runs, and tells you how to fix what fails. It changes nothing. | Live host |
| 8 | Serve a large model | Terminal on the host: `start_vllm.sh`, `check_vllm.sh --wait` | You start the server. Antar never starts anything that bills. | Live host |
| 9 | Real GPUs | AMD Cloud page: connected, the GPU table | These readings come from amd-smi on the host. They are for the whole GPU, not per request. | Live host, SSH configured |
| 10 | Same question, two places | Playground with a local model, then the cloud model; Vision with a cloud vision model | The same chat, the same metrics panel, a different place. Where the backend reports no timings, the panel says unavailable. | Live host |
| 11 | Compare | Comparison Lab: confirmation step, live progress, the report, the Markdown export | The same prompts on both sides. Every number says who measured it. This is not a hardware comparison, and the report says that first. | Live host |

## Recording notes

- For scenes 7–11, name the real hardware on screen: the local machine, and the GPU model
  and count the preflight reported.
- Turn the mock backend off (`ANTAR_ENABLE_MOCK_BACKEND=false`) for scenes 7–11 so nothing
  simulated can appear.
- Show a saved report file from `data/comparisons/` for at least one result.
- Show the caveats. Do not crop the "not a hardware-normalized comparison" notice.
- Do not speed up footage of measurements without saying so.
- Keep the API key, hostnames, and IP addresses off screen. The dashboard never shows the
  key; your terminal might.

## Operator checklist

Use this every time you finish with a cloud instance. Antar can confirm **none** of these
steps for you: it has no access to your provider.

### Before you shut anything down

- [ ] Wait for, or cancel, any running comparison or benchmark. A cancelled run still
      saves what finished.
- [ ] Export what you want to keep: on the Experiment History page, or
      `GET /api/v1/comparisons/{id}/export?format=json|csv|md`.
- [ ] Copy the reports: `data/comparisons/` and `data/benchmarks/` on your machine. They
      are git-ignored and exist nowhere else.
- [ ] Copy the host's records if you want load and download times kept:
      `scp my-amd-host:antar/'*.json' ./host-records/`
      (`vllm-deployment.json`, `vllm-ready.json`, `model-download.json`).
- [ ] Save logs if something went wrong: `docker logs antar-vllm > vllm.log` on the host.
- [ ] Note the preflight facts (GPU model, count, driver, ROCm) with your results.
- [ ] If you registered the endpoint with Lemonade, remove the provider in Settings.

### Shutting down: three different things

| Action | What it does | Does billing stop? |
|---|---|---|
| **Stop the model process**: `./stop_vllm.sh` on the host | Stops and removes the vLLM container. Frees GPU memory | **No.** The machine is still running |
| **Power off the VM**, in your provider's console | Stops the operating system | **Depends on the provider.** Many keep charging for a stopped instance's reserved GPU, disk, or address. Read your provider's terms |
| **Destroy the instance**, in your provider's console | Deletes the machine and, usually, its disk | **Usually yes**, for the instance. Separately billed storage or addresses may remain |

For most providers only destroying the instance, and any attached storage you no longer
need, ends all charges. Destroying also deletes the downloaded weights and anything else
on the disk.

- [ ] `./stop_vllm.sh` on the host.
- [ ] Close the SSH tunnel on your machine.
- [ ] Power off or destroy the instance in your provider's console, according to its
      terms.
- [ ] **Check the provider's console or billing page** to confirm the instance's state.
      This is the only confirmation there is.
- [ ] On the AMD Cloud page, record the stop time. This only stops Antar's own estimate
      from counting; it is your statement, and Antar says so.
- [ ] Unset `ANTAR_CLOUD__BASE_URL` (or leave it; Antar will report the endpoint as
      unreachable, which is accurate).
- [ ] If the API key was shown anywhere, do not reuse it.
