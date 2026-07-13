"""Loopback-only browser UI for blinded human calibration review."""

from __future__ import annotations

import hmac
import json
import os
import secrets
import tempfile
import threading
import webbrowser
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from codepulse.eval.calibration_review import (
    FUNCTIONAL_LABELS,
    load_jsonl,
    validate_review_packets,
    validate_review_responses,
    write_jsonl,
)

STANDARD_RATIONALES = {
    "supported_pass": "退出码为 0，且官方测试摘要显示全部通过。",
    "supported_fail": "官方验证显示测试失败、报错或未完整执行。",
    "insufficient_evidence": "官方验证结果缺失，或退出码与测试摘要相互矛盾。",
}
_IMMUTABLE_RESPONSE_KEYS = (
    "packet_id",
    "round",
    "rubric_version",
    "packet_sha256",
)
_MAX_REQUEST_BYTES = 64 * 1024


@dataclass
class ReviewSession:
    """Validated in-memory review state backed by an atomic JSONL file."""

    packets: list[dict[str, Any]]
    responses: list[dict[str, Any]]
    response_path: Path
    _packet_by_id: dict[str, dict[str, Any]] = field(init=False, repr=False)
    _response_index_by_id: dict[str, int] = field(init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        errors = _validate_partial_responses(self.packets, self.responses)
        if errors:
            raise ValueError("invalid review responses: " + "; ".join(errors))
        self._packet_by_id = {
            str(packet["packet_id"]): packet for packet in self.packets
        }
        self._response_index_by_id = {
            str(response["packet_id"]): index
            for index, response in enumerate(self.responses)
        }

    @classmethod
    def from_files(cls, packet_path: str | Path, response_path: str | Path) -> ReviewSession:
        """Load a packet set and its pristine or partially completed response file."""
        responses = Path(response_path)
        return cls(
            packets=load_jsonl(Path(packet_path)),
            responses=load_jsonl(responses),
            response_path=responses,
        )

    def state(self, index: int | None = None) -> dict[str, Any]:
        """Return browser-safe state at an explicit or resumable packet position."""
        with self._lock:
            return self._state_unlocked(index)

    def save(self, packet_id: str, label: str, rationale: str) -> dict[str, Any]:
        """Persist one explicit human choice and return the next resumable state."""
        with self._lock:
            response_index = self._response_index_by_id.get(packet_id)
            if response_index is None:
                raise ValueError(f"unknown packet: {packet_id}")
            if label not in FUNCTIONAL_LABELS:
                raise ValueError(f"invalid label: {label}")
            rationale = rationale.strip()
            if not rationale:
                raise ValueError("rationale is required")

            response = self.responses[response_index]
            previous = {
                key: response.get(key) for key in ("label", "rationale", "reviewed_at")
            }
            response["label"] = label
            response["rationale"] = rationale
            response["reviewed_at"] = (
                datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
            )
            try:
                _atomic_write_jsonl(self.response_path, self.responses)
            except OSError:
                response.update(previous)
                raise
            return self._state_unlocked(None)

    def _state_unlocked(self, index: int | None) -> dict[str, Any]:
        completed = sum(_is_complete(response) for response in self.responses)
        complete = completed == len(self.packets)
        if index is None:
            index = next(
                (
                    packet_index
                    for packet_index, packet in enumerate(self.packets)
                    if not _is_complete(
                        self.responses[
                            self._response_index_by_id[str(packet["packet_id"])]
                        ]
                    )
                ),
                max(len(self.packets) - 1, 0),
            )
        if not 0 <= index < len(self.packets):
            raise ValueError(f"packet index out of range: {index}")

        packet = self.packets[index]
        response = self.responses[
            self._response_index_by_id[str(packet["packet_id"])]
        ]
        errors = (
            validate_review_responses(self.packets, self.responses) if complete else []
        )
        return {
            "index": index,
            "total": len(self.packets),
            "completed": completed,
            "complete": complete,
            "valid": complete and not errors,
            "errors": errors,
            "packet": {
                "packet_id": packet["packet_id"],
                "round": packet["round"],
                "task_id": packet["task_id"],
                "evidence": packet["evidence"],
            },
            "response": {
                "label": response.get("label"),
                "rationale": response.get("rationale"),
                "reviewed_at": response.get("reviewed_at"),
            },
            "standard_rationales": STANDARD_RATIONALES,
        }


def run_review_server(packet_path: str | Path, response_path: str | Path) -> None:
    """Open and serve the local review UI until interrupted."""
    session = ReviewSession.from_files(packet_path, response_path)
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _handler_for(session, token),
    )
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}/?{urlencode({'token': token})}"
    print(f"Review UI: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReview UI stopped. Progress is saved.")
    finally:
        server.server_close()


def _validate_partial_responses(
    packets: list[dict[str, Any]], responses: list[dict[str, Any]]
) -> list[str]:
    errors = validate_review_packets(packets)
    packet_by_id = {str(packet["packet_id"]): packet for packet in packets}
    response_ids = [str(response.get("packet_id", "")) for response in responses]
    if Counter(response_ids) != Counter(packet_by_id.keys()):
        errors.append("response coverage does not match review packets")

    for response in responses:
        packet_id = str(response.get("packet_id", ""))
        packet = packet_by_id.get(packet_id)
        if packet is None:
            continue
        for key in _IMMUTABLE_RESPONSE_KEYS:
            if response.get(key) != packet.get(key):
                errors.append(f"response {packet_id} {key} mismatch")
        if not _nonempty_string(response.get("reviewer_id")):
            errors.append(f"response {packet_id} requires reviewer_id")

        fields = (
            response.get("label"),
            response.get("rationale"),
            response.get("reviewed_at"),
        )
        if fields == (None, None, None):
            continue
        if any(value is None for value in fields):
            errors.append(f"response {packet_id} is a partial response")
            continue
        if response.get("label") not in FUNCTIONAL_LABELS:
            errors.append(f"response {packet_id} has invalid label")
        if not _nonempty_string(response.get("rationale")):
            errors.append(f"response {packet_id} requires rationale")
        if not _nonempty_string(response.get("reviewed_at")):
            errors.append(f"response {packet_id} requires reviewed_at")
    return errors


def _atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        write_jsonl(temporary, rows)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _is_complete(response: dict[str, Any]) -> bool:
    return (
        response.get("label") in FUNCTIONAL_LABELS
        and _nonempty_string(response.get("rationale"))
        and _nonempty_string(response.get("reviewed_at"))
    )


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _handler_for(
    session: ReviewSession, token: str
) -> type[BaseHTTPRequestHandler]:
    class ReviewRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not self._authorized(parsed.query):
                self._json(HTTPStatus.FORBIDDEN, {"error": "invalid session token"})
                return
            if parsed.path == "/":
                self._html(_REVIEW_PAGE)
                return
            if parsed.path != "/api/state":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                values = parse_qs(parsed.query).get("index")
                index = int(values[0]) if values else None
                self._json(HTTPStatus.OK, session.state(index))
            except (TypeError, ValueError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not self._authorized(parsed.query):
                self._json(HTTPStatus.FORBIDDEN, {"error": "invalid session token"})
                return
            if parsed.path != "/api/review":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= _MAX_REQUEST_BYTES:
                    raise ValueError("invalid request size")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be an object")
                packet_id = payload.get("packet_id")
                label = payload.get("label")
                rationale = payload.get("rationale")
                if (
                    not isinstance(packet_id, str)
                    or not isinstance(label, str)
                    or not isinstance(rationale, str)
                ):
                    raise ValueError("packet_id, label, and rationale must be strings")
                self._json(
                    HTTPStatus.OK,
                    session.save(packet_id, label, rationale),
                )
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _authorized(self, query: str) -> bool:
            return _valid_token(query, token)

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self._headers("application/json; charset=utf-8", len(body))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, content: str) -> None:
            body = content.encode()
            self.send_response(HTTPStatus.OK)
            self._headers("text/html; charset=utf-8", len(body))
            self.end_headers()
            self.wfile.write(body)

        def _headers(self, content_type: str, length: int) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'",
            )

    return ReviewRequestHandler


def _valid_token(query: str, expected: str) -> bool:
    supplied = parse_qs(query).get("token", [""])[0]
    return hmac.compare_digest(supplied, expected)


_REVIEW_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Phase 2 人工校准</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #18201d; background: #f7f8f5; }
    button, textarea { font: inherit; }
    header { height: 70px; padding: 0 32px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #d8ddd9; background: #fff; }
    h1 { font-size: 18px; margin: 0; letter-spacing: 0; }
    .progress { display: flex; gap: 14px; align-items: center; color: #56625c; font-size: 14px; }
    .bar { width: 160px; height: 6px; background: #e3e7e3; overflow: hidden; }
    .bar span { display: block; height: 100%; background: #16794b; }
    main { max-width: 1180px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(330px, .8fr); min-height: calc(100vh - 70px); }
    section, aside { padding: 34px 38px 44px; min-width: 0; }
    aside { border-left: 1px solid #d8ddd9; background: #fff; }
    .eyebrow { margin: 0 0 6px; color: #68736d; font-size: 12px; text-transform: uppercase; }
    h2 { font-size: 22px; margin: 0 0 24px; letter-spacing: 0; }
    .facts { display: grid; grid-template-columns: repeat(3, 1fr); border-top: 1px solid #d8ddd9; border-bottom: 1px solid #d8ddd9; margin-bottom: 24px; }
    .fact { padding: 15px 10px 15px 0; }
    .fact + .fact { border-left: 1px solid #d8ddd9; padding-left: 18px; }
    .fact span { display: block; color: #68736d; font-size: 12px; margin-bottom: 5px; }
    .fact strong { font-size: 15px; font-weight: 650; }
    .label { font-size: 12px; color: #68736d; margin: 20px 0 8px; }
    pre { margin: 0; padding: 18px; min-height: 200px; max-height: 48vh; overflow: auto; background: #1d2421; color: #edf2ee; border-radius: 4px; font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; word-break: break-word; }
    .stderr { min-height: 56px; max-height: 120px; background: #332321; }
    .choice { width: 100%; text-align: left; border: 1px solid #cbd2cd; background: #fff; padding: 14px; margin-bottom: 10px; border-radius: 4px; cursor: pointer; }
    .choice:hover, .choice:focus-visible { border-color: #16794b; outline: 2px solid #bfe3ce; outline-offset: 1px; }
    .choice strong { display: block; font-size: 14px; margin-bottom: 4px; }
    .choice span { display: block; color: #5d6862; font-size: 12px; line-height: 1.45; }
    .choice.pass strong { color: #12653f; }
    .choice.fail strong { color: #a1322d; }
    .choice.insufficient strong { color: #8a5a05; }
    textarea { width: 100%; resize: vertical; min-height: 86px; border: 1px solid #cbd2cd; border-radius: 4px; padding: 11px; color: #18201d; background: #fff; }
    textarea:focus { border-color: #16794b; outline: 2px solid #bfe3ce; }
    .nav { display: flex; justify-content: space-between; margin-top: 22px; }
    .icon { width: 38px; height: 38px; border: 1px solid #cbd2cd; background: #fff; border-radius: 4px; cursor: pointer; font-size: 19px; }
    .icon:disabled, .choice:disabled { opacity: .45; cursor: default; }
    .message { margin: 0 0 18px; padding: 11px 12px; border-left: 3px solid #16794b; background: #edf7f1; font-size: 13px; line-height: 1.45; }
    .message.error { border-color: #a1322d; background: #fbefee; }
    .hidden { display: none; }
    @media (max-width: 820px) {
      header { padding: 0 18px; }
      .bar { width: 90px; }
      main { grid-template-columns: 1fr; }
      section, aside { padding: 26px 20px 34px; }
      aside { border-left: 0; border-top: 1px solid #d8ddd9; }
      .facts { grid-template-columns: 1fr; }
      .fact + .fact { border-left: 0; border-top: 1px solid #d8ddd9; padding-left: 0; }
    }
    @media (max-width: 360px) { .bar { display: none; } }
  </style>
</head>
<body>
  <header>
    <h1>Phase 2 人工校准</h1>
    <div class="progress"><div class="bar"><span id="bar"></span></div><strong id="progress"></strong></div>
  </header>
  <main>
    <section>
      <p class="eyebrow" id="round"></p>
      <h2 id="task"></h2>
      <div class="facts">
        <div class="fact"><span>退出码</span><strong id="exitCode"></strong></div>
        <div class="fact"><span>材料状态</span><strong id="artifactStatus"></strong></div>
        <div class="fact"><span>已审核</span><strong id="reviewedAt"></strong></div>
      </div>
      <p class="label">标准输出</p>
      <pre id="stdout"></pre>
      <p class="label">错误输出</p>
      <pre class="stderr" id="stderr"></pre>
    </section>
    <aside>
      <div id="message" class="message hidden"></div>
      <p class="eyebrow">你的结论</p>
      <h2>证据支持什么？</h2>
      <button class="choice pass" data-label="supported_pass"><strong>支持通过</strong><span></span></button>
      <button class="choice fail" data-label="supported_fail"><strong>支持失败</strong><span></span></button>
      <button class="choice insufficient" data-label="insufficient_evidence"><strong>证据不足</strong><span></span></button>
      <p class="label">自定义理由（可选）</p>
      <textarea id="customRationale" aria-label="自定义理由"></textarea>
      <div class="nav">
        <button class="icon" id="previous" title="上一条" aria-label="上一条">&larr;</button>
        <button class="icon" id="next" title="下一条" aria-label="下一条">&rarr;</button>
      </div>
    </aside>
  </main>
  <script>
    const token = new URLSearchParams(location.search).get("token") || "";
    const buttons = [...document.querySelectorAll(".choice")];
    let state = null;

    async function request(path, options = {}) {
      const joiner = path.includes("?") ? "&" : "?";
      const response = await fetch(`${path}${joiner}token=${encodeURIComponent(token)}`, options);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "请求失败");
      return payload;
    }

    function text(id, value, empty = "无") {
      document.getElementById(id).textContent = value === null || value === undefined || value === "" ? empty : String(value);
    }

    function render(nextState) {
      state = nextState;
      const packet = state.packet;
      const verification = packet.evidence.verification || {};
      const percent = state.total ? (state.completed / state.total) * 100 : 0;
      document.getElementById("bar").style.width = `${percent}%`;
      text("progress", `${state.completed} / ${state.total}`);
      text("round", `第 ${packet.round} 轮 · 第 ${state.index + 1} 条`);
      text("task", packet.task_id);
      text("exitCode", verification.exit_code);
      const artifactLabels = {
        missing_final_code_and_full_transcript: "仅含功能验证材料",
      };
      text("artifactStatus", artifactLabels[packet.evidence.artifact_status] || "功能验证材料");
      text("reviewedAt", state.response.reviewed_at, "未审核");
      text("stdout", verification.stdout);
      text("stderr", verification.stderr);
      buttons.forEach((button) => {
        const label = button.dataset.label;
        button.querySelector("span").textContent = state.standard_rationales[label];
        button.disabled = false;
      });
      const standards = Object.values(state.standard_rationales);
      document.getElementById("customRationale").value =
        state.response.rationale && !standards.includes(state.response.rationale)
          ? state.response.rationale
          : "";
      document.getElementById("previous").disabled = state.index === 0;
      document.getElementById("next").disabled = state.index === state.total - 1;
      const message = document.getElementById("message");
      message.classList.add("hidden");
      message.classList.remove("error");
      if (state.complete) {
        message.textContent = state.valid ? "本轮审核完成，校验通过。" : state.errors.join("；");
        message.classList.remove("hidden");
        if (!state.valid) message.classList.add("error");
      }
    }

    async function load(index = null) {
      const path = index === null ? "/api/state" : `/api/state?index=${index}`;
      try { render(await request(path)); }
      catch (error) { showError(error); }
    }

    async function submit(label) {
      if (!state) return;
      buttons.forEach((button) => button.disabled = true);
      const custom = document.getElementById("customRationale").value.trim();
      const rationale = custom || state.standard_rationales[label];
      try {
        render(await request("/api/review", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({packet_id: state.packet.packet_id, label, rationale}),
        }));
      } catch (error) {
        buttons.forEach((button) => button.disabled = false);
        showError(error);
      }
    }

    function showError(error) {
      const message = document.getElementById("message");
      message.textContent = error instanceof Error ? error.message : String(error);
      message.classList.remove("hidden");
      message.classList.add("error");
    }

    buttons.forEach((button) => button.addEventListener("click", () => submit(button.dataset.label)));
    document.getElementById("previous").addEventListener("click", () => load(state.index - 1));
    document.getElementById("next").addEventListener("click", () => load(state.index + 1));
    document.addEventListener("keydown", (event) => {
      if (["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
      const labels = {"1": "supported_pass", "2": "supported_fail", "3": "insufficient_evidence"};
      if (labels[event.key]) submit(labels[event.key]);
      if (event.key === "ArrowLeft" && state.index > 0) load(state.index - 1);
      if (event.key === "ArrowRight" && state.index < state.total - 1) load(state.index + 1);
    });
    load();
  </script>
</body>
</html>
"""
