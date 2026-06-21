from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel

from browserdelta.config import get_settings
from browserdelta.schemas import (
    CompactObservation,
    EvalComparisonReport,
    ReplayContextMode,
    ReplayReport,
    RunManifest,
    StepRecord,
)


T = TypeVar("T", bound=BaseModel)


def runs_root() -> Path:
    root = get_settings().runs_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_dir(run_id: str) -> Path:
    path = runs_root() / run_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "steps").mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, model_or_data: BaseModel | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(model_or_data, BaseModel):
        data = model_or_data.model_dump(mode="json")
    else:
        data = model_or_data
    path.write_text(json.dumps(data, indent=2) + "\n")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def append_jsonl(path: Path, model_or_data: BaseModel | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(model_or_data, BaseModel):
        data = model_or_data.model_dump(mode="json")
    else:
        data = model_or_data
    with path.open("a") as handle:
        handle.write(json.dumps(data) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_manifest(path: Path, manifest: RunManifest) -> None:
    write_json(path / "run.json", manifest)


def read_manifest(path: Path) -> RunManifest:
    return RunManifest.model_validate(read_json(path / "run.json"))


def write_steps(path: Path, steps: Iterable[StepRecord]) -> None:
    steps_path = _steps_path(path)
    if steps_path.exists():
        steps_path.unlink()
    for step in steps:
        append_jsonl(steps_path, step)


def read_steps(path: Path) -> list[StepRecord]:
    return [StepRecord.model_validate(row) for row in read_jsonl(_steps_path(path))]


def write_compact_observations(path: Path, observations: Iterable[CompactObservation]) -> None:
    out = path / "compact_observations.jsonl"
    if out.exists():
        out.unlink()
    for observation in observations:
        append_jsonl(out, observation)


def write_eval_report(path: Path, report: ReplayReport) -> None:
    write_json(path / _eval_report_name(report.context_mode), report)


def read_eval_report(
    path: Path, context_mode: ReplayContextMode = "compact"
) -> ReplayReport | None:
    report_path = path / _eval_report_name(context_mode)
    if not report_path.exists():
        return None
    return ReplayReport.model_validate(read_json(report_path))


def write_eval_comparison_report(path: Path, report: EvalComparisonReport) -> None:
    write_json(path / "eval_comparison.json", report)


def read_eval_comparison_report(path: Path) -> EvalComparisonReport | None:
    report_path = path / "eval_comparison.json"
    if not report_path.exists():
        return None
    return EvalComparisonReport.model_validate(read_json(report_path))


def _steps_path(path: Path) -> Path:
    manifest_path = path / "run.json"
    if not manifest_path.exists():
        return path / "steps.jsonl"
    return path / read_manifest(path).steps_path


def _eval_report_name(context_mode: ReplayContextMode) -> str:
    if context_mode == "compact":
        return "eval_report.json"
    return f"eval_{context_mode}_report.json"
