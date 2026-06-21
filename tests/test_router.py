from browserdelta.compaction.router import route_observation
from browserdelta.schemas import BoundingBox, StructuralChange, VisualDiff, VisualRegion


def test_routes_text_only_when_dom_explains_change():
    decision = route_observation(
        changes=[StructuralChange(type="validation_error", detail="Email is required")],
        visual=VisualDiff(changed_pct=0.2),
        action_ok=True,
    )

    assert decision.route == "text_only"
    assert decision.fallback == "none"
    assert decision.confidence > 0.85


def test_routes_crop_when_visual_changes_without_dom_explanation():
    decision = route_observation(
        changes=[],
        visual=VisualDiff(
            changed_pct=8.0,
            regions=[
                VisualRegion(
                    bbox=BoundingBox(x=10, y=20, width=100, height=80),
                )
            ],
        ),
        action_ok=True,
    )

    assert decision.route == "crop_with_context"
    assert decision.fallback == "crop"
    assert decision.confidence < 0.7


def test_routes_crop_when_only_focus_change_explains_aligned_visual_region():
    decision = route_observation(
        changes=[StructuralChange(type="focus_changed", detail="Focus changed to button Redraw")],
        visual=VisualDiff(
            changed_pct=4.0,
            regions=[
                VisualRegion(
                    bbox=BoundingBox(x=10, y=20, width=100, height=80),
                    element_ref="e4",
                    element_role="canvas",
                    element_name="Revenue chart",
                    overlap_pct=96.0,
                )
            ],
        ),
        action_ok=True,
    )

    assert decision.route == "crop_with_context"
    assert decision.fallback == "crop"
    assert "weak DOM" in decision.reason


def test_routes_full_screenshot_for_large_visual_change():
    decision = route_observation(
        changes=[StructuralChange(type="text_added", detail="Many items appeared")],
        visual=VisualDiff(changed_pct=60.0),
        action_ok=True,
    )

    assert decision.route == "full_screenshot"
    assert decision.fallback == "full_screenshot"
    assert "Large visual change" in decision.reason


def test_routes_text_only_when_strong_semantic_event_explains_large_visual_change():
    decision = route_observation(
        changes=[
            StructuralChange(type="modal_opened", detail="A modal or dialog opened"),
            StructuralChange(type="form_fields_appeared", detail="New form fields appeared"),
        ],
        visual=VisualDiff(changed_pct=84.0),
        action_ok=True,
    )

    assert decision.route == "text_only"
    assert decision.fallback == "none"
    assert decision.confidence > 0.85


def test_failed_action_stays_text_only():
    decision = route_observation(
        changes=[],
        visual=VisualDiff(changed_pct=80.0),
        action_ok=False,
    )

    assert decision.route == "text_only"
    assert decision.fallback == "none"
    assert decision.confidence == 0.95
