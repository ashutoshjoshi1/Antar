"""Tests for hardware detection, settings, and the typed experiment formats."""

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from antar.backends.amd_cloud.config import AmdCloudProfile
from antar.benchmarking.config import BenchmarkConfig
from antar.config.settings import CONFIG_FILE_ENV, LemonadeSettings, Settings
from antar.core.errors import AntarError, ExperimentNotFoundError
from antar.core.types import Modality, Task
from antar.deployment.manifest import ArtifactRef
from antar.evaluation.result import DatasetRef, EvaluationResult, MetricValue
from antar.hardware.detect import detect_local_hardware, parse_macos_displays
from antar.modalities.catalog import MODALITY_CATALOG
from antar.models.spec import ModelRef, ModelSpec
from antar.optimization.job import (
    TECHNIQUE_MATRIX,
    Applicability,
    OptimizationJob,
    OptimizationTechnique,
    applicability_of,
)
from antar.orchestration.experiment import ExperimentRecord, ExperimentStore
from tests.conftest import REPO_ROOT

_MODEL = ModelRef(id="org/model", revision="abc123")


def _evaluation(*, simulated: bool = False) -> EvaluationResult:
    return EvaluationResult(
        model=_MODEL,
        backend="mock",
        modality=Modality.TEXT,
        task=Task.CHAT,
        dataset=DatasetRef(name="org/dataset", version="v1", license="CC-BY-4.0"),
        methodology="5 measured runs after 1 warmup; median reported.",
        metrics=(MetricValue(key="tokens_per_second", value=12.5, unit="tokens/s"),),
        simulated=simulated,
    )


def test_detected_hardware_is_internally_consistent() -> None:
    profile = detect_local_hardware()

    assert profile.cpu_model
    assert 0 < profile.memory_available_bytes <= profile.memory_total_bytes
    assert 0 <= profile.disk_free_bytes <= profile.disk_total_bytes
    assert {runtime.name for runtime in profile.runtimes} == {"metal", "rocm", "cuda", "torch"}


def test_parse_macos_displays_extracts_apple_gpu() -> None:
    raw = '{"SPDisplaysDataType": [{"sppci_model": "Apple M3 Pro", "sppci_cores": "18"}]}'

    (gpu,) = parse_macos_displays(raw)

    assert gpu.name == "Apple M3 Pro"
    assert gpu.cores == 18
    assert gpu.shares_system_memory is True
    assert gpu.memory_bytes is None


@pytest.mark.parametrize("raw", ["not json", "[]", '{"SPDisplaysDataType": "x"}', "{}"])
def test_parse_macos_displays_returns_nothing_for_unexpected_output(raw: str) -> None:
    assert parse_macos_displays(raw) == ()


def test_settings_default_to_documented_lemonade_endpoint(settings: Settings) -> None:
    assert str(settings.lemonade.base_url) == "http://localhost:13305/v1"
    assert settings.amd_cloud is None
    assert settings.enable_mock_backend is True


def test_environment_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "antar.yaml"
    config.write_text(
        "lemonade:\n  base_url: http://yaml-host:1/v1\n  timeout_seconds: 9\n"
        "amd_cloud:\n  name: lab\n  ssh_host: 10.0.0.5\n  ssh_user: ubuntu\n"
    )
    monkeypatch.setenv(CONFIG_FILE_ENV, str(config))
    monkeypatch.setenv("ANTAR_LEMONADE__BASE_URL", "http://env-host:2/v1")

    settings = Settings(_env_file=None)

    assert str(settings.lemonade.base_url) == "http://env-host:2/v1"
    assert settings.lemonade.timeout_seconds == 9
    assert settings.amd_cloud is not None
    assert settings.amd_cloud.ssh_host == "10.0.0.5"


def test_api_key_is_not_exposed_in_repr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(CONFIG_FILE_ENV, str(tmp_path / "absent.yaml"))
    monkeypatch.setenv("ANTAR_LEMONADE__API_KEY", "super-secret")

    settings = Settings(_env_file=None)

    assert "super-secret" not in repr(settings)
    assert "super-secret" not in settings.model_dump_json()


@pytest.mark.parametrize(
    ("path", "model"),
    [
        ("configs/hardware/amd-cloud.example.yaml", AmdCloudProfile),
        ("configs/models/text-llm.example.yaml", ModelSpec),
        ("configs/training/qlora-text.example.yaml", OptimizationJob),
        ("configs/benchmarks/text-chat-performance.example.yaml", BenchmarkConfig),
        ("configs/antar.example.yaml", Settings),
    ],
)
def test_shipped_example_configs_validate(path: str, model: type[BaseModel]) -> None:
    data = yaml.safe_load((REPO_ROOT / path).read_text())

    model.model_validate(data)


def test_technique_matrix_covers_every_combination_and_claims_nothing_implemented() -> None:
    assert len(TECHNIQUE_MATRIX) == len(OptimizationTechnique) * len(Modality)
    assert not any(entry.implemented for entry in TECHNIQUE_MATRIX)


def test_every_modality_has_quality_and_performance_metrics() -> None:
    assert {info.modality for info in MODALITY_CATALOG} == set(Modality)
    for info in MODALITY_CATALOG:
        assert {metric.kind.value for metric in info.metrics} == {"quality", "performance"}


def test_optimization_job_rejects_technique_not_applicable_to_modality() -> None:
    assert (
        applicability_of(OptimizationTechnique.QLORA, Modality.IMAGE)
        is Applicability.NOT_APPLICABLE
    )

    with pytest.raises(ValidationError, match="Not applicable to the image modality: qlora"):
        OptimizationJob.model_validate(
            {
                "name": "bad",
                "model": {"id": "org/diffusion"},
                "modality": "image",
                "task": "text_to_image",
                "techniques": [{"technique": "qlora"}],
                "execution_backend": "amd_cloud",
                "target_backend": "lemonade",
            }
        )


def test_evaluation_result_rejects_metric_from_another_modality() -> None:
    with pytest.raises(ValidationError, match="word_error_rate"):
        EvaluationResult(
            model=_MODEL,
            backend="mock",
            modality=Modality.TEXT,
            task=Task.CHAT,
            methodology="n/a",
            metrics=(MetricValue(key="word_error_rate", value=0.1),),
        )


def test_benchmark_config_rejects_unknown_metric() -> None:
    with pytest.raises(ValidationError, match="fid"):
        BenchmarkConfig(
            name="b",
            model=_MODEL,
            backend="mock",
            modality=Modality.TEXT,
            task=Task.CHAT,
            metrics=("fid",),
        )


def test_artifact_requires_sha256_digest() -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(kind="weights", path="model.gguf", sha256="abc", size_bytes=1)


def _record(experiment_id: str, *, simulated: bool = False) -> ExperimentRecord:
    return ExperimentRecord(
        id=experiment_id,
        name="Example",
        model=_MODEL,
        hardware=detect_local_hardware(),
        backend="mock",
        seed=42,
        baseline=_evaluation(simulated=simulated),
    )


def test_experiment_store_round_trips_records(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path / "experiments")
    record = _record("exp-001")

    store.save(record)

    assert store.get("exp-001") == record
    assert store.list() == (record,)


def test_experiment_store_is_empty_before_first_write(tmp_path: Path) -> None:
    assert ExperimentStore(tmp_path / "missing").list() == ()


@pytest.mark.parametrize("experiment_id", ["../secrets", "a/b", "", "UPPER"])
def test_experiment_store_rejects_ids_that_could_escape_root(
    tmp_path: Path, experiment_id: str
) -> None:
    with pytest.raises(ExperimentNotFoundError):
        ExperimentStore(tmp_path).get(experiment_id)


def test_experiment_store_lists_good_records_despite_a_corrupt_one(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    record = _record("good")
    store.save(record)
    (tmp_path / "broken.json").write_text("{not json")

    assert store.list() == (record,)
    with pytest.raises(AntarError, match="unreadable or invalid"):
        store.get("broken")


def test_metric_values_must_be_finite() -> None:
    with pytest.raises(ValidationError):
        MetricValue(key="tokens_per_second", value=float("nan"))


def test_lemonade_url_must_not_embed_credentials() -> None:
    with pytest.raises(ValidationError, match="must not contain credentials"):
        LemonadeSettings.model_validate({"base_url": "http://user:pw@localhost:13305/v1"})


def test_experiment_is_simulated_if_any_result_came_from_a_mock() -> None:
    assert _record("real").simulated is False
    assert _record("fake", simulated=True).simulated is True
