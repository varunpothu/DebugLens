"""Browser evidence capture with explicit host allow-list and non-mutating navigation.

Run this only in a disposable worker with network egress controls. Host allow-lists are an
application guard, not a replacement for network-level SSRF protection.
"""
from __future__ import annotations

import ipaddress
from typing import Any
from dataclasses import dataclass
from urllib.parse import urlparse


class UnsafeTargetError(ValueError):
    """Raised when a browser target or subresource is outside the approved scope."""


@dataclass(frozen=True, slots=True)
class BrowserCaptureResult:
    final_url: str
    page_title: str
    viewport_width: int
    viewport_height: int
    screenshot_png: bytes
    dom_tag_counts: dict[str, int]
    console_errors: list[str]
    page_errors: list[str]
    failed_request_count: int


def validate_target_url(url: str, allowed_hosts: set[str]) -> str:
    """Return the normalised hostname only if the URL is explicitly allow-listed."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeTargetError("Target must be an absolute HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise UnsafeTargetError("Credentials in target URLs are not permitted.")
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        if not address.is_global:
            raise UnsafeTargetError("Private, loopback, and non-global IP targets are blocked.")
        raise UnsafeTargetError("Use an explicitly allow-listed DNS hostname, not an IP address.")
    allowed = {host.rstrip(".").lower() for host in allowed_hosts}
    if hostname not in allowed:
        raise UnsafeTargetError("Target hostname is not in the approved allow-list.")
    return hostname


async def capture_page(
    url: str,
    *,
    allowed_hosts: set[str],
    viewport: tuple[int, int] = (1440, 900),
    timeout_ms: int = 15000,
) -> BrowserCaptureResult:
    """Capture visual and limited runtime evidence without saving raw DOM text or request URLs."""
    validate_target_url(url, allowed_hosts)
    if not (320 <= viewport[0] <= 3840 and 320 <= viewport[1] <= 2160):
        raise ValueError("Viewport is outside the supported safety bounds.")
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Install the optional browser dependencies and Playwright browser.") from exc

    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[bool] = []
    allowed = {host.rstrip(".").lower() for host in allowed_hosts}

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                accept_downloads=False,
                service_workers="block",
            )
            page = await context.new_page()
            page.set_default_timeout(timeout_ms)

            async def guard_request(route: Any, request: Any) -> None:
                try:
                    validate_target_url(request.url, allowed)
                    if request.method not in {"GET", "HEAD"}:
                        await route.abort("blockedbyclient")
                        return
                    await route.continue_()
                except UnsafeTargetError:
                    await route.abort("blockedbyclient")

            await page.route("**/*", guard_request)
            page.on("console", lambda message: console_errors.append(message.type) if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(type(error).__name__))
            page.on("requestfailed", lambda request: failed_requests.append(True))
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(250)
            screenshot = await page.screenshot(type="png", full_page=True)
            summary = await page.locator("body").evaluate(
                """body => {
                    const counts = {};
                    for (const element of body.querySelectorAll('*')) {
                        const tag = element.tagName.toLowerCase();
                        counts[tag] = (counts[tag] || 0) + 1;
                    }
                    return counts;
                }"""
            )
            return BrowserCaptureResult(
                final_url=page.url.split("?")[0].split("#")[0],
                page_title=(await page.title())[:300],
                viewport_width=viewport[0],
                viewport_height=viewport[1],
                screenshot_png=screenshot,
                dom_tag_counts={str(k): int(v) for k, v in summary.items()},
                console_errors=console_errors[:100],
                page_errors=page_errors[:100],
                failed_request_count=len(failed_requests),
            )
        finally:
            await browser.close()
