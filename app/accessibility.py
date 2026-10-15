"""Bounded static accessibility heuristics for a Playwright-compatible page.

This is a lightweight issue detector, not a WCAG conformance engine. It avoids returning visible
page text or form values, and caps all collected findings.
"""
from __future__ import annotations

from typing import Any, Protocol

MAX_ISSUES = 100
MAX_TARGET_LENGTH = 250


class AccessibilityAuditError(RuntimeError):
    """Raised when a page cannot produce a valid accessibility audit report."""


class PageEvaluator(Protocol):
    def evaluate(self, expression: str) -> object:
        """Evaluate a browser-side expression and return JSON-compatible data."""


ACCESSIBILITY_AUDIT_SCRIPT = r"""
() => {
  const issues = [];
  const add = (rule_id, impact, message, element) => {
    if (issues.length >= 101) return;
    issues.push({
      rule_id,
      impact,
      message,
      target: selectorFor(element)
    });
  };
  const selectorFor = (element) => {
    if (!element || !element.tagName) return "document";
    const parts = [];
    let current = element;
    while (current && current.nodeType === 1 && parts.length < 5) {
      let part = current.tagName.toLowerCase();
      if (current.id && /^[A-Za-z][A-Za-z0-9_:-]{0,40}$/.test(current.id)) {
        part += "#" + current.id;
      } else if (current.parentElement) {
        const siblings = Array.from(current.parentElement.children)
          .filter((sibling) => sibling.tagName === current.tagName);
        if (siblings.length > 1) part += ":nth-of-type(" + (siblings.indexOf(current) + 1) + ")";
      }
      parts.unshift(part);
      current = current.parentElement;
    }
    return parts.join(" > ").slice(0, 250);
  };
  const nonEmpty = (value) => typeof value === "string" && value.trim().length > 0;
  const hasReferenceName = (element) => {
    const labelledBy = element.getAttribute("aria-labelledby");
    if (nonEmpty(labelledBy)) {
      const labelText = labelledBy.split(/\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((node) => node.textContent || "")
        .join(" ");
      if (nonEmpty(labelText)) return true;
    }
    return ["aria-label", "title"].some((name) => nonEmpty(element.getAttribute(name)));
  };
  const hasControlLabel = (element) => {
    if (hasReferenceName(element)) return true;
    if (element.labels && Array.from(element.labels).some((label) => nonEmpty(label.textContent))) return true;
    return false;
  };

  if (!nonEmpty(document.documentElement.getAttribute("lang"))) {
    add("document-language", "serious", "Document language is missing.", document.documentElement);
  }
  if (!nonEmpty(document.title)) {
    add("document-title", "moderate", "Document title is missing.", document.documentElement);
  }
  if (!document.querySelector("main, [role='main']")) {
    add("main-landmark", "moderate", "No main landmark was found.", document.body);
  }
  document.querySelectorAll("img:not([alt])").forEach((element) => {
    add("image-alt", "serious", "Image has no alt attribute.", element);
  });
  document.querySelectorAll("button, a[href], summary, [role='button'], [role='link']").forEach((element) => {
    const textName = nonEmpty(element.textContent);
    if (!hasReferenceName(element) && !textName) {
      add("interactive-name", "serious", "Interactive element has no detectable accessible name.", element);
    }
  });
  document.querySelectorAll("input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']), select, textarea").forEach((element) => {
    if (!hasControlLabel(element)) {
      add("form-control-label", "serious", "Form control has no associated label or ARIA name.", element);
    }
  });
  const seenIds = new Set();
  document.querySelectorAll("[id]").forEach((element) => {
    if (seenIds.has(element.id)) add("duplicate-id", "moderate", "ID value is duplicated.", element);
    seenIds.add(element.id);
  });
  let previousHeadingLevel = 0;
  document.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((element) => {
    const level = Number(element.tagName.slice(1));
    if (previousHeadingLevel > 0 && level > previousHeadingLevel + 1) {
      add("heading-order", "moderate", "Heading level skips one or more levels.", element);
    }
    previousHeadingLevel = level;
  });
  document.querySelectorAll("[aria-hidden='true']").forEach((container) => {
    if (container.matches("a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])") ||
        container.querySelector("a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])")) {
      add("aria-hidden-focusable", "serious", "aria-hidden subtree contains a focusable element.", container);
    }
  });
  document.querySelectorAll("[tabindex]").forEach((element) => {
    const value = Number(element.getAttribute("tabindex"));
    if (Number.isFinite(value) && value > 0) {
      add("positive-tabindex", "moderate", "Positive tabindex can disrupt logical keyboard order.", element);
    }
  });
  const truncated = issues.length > 100;
  return {
    engine: "debuglens-static-dom-heuristics-v1",
    issue_count: issues.length,
    truncated,
    issues: issues.slice(0, 100)
  };
}
"""


def validate_accessibility_report(value: object) -> dict[str, Any]:
    """Validate and bound browser-side output before returning it to API or UI callers."""
    if not isinstance(value, dict):
        raise AccessibilityAuditError("Accessibility audit returned a non-object result.")
    if value.get("engine") != "debuglens-static-dom-heuristics-v1":
        raise AccessibilityAuditError("Accessibility audit engine identifier is invalid.")
    raw_issues = value.get("issues")
    if not isinstance(raw_issues, list):
        raise AccessibilityAuditError("Accessibility audit issues must be a list.")
    issues: list[dict[str, str]] = []
    for item in raw_issues[:MAX_ISSUES]:
        if not isinstance(item, dict):
            continue
        rule_id = item.get("rule_id")
        impact = item.get("impact")
        message = item.get("message")
        target = item.get("target")
        if not isinstance(rule_id, str) or not isinstance(impact, str):
            continue
        if not isinstance(message, str) or not isinstance(target, str):
            continue
        if not rule_id.strip() or not impact.strip() or not message.strip() or not target.strip():
            continue
        issues.append({
            "rule_id": rule_id[:80],
            "impact": impact[:20],
            "message": message[:300],
            "target": target[:MAX_TARGET_LENGTH],
        })
    issue_count = value.get("issue_count")
    if not isinstance(issue_count, int) or issue_count < len(issues):
        issue_count = len(issues)
    return {
        "engine": "debuglens-static-dom-heuristics-v1",
        "issue_count": issue_count,
        "truncated": bool(value.get("truncated")) or issue_count > len(issues),
        "issues": issues,
        "status": "heuristic_not_wcag_certification",
    }


def audit_page(page: PageEvaluator) -> dict[str, Any]:
    """Run bounded accessibility heuristics on a Playwright-compatible page object."""
    try:
        result = page.evaluate(ACCESSIBILITY_AUDIT_SCRIPT)
    except Exception as exc:
        raise AccessibilityAuditError("Accessibility audit could not inspect the page.") from exc
    return validate_accessibility_report(result)
