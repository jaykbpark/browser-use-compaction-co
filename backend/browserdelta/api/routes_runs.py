from pathlib import Path

from fastapi import APIRouter, HTTPException

from browserdelta.compaction.codec import compact_run
from browserdelta.config import get_settings
from browserdelta.storage import read_jsonl


router = APIRouter(tags=["runs"])


@router.get("/runs")
def list_runs() -> dict[str, list[str]]:
    root = get_settings().runs_dir
    if not root.exists():
        return {"runs": []}
    runs = sorted(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))
    return {"runs": runs}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    path = get_settings().runs_dir / run_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="run not found")

    return {
        "run_id": run_id,
        "manifest": _read_optional_json(path / "run.json"),
        "steps": read_jsonl(path / "steps.jsonl"),
        "compact_observations": read_jsonl(path / "compact_observations.jsonl"),
    }


@router.post("/runs/{run_id}/compact")
def compact_saved_run(run_id: str) -> dict:
    path = get_settings().runs_dir / run_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="run not found")
    observations = compact_run(path)
    return {"run_id": run_id, "observations": [obs.model_dump(mode="json") for obs in observations]}


def _read_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text())
