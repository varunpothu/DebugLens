import pytest

from app.accessibility import (
    ACCESSIBILITY_AUDIT_SCRIPT,
    AccessibilityAuditError,
    audit_page,
    validate_accessibility_report,
)


class FakePage:
    def __init__(self, result: object = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.expression = ""

    def evaluate(self, expression: str) -> object:
        self.expression = expression
        if self.error is not None:
            raise self.error
        return self.result


def issue(target: str = "main > button") -> dict[str, str]:
    return {
        "rule_id": "interactive-name",
        "impact": "serious",
        "message": "Interactive element has no detectable accessible name.",
        "target": target,
    }


def test_audit_page_runs_bounded_dom_script_and_returns_heuristic_status() -> None:
    page = FakePage({
        "engine": "debuglens-static-dom-heuristics-v1",
        "issue_count": 1,
        "truncated": False,
        "issues": [issue()],
    })
    report = audit_page(page)
    assert "img:not([alt])" in page.expression
    assert "form-control-label" in page.expression
    assert report["status"] == "heuristic_not_wcag_certification"
    assert report["issue_count"] == 1
    assert report["issues"][0]["rule_id"] == "interactive-name"


def test_report_validation_drops_malformed_issues_and_bounds_fields() -> None:
    report = validate_accessibility_report({
        "engine": "debuglens-static-dom-heuristics-v1",
        "issue_count": 2,
        "truncated": False,
        "issues": [
            issue("x" * 500),
            {"rule_id": "", "impact": "serious", "message": "invalid", "target": "button"},
        ],
    })
    assert len(report["issues"]) == 1
    assert len(report["issues"][0]["target"]) == 250
    assert report["truncated"] is True


def test_report_caps_issue_count_and_list_size() -> None:
    report = validate_accessibility_report({
        "engine": "debuglens-static-dom-heuristics-v1",
        "issue_count": 500,
        "truncated": True,
        "issues": [issue() for _ in range(200)],
    })
    assert len(report["issues"]) == 100
    assert report["issue_count"] == 500
    assert report["truncated"] is True


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"engine": "other", "issues": []},
        {"engine": "debuglens-static-dom-heuristics-v1", "issues": "not-a-list"},
    ],
)
def test_invalid_browser_results_are_rejected(value: object) -> None:
    with pytest.raises(AccessibilityAuditError):
        validate_accessibility_report(value)


def test_browser_evaluation_failure_is_sanitised() -> None:
    with pytest.raises(AccessibilityAuditError, match="could not inspect"):
        audit_page(FakePage(error=RuntimeError("sensitive page content")))


def test_script_avoids_returning_visible_text_or_form_values() -> None:
    assert "element.textContent" in ACCESSIBILITY_AUDIT_SCRIPT
    assert "document.title" in ACCESSIBILITY_AUDIT_SCRIPT
    assert "value:" not in ACCESSIBILITY_AUDIT_SCRIPT
