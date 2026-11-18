"""Published facts about models Antar has verified, used to describe and size cloud deployments.

Every value was read from the model's Hugging Face repository on 2026-11-18
(``/api/models/<id>``, ``config.json``, and the sum of ``*.safetensors`` blob
sizes). Nothing here is estimated. A model missing from this catalog is still
usable; Antar simply knows less about it and says so.

``revision`` is the commit the facts were read from. Pin it when serving for a
reproducible run.
"""

from pydantic import BaseModel, ConfigDict, Field

from antar.core.types import Modality


class KnownModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    family: str
    modalities: tuple[Modality, ...]
    license: str
    revision: str
    parameter_count: int = Field(gt=0)
    weights_bytes: int = Field(gt=0, description="Sum of the safetensors files.")
    precision: str
    context_length: int = Field(gt=0, description="max_position_embeddings of the language model.")
    num_layers: int = Field(gt=0)
    hidden_size: int = Field(gt=0)
    num_attention_heads: int = Field(gt=0)
    num_key_value_heads: int = Field(gt=0)
    reasoning_parser: str | None = Field(
        default=None, description="vLLM --reasoning-parser value for models that think."
    )
    note: str | None = None


KNOWN_MODELS: tuple[KnownModel, ...] = (
    KnownModel(
        id="Qwen/Qwen3-8B",
        name="Qwen3 8B",
        family="Qwen3",
        modalities=(Modality.TEXT,),
        license="apache-2.0",
        revision="b968826d9c46dd6066d109eabc6255188de91218",
        parameter_count=8_190_735_360,
        weights_bytes=16_381_516_776,
        precision="BF16",
        context_length=40_960,
        num_layers=36,
        hidden_size=4096,
        num_attention_heads=32,
        num_key_value_heads=8,
        reasoning_parser="qwen3",
    ),
    KnownModel(
        id="Qwen/Qwen3-32B",
        name="Qwen3 32B",
        family="Qwen3",
        modalities=(Modality.TEXT,),
        license="apache-2.0",
        revision="9216db5781bf21249d130ec9da846c4624c16137",
        parameter_count=32_762_123_264,
        weights_bytes=65_524_328_560,
        precision="BF16",
        context_length=40_960,
        num_layers=64,
        hidden_size=5120,
        num_attention_heads=64,
        num_key_value_heads=8,
        reasoning_parser="qwen3",
    ),
    KnownModel(
        id="Qwen/Qwen3-VL-8B-Instruct",
        name="Qwen3-VL 8B Instruct",
        family="Qwen3-VL",
        modalities=(Modality.TEXT, Modality.VISION),
        license="apache-2.0",
        revision="0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
        parameter_count=8_767_123_696,
        weights_bytes=17_534_339_512,
        precision="BF16",
        context_length=262_144,
        num_layers=36,
        hidden_size=4096,
        num_attention_heads=32,
        num_key_value_heads=8,
        note="Serve with a much smaller --max-model-len than the 262,144-token maximum.",
    ),
    KnownModel(
        id="Qwen/Qwen3-VL-32B-Instruct",
        name="Qwen3-VL 32B Instruct",
        family="Qwen3-VL",
        modalities=(Modality.TEXT, Modality.VISION),
        license="apache-2.0",
        revision="0cfaf48183f594c314753d30a4c4974bc75f3ccb",
        parameter_count=33_357_390_064,
        weights_bytes=66_714_912_872,
        precision="BF16",
        context_length=262_144,
        num_layers=64,
        hidden_size=5120,
        num_attention_heads=64,
        num_key_value_heads=8,
        note="Serve with a much smaller --max-model-len than the 262,144-token maximum.",
    ),
)


def find_known_model(*candidates: str | None) -> KnownModel | None:
    """Look a model up by any of the ids a backend may use for it."""
    wanted = {candidate for candidate in candidates if candidate}
    return next((model for model in KNOWN_MODELS if model.id in wanted), None)
