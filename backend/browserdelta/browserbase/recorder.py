from __future__ import annotations

from pathlib import Path
import shutil

from playwright.async_api import Page

from browserdelta.browserbase.actions import execute_action
from browserdelta.browserbase.state import capture_state
from browserdelta.schemas import BrowserAction, RunManifest, StepRecord, StatePointer
from browserdelta.storage import append_jsonl, run_dir, write_json, write_manifest


class StepRecorder:
    def __init__(
        self,
        run_id: str,
        start_url: str,
        mode: str,
        reset_existing: bool = True,
        steps_path: str = "steps.jsonl",
        metadata: dict | None = None,
    ) -> None:
        self.run_id = run_id
        self.path = run_dir(run_id)
        self.steps_dir = self.path / "steps"
        self.steps_path = steps_path
        self.step_index = 0
        if reset_existing:
            self._reset_run_files()
        write_manifest(
            self.path,
            RunManifest(
                run_id=run_id,
                start_url=start_url,
                mode=mode,  # type: ignore[arg-type]
                steps_path=steps_path,
                metadata=metadata or {},
            ),
        )

    def _reset_run_files(self) -> None:
        for path in [
            self.path / self.steps_path,
            self.path / "compact_observations.jsonl",
        ]:
            if path.exists():
                path.unlink()
        for path in [self.steps_dir, self.path / "crops"]:
            if path.exists():
                shutil.rmtree(path)
        self.steps_dir.mkdir(parents=True, exist_ok=True)

    async def record_action(self, page: Page, action: BrowserAction) -> StepRecord:
        self.step_index += 1
        stem = f"step_{self.step_index:03d}"
        before_pointer = await self._capture(page, f"{stem}_before")
        result = await execute_action(page, action)
        after_pointer = await self._capture(page, f"{stem}_after")

        record = StepRecord(
            step=self.step_index,
            action=action,
            result=result,
            before=before_pointer,
            after=after_pointer,
        )
        append_jsonl(self.path / self.steps_path, record)
        return record

    async def _capture(self, page: Page, name: str) -> StatePointer:
        screenshot_rel = Path("steps") / f"{name}.png"
        state_rel = Path("steps") / f"{name}.json"
        state = await capture_state(
            page,
            self.path / screenshot_rel,
            screenshot_ref=screenshot_rel.as_posix(),
        )
        write_json(self.path / state_rel, state)
        return StatePointer(screenshot=str(screenshot_rel), state=str(state_rel))
