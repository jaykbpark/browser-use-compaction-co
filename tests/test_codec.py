from pathlib import Path

from PIL import Image

from browserdelta.compaction.codec import compact_step
from browserdelta.schemas import (
    ActionResult,
    BrowserAction,
    InteractiveElement,
    PageState,
    StatePointer,
    StepRecord,
)
from browserdelta.storage import write_json


def test_compact_step_prefers_specific_validation_error(tmp_path: Path):
    steps = tmp_path / "steps"
    steps.mkdir()
    before_png = steps / "step_001_before.png"
    after_png = steps / "step_001_after.png"
    Image.new("RGB", (100, 100), "white").save(before_png)
    Image.new("RGB", (100, 100), "white").save(after_png)

    write_json(
        steps / "step_001_before.json",
        PageState(
            url="https://app.test/login",
            title="Login",
            text=["Login"],
            interactive=[
                InteractiveElement(ref="e1", role="textbox", name="Email"),
                InteractiveElement(ref="e2", role="button", name="Submit"),
            ],
        ),
    )
    write_json(
        steps / "step_001_after.json",
        PageState(
            url="https://app.test/login",
            title="Login",
            text=["Login", "Email is required"],
            interactive=[
                InteractiveElement(ref="e5", role="textbox", name="Email"),
                InteractiveElement(ref="e6", role="button", name="Submit"),
            ],
        ),
    )

    step = StepRecord(
        step=1,
        action=BrowserAction(type="click", target="Submit"),
        result=ActionResult(ok=True),
        before=StatePointer(
            screenshot="steps/step_001_before.png",
            state="steps/step_001_before.json",
        ),
        after=StatePointer(
            screenshot="steps/step_001_after.png",
            state="steps/step_001_after.json",
        ),
    )

    observation = compact_step(tmp_path, step)

    assert "Email is required" in observation.summary
    assert "Email is required" in observation.llm_observation
    assert observation.fallback == "none"
    assert observation.route == "text_only"
    assert observation.confidence > 0.85
    assert observation.tokens_estimate > 0
    assert observation.baseline_tokens_estimate > observation.tokens_estimate
    assert observation.reduction_pct > 0


def test_compact_step_adds_checklist_progress_context(tmp_path: Path):
    step = _write_state_pair(
        tmp_path,
        before=PageState(
            url="https://app.test/checks",
            title="Checks",
            text=["Select Alpha and Beta"],
            interactive=[
                InteractiveElement(ref="l1", role="LabelText"),
                InteractiveElement(ref="c1", role="checkbox", name="Alpha", checked=False),
                InteractiveElement(ref="c2", role="checkbox", name="Beta", checked=False),
                InteractiveElement(ref="s1", role="button", name="Submit"),
            ],
            metadata={"goal": "Select Alpha, Beta and click Submit."},
        ),
        after=PageState(
            url="https://app.test/checks",
            title="Checks",
            text=["Select Alpha and Beta"],
            interactive=[
                InteractiveElement(ref="l1", role="LabelText"),
                InteractiveElement(ref="c1", role="checkbox", name="Alpha", checked=True),
                InteractiveElement(ref="c2", role="checkbox", name="Beta", checked=False),
                InteractiveElement(ref="s1", role="button", name="Submit"),
            ],
            metadata={"goal": "Select Alpha, Beta and click Submit."},
        ),
        action=BrowserAction(type="click", target="Alpha"),
    )

    observation = compact_step(tmp_path, step)

    assert "Checklist progress:" in observation.llm_observation
    assert "progress=1/2" in observation.llm_observation
    assert "selected=Alpha" in observation.llm_observation
    assert "remaining=Beta" in observation.llm_observation
    assert "remaining_refs=c2 Beta" in observation.llm_observation
    assert "submit=s1 button Submit" in observation.llm_observation
    assert "c1 checkbox: Alpha" in observation.llm_observation


def test_compact_step_marks_large_checklist_submit_ready(tmp_path: Path):
    names = [f"Item{i}" for i in range(12)]
    before_items = [
        InteractiveElement(ref=f"c{i}", role="checkbox", name=name, checked=i < 8)
        for i, name in enumerate(names)
    ]
    after_items = [
        InteractiveElement(ref=f"c{i}", role="checkbox", name=name, checked=i < 9)
        for i, name in enumerate(names)
    ]
    goal = "Select " + ", ".join(names) + " and click Submit."
    step = _write_state_pair(
        tmp_path,
        before=PageState(
            url="https://app.test/checks",
            title="Checks",
            text=["Select many"],
            interactive=[
                *before_items,
                InteractiveElement(ref="s1", role="button", name="Submit"),
            ],
            metadata={"goal": goal},
        ),
        after=PageState(
            url="https://app.test/checks",
            title="Checks",
            text=["Select many"],
            interactive=[
                *after_items,
                InteractiveElement(ref="s1", role="button", name="Submit"),
            ],
            metadata={"goal": goal},
        ),
        action=BrowserAction(type="click", target="c8"),
    )

    observation = compact_step(tmp_path, step)

    assert "progress=9/12" in observation.llm_observation
    assert "remaining_refs=c9 Item9, c10 Item10, c11 Item11" in observation.llm_observation
    assert "submit_ready_ref=s1" in observation.llm_observation


def test_compact_step_adds_listbox_state_for_blank_options(tmp_path: Path):
    step = _write_state_pair(
        tmp_path,
        before=PageState(
            url="https://app.test/list",
            title="List",
            text=["Choose List Task"],
            interactive=[
                InteractiveElement(ref="lb", role="listbox"),
                InteractiveElement(ref="o1", role="option", selected=False),
                InteractiveElement(ref="o2", role="option", selected=False),
                InteractiveElement(ref="s1", role="button", name="Submit"),
            ],
            metadata={"goal": "Select Antigua and Barbuda from the scroll list and click Submit."},
        ),
        after=PageState(
            url="https://app.test/list",
            title="List",
            text=["Choose List Task"],
            interactive=[
                InteractiveElement(ref="lb", role="listbox"),
                InteractiveElement(ref="o1", role="option", selected=True),
                InteractiveElement(ref="o2", role="option", selected=False),
                InteractiveElement(ref="s1", role="button", name="Submit"),
            ],
            metadata={"goal": "Select Antigua and Barbuda from the scroll list and click Submit."},
        ),
        action=BrowserAction(type="click", target="o1"),
    )

    observation = compact_step(tmp_path, step)

    assert "Listbox state:" in observation.llm_observation
    assert "option labels unavailable" in observation.llm_observation
    assert "o1:(blank) selected" in observation.llm_observation


def test_compact_step_adds_tab_panel_text_context(tmp_path: Path):
    step = _write_state_pair(
        tmp_path,
        before=PageState(
            url="https://app.test/tabs",
            title="Tabs",
            text=["Click Tab Task", "Tab #1", "sed"],
            interactive=[
                InteractiveElement(ref="t1", role="tab", name="Tab #1", selected=True),
                InteractiveElement(ref="t2", role="tab", name="Tab #2", selected=False),
                InteractiveElement(ref="g1", role="generic"),
            ],
            metadata={"goal": 'Switch tabs and click the link "faucibus".'},
        ),
        after=PageState(
            url="https://app.test/tabs",
            title="Tabs",
            text=["Click Tab Task", "Tab #2", "faucibus", "eu"],
            interactive=[
                InteractiveElement(ref="t1", role="tab", name="Tab #1", selected=False),
                InteractiveElement(ref="t2", role="tab", name="Tab #2", selected=True),
                InteractiveElement(ref="g2", role="generic"),
            ],
            metadata={"goal": 'Switch tabs and click the link "faucibus".'},
        ),
        action=BrowserAction(type="click", target="Tab #2"),
    )

    observation = compact_step(tmp_path, step)

    assert "Tab state:" in observation.llm_observation
    assert "active=t2 tab: Tab #2 (selected)" in observation.llm_observation
    assert 'target_hint="faucibus" visible; likely_click_ref=g2' in observation.llm_observation
    assert "visible_panel_text=faucibus; eu" in observation.llm_observation


def _write_state_pair(
    tmp_path: Path,
    *,
    before: PageState,
    after: PageState,
    action: BrowserAction,
) -> StepRecord:
    steps = tmp_path / "steps"
    steps.mkdir(exist_ok=True)
    before_png = steps / "step_001_before.png"
    after_png = steps / "step_001_after.png"
    Image.new("RGB", (100, 100), "white").save(before_png)
    Image.new("RGB", (100, 100), "white").save(after_png)
    write_json(steps / "step_001_before.json", before)
    write_json(steps / "step_001_after.json", after)
    return StepRecord(
        step=1,
        action=action,
        result=ActionResult(ok=True),
        before=StatePointer(
            screenshot="steps/step_001_before.png",
            state="steps/step_001_before.json",
        ),
        after=StatePointer(
            screenshot="steps/step_001_after.png",
            state="steps/step_001_after.json",
        ),
    )
