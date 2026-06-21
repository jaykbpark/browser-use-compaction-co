from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from browserdelta.compaction.codec import compact_run
from browserdelta.config import get_settings
from browserdelta.eval.runner import evaluate_comparison, evaluate_run
from browserdelta.storage import (
    read_eval_comparison_report,
    read_eval_report,
    read_jsonl,
    read_steps,
)


router = APIRouter(tags=["runs"])


@router.get("/runs")
def list_runs() -> dict[str, list[str]]:
    root = get_settings().runs_dir
    if not root.exists():
        return {"runs": []}
    runs = sorted(
        path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")
    )
    return {"runs": runs}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    path = get_settings().runs_dir / run_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="run not found")

    return {
        "run_id": run_id,
        "manifest": _read_optional_json(path / "run.json"),
        "steps": [step.model_dump(mode="json") for step in read_steps(path)],
        "compact_observations": read_jsonl(path / "compact_observations.jsonl"),
        "eval_report": _read_eval_report_json(path),
        "eval_full_state_report": _read_eval_report_json(path, context_mode="full_state"),
        "eval_vision_full_state_report": _read_eval_report_json(
            path, context_mode="vision_full_state"
        ),
        "eval_comparison": _read_eval_comparison_report_json(path),
    }


@router.post("/runs/{run_id}/compact")
def compact_saved_run(run_id: str) -> dict:
    path = get_settings().runs_dir / run_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="run not found")
    observations = compact_run(path)
    return {"run_id": run_id, "observations": [obs.model_dump(mode="json") for obs in observations]}


@router.post("/runs/{run_id}/eval")
def evaluate_saved_run(
    run_id: str,
    predictor: str = "heuristic",
    context_mode: str = "compact",
) -> dict:
    path = get_settings().runs_dir / run_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="run not found")
    try:
        report = evaluate_run(path, predictor=predictor, context_mode=context_mode)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"run_id": run_id, "report": report.model_dump(mode="json")}


@router.post("/runs/{run_id}/eval/compare")
def compare_saved_run(
    run_id: str,
    predictor: str = "llm",
    baseline_context_mode: str = "vision_full_state",
) -> dict:
    path = get_settings().runs_dir / run_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="run not found")
    try:
        report = evaluate_comparison(
            path,
            predictor=predictor,
            baseline_context_mode=baseline_context_mode,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"run_id": run_id, "comparison": report.model_dump(mode="json")}


@router.get("/runs/{run_id}/files/{file_path:path}")
def get_run_file(run_id: str, file_path: str) -> FileResponse:
    run_path = (get_settings().runs_dir / run_id).resolve()
    candidate = (run_path / file_path).resolve()
    try:
        candidate.relative_to(run_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid file path") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(candidate)


def _read_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text())


def _read_eval_report_json(path: Path, context_mode: str = "compact") -> dict | None:
    report = read_eval_report(path, context_mode=context_mode)  # type: ignore[arg-type]
    if report is None:
        return None
    return report.model_dump(mode="json")


def _read_eval_comparison_report_json(path: Path) -> dict | None:
    report = read_eval_comparison_report(path)
    if report is None:
        return None
    return report.model_dump(mode="json")
