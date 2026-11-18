"""Will this model fit? An approximate GPU memory budget, computed before anything is deployed.

This is arithmetic on published model facts, not a measurement:

* **Weights** — the size of the model's safetensors files.
* **KV cache** — per token, two tensors (key and value) per layer of
  ``num_key_value_heads x head_dim`` values, at the weight precision. The
  budget assumes every concurrent sequence fills the whole context, which is
  the worst case.
* **Runtime overhead** — a flat, configurable allowance per GPU for the
  runtime's own allocations. The default is an assumption, not a vLLM figure.

vLLM reserves a fixed fraction of each GPU (``--gpu-memory-utilization``) and
gives whatever the weights leave of it to the KV cache, so the question
answered here is whether the requested context and concurrency fit in that
reservation. Vision encoders' activation memory is not modelled. Treat "fits"
as "worth trying", and a real load as the only proof.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from antar.models.catalog import KnownModel

GIB = 1024**3
_BYTES_PER_VALUE = {"BF16": 2, "F16": 2, "FP16": 2, "F32": 4, "FP32": 4, "FP8": 1}

Verdict = Literal["fits", "tight", "does_not_fit"]


class FeasibilityRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    gpu_count: int = Field(default=1, ge=1, le=16, description="Physical GPUs used.")
    gpu_memory_bytes: int = Field(gt=0, description="Memory of one GPU.")
    max_model_len: int | None = Field(
        default=None, ge=1, description="Context to serve; defaults to the model's maximum."
    )
    concurrency: int = Field(default=1, ge=1, le=1024)
    gpu_memory_utilization: float = Field(default=0.9, gt=0, le=1)
    runtime_overhead_bytes_per_gpu: int = Field(default=2 * GIB, ge=0)


class FeasibilityEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    gpu_count: int
    max_model_len: int
    concurrency: int
    weights_bytes: int
    kv_cache_bytes: int
    kv_cache_bytes_per_token: int
    runtime_overhead_bytes: int
    required_bytes: int
    usable_bytes: int
    total_bytes: int
    headroom_bytes: int
    verdict: Verdict
    max_concurrency_at_full_context: int
    notes: tuple[str, ...]


def kv_cache_bytes_per_token(model: KnownModel) -> int:
    head_dim = model.hidden_size // model.num_attention_heads
    width = _BYTES_PER_VALUE.get(model.precision.upper(), 2)
    return 2 * model.num_layers * model.num_key_value_heads * head_dim * width


def estimate_feasibility(model: KnownModel, request: FeasibilityRequest) -> FeasibilityEstimate:
    context = min(request.max_model_len or model.context_length, model.context_length)
    per_token = kv_cache_bytes_per_token(model)
    kv_cache = per_token * context * request.concurrency
    overhead = request.runtime_overhead_bytes_per_gpu * request.gpu_count
    total = request.gpu_memory_bytes * request.gpu_count
    usable = round(total * request.gpu_memory_utilization)
    required = model.weights_bytes + kv_cache + overhead
    headroom = usable - required
    cache_room = usable - model.weights_bytes - overhead

    if headroom < 0:
        verdict: Verdict = "does_not_fit"
    elif headroom < usable * 0.1:
        verdict = "tight"
    else:
        verdict = "fits"

    notes = [
        "Approximate. Weights are the published file sizes; the KV cache assumes every "
        "concurrent sequence fills the whole context.",
        "The runtime overhead is a configurable allowance, not a measured figure.",
    ]
    if request.gpu_count > 1:
        notes.append(
            f"Assumes --tensor-parallel-size {request.gpu_count}. Sharding across GPUs adds "
            "communication overhead that is not modelled."
        )
    if len(model.modalities) > 1:
        notes.append("Image inputs use additional activation memory that is not modelled.")
    if model.note:
        notes.append(model.note)
    return FeasibilityEstimate(
        model=model.id,
        gpu_count=request.gpu_count,
        max_model_len=context,
        concurrency=request.concurrency,
        weights_bytes=model.weights_bytes,
        kv_cache_bytes=kv_cache,
        kv_cache_bytes_per_token=per_token,
        runtime_overhead_bytes=overhead,
        required_bytes=required,
        usable_bytes=usable,
        total_bytes=total,
        headroom_bytes=headroom,
        verdict=verdict,
        max_concurrency_at_full_context=max(0, cache_room // (per_token * context)),
        notes=tuple(notes),
    )
