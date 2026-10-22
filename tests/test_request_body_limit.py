import asyncio

from app.request_body_limit import RequestBodyLimitMiddleware


def run_middleware(chunks: list[bytes], max_bytes: int = 5) -> tuple[int, bytes, bytes | None]:
    messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    sent: list[dict] = []
    downstream_body: list[bytes] = []

    async def receive() -> dict:
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    async def downstream(scope: dict, inner_receive, inner_send) -> None:
        message = await inner_receive()
        downstream_body.append(message.get("body", b""))
        await inner_send({"type": "http.response.start", "status": 200, "headers": []})
        await inner_send({"type": "http.response.body", "body": b"ok", "more_body": False})

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/analyses",
        "raw_path": b"/v1/analyses",
        "query_string": b"",
        "headers": [(b"x-correlation-id", b"safe-id")],
        "server": ("test", 80),
        "client": ("127.0.0.1", 12345),
    }
    middleware = RequestBodyLimitMiddleware(downstream, max_bytes=max_bytes)
    asyncio.run(middleware(scope, receive, send))
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    response_body = next(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    delivered_body = downstream_body[0] if downstream_body else None
    return status, response_body, delivered_body


def test_chunked_body_without_content_length_is_replayed_within_limit() -> None:
    status, response_body, delivered = run_middleware([b"abc", b"de"], max_bytes=5)
    assert status == 200
    assert response_body == b"ok"
    assert delivered == b"abcde"


def test_chunked_body_over_limit_is_rejected_before_route() -> None:
    status, response_body, delivered = run_middleware([b"abc", b"def"], max_bytes=5)
    assert status == 413
    assert b"configured limit" in response_body
    assert delivered is None


def test_declared_oversized_body_is_rejected_without_reading_body() -> None:
    async def scenario() -> tuple[int, bool]:
        called = False
        sent: list[dict] = []

        async def receive() -> dict:
            nonlocal called
            called = True
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            sent.append(message)

        async def downstream(scope: dict, inner_receive, inner_send) -> None:
            raise AssertionError("downstream must not run for an oversized declared body")

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/analyses",
            "raw_path": b"/v1/analyses",
            "query_string": b"",
            "headers": [(b"content-length", b"6")],
            "server": ("test", 80),
            "client": ("127.0.0.1", 12345),
        }
        await RequestBodyLimitMiddleware(downstream, max_bytes=5)(scope, receive, send)
        status = next(message["status"] for message in sent if message["type"] == "http.response.start")
        return status, called

    status, receive_called = asyncio.run(scenario())
    assert status == 413
    assert receive_called is False
