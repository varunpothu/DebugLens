# Accessibility heuristics

`app.accessibility.audit_page(page)` runs a small synchronous Playwright-compatible DOM audit. When browser capture is enabled, DebugLens automatically attaches this bounded report to the durable browser evidence alongside the screenshot analysis and runtime error summary. It checks for common issues:

- missing document language and title;
- missing main landmark;
- images without an `alt` attribute;
- interactive controls without a detectable accessible name;
- form controls without a label or ARIA name;
- duplicate IDs;
- heading-level skips;
- focusable elements inside `aria-hidden="true"`;
- positive `tabindex` values.

The report contains rule IDs, severity-like impact labels, short explanations, and bounded DOM selectors. It deliberately does not return page text, form values, or screenshots. The report is capped at 100 issues and marked `heuristic_not_wcag_certification`.

These checks are only an initial automated screen. They do not cover the complete WCAG criteria, colour contrast, keyboard interaction, screen-reader behaviour, reflow, zoom, or all ARIA semantics. Run them against a controlled test page, then perform keyboard, screen-reader, contrast, and human review. Keep browser navigation behind the configured hostname allow-list and network egress controls.
