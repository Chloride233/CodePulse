"""Loopback-only browser UI for blinded qualitative diagnostic review."""

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

from codepulse.eval.artifacts import load_jsonl, write_jsonl
from codepulse.eval.calibration_diagnostic import (
    validate_diagnostic_packets,
    validate_diagnostic_responses,
)

_IMMUTABLE_RESPONSE_KEYS = (
    "packet_id",
    "round",
    "rubric_version",
    "packet_sha256",
)
_MAX_REQUEST_BYTES = 64 * 1024


@dataclass
class DiagnosticReviewSession:
    """Validated diagnostic review state backed by an atomic JSONL file."""

    packets: list[dict[str, Any]]
    responses: list[dict[str, Any]]
    response_path: Path
    _response_index_by_id: dict[str, int] = field(init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        errors = _validate_partial_responses(self.packets, self.responses)
        if errors:
            raise ValueError("invalid diagnostic responses: " + "; ".join(errors))
        self._response_index_by_id = {
            str(response["packet_id"]): index
            for index, response in enumerate(self.responses)
        }

    @classmethod
    def from_files(
        cls, packet_path: str | Path, response_path: str | Path
    ) -> DiagnosticReviewSession:
        """Load one blind round and its pristine or partially completed responses."""
        response_file = Path(response_path)
        return cls(
            packets=load_jsonl(Path(packet_path)),
            responses=load_jsonl(response_file),
            response_path=response_file,
        )

    def state(self, index: int | None = None) -> dict[str, Any]:
        """Return browser-safe state at an explicit or resumable packet position."""
        with self._lock:
            return self._state_unlocked(index)

    def save(self, packet_id: str, score: object, rationale: str) -> dict[str, Any]:
        """Persist one explicit human score and return the next resumable state."""
        with self._lock:
            response_index = self._response_index_by_id.get(packet_id)
            if response_index is None:
                raise ValueError(f"unknown packet: {packet_id}")
            if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
                raise ValueError("invalid score: expected an integer from 1 to 5")
            rationale = rationale.strip()
            if not rationale:
                raise ValueError("rationale is required")

            response = self.responses[response_index]
            previous = {
                key: response.get(key) for key in ("score", "rationale", "reviewed_at")
            }
            response["score"] = score
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
            validate_diagnostic_responses(self.packets, self.responses)
            if complete
            else []
        )
        return {
            "index": index,
            "total": len(self.packets),
            "completed": completed,
            "complete": complete,
            "valid": complete and not errors,
            "errors": errors,
            "packet": packet,
            "response": {
                "score": response.get("score"),
                "rationale": response.get("rationale"),
                "reviewed_at": response.get("reviewed_at"),
            },
        }


def create_diagnostic_review_server(
    packet_path: str | Path, response_path: str | Path
) -> tuple[ThreadingHTTPServer, str]:
    """Create a token-protected loopback server and return its browser URL."""
    session = DiagnosticReviewSession.from_files(packet_path, response_path)
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _handler_for(session, token),
    )
    port = int(server.server_address[1])
    return server, f"http://127.0.0.1:{port}/?{urlencode({'token': token})}"


def run_diagnostic_review_server(
    packet_path: str | Path, response_path: str | Path
) -> None:
    """Open and serve one local diagnostic review round until interrupted."""
    server, url = create_diagnostic_review_server(packet_path, response_path)
    print(f"Diagnostic review UI: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDiagnostic review UI stopped. Progress is saved.")
    finally:
        server.server_close()


def _validate_partial_responses(
    packets: list[dict[str, Any]], responses: list[dict[str, Any]]
) -> list[str]:
    errors = validate_diagnostic_packets(packets)
    packet_by_id = {str(packet["packet_id"]): packet for packet in packets}
    response_ids = [str(response.get("packet_id", "")) for response in responses]
    if Counter(response_ids) != Counter(packet_by_id.keys()):
        errors.append("response coverage does not match diagnostic packets")

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
            response.get("score"),
            response.get("rationale"),
            response.get("reviewed_at"),
        )
        if fields == (None, None, None):
            continue
        if any(value is None for value in fields):
            errors.append(f"response {packet_id} is a partial response")
            continue
        score = response.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            errors.append(f"response {packet_id} has invalid score")
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
    score = response.get("score")
    return (
        isinstance(score, int)
        and not isinstance(score, bool)
        and 1 <= score <= 5
        and _nonempty_string(response.get("rationale"))
        and _nonempty_string(response.get("reviewed_at"))
    )


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _handler_for(
    session: DiagnosticReviewSession, token: str
) -> type[BaseHTTPRequestHandler]:
    class DiagnosticReviewRequestHandler(BaseHTTPRequestHandler):
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
                rationale = payload.get("rationale")
                if not isinstance(packet_id, str) or not isinstance(rationale, str):
                    raise ValueError("packet_id and rationale must be strings")
                self._json(
                    HTTPStatus.OK,
                    session.save(packet_id, payload.get("score"), rationale),
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
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                "style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )

    return DiagnosticReviewRequestHandler


def _valid_token(query: str, expected: str) -> bool:
    supplied = parse_qs(query).get("token", [""])[0]
    return hmac.compare_digest(supplied, expected)


_REVIEW_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Phase 2 定性盲审</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #17201c; background: #f4f6f5; }
    button, textarea { font: inherit; }
    header { min-height: 68px; padding: 14px 28px; display: flex; gap: 24px; align-items: center; justify-content: space-between; border-bottom: 1px solid #d5dcda; background: #fff; position: sticky; top: 0; z-index: 10; }
    h1 { font-size: 18px; margin: 0; letter-spacing: 0; }
    .progress { display: flex; gap: 12px; align-items: center; color: #596660; font-size: 13px; }
    .bar { width: 150px; height: 6px; background: #e1e6e4; overflow: hidden; }
    .bar span { display: block; height: 100%; background: #08775a; transition: width 180ms ease; }
    main { width: min(1500px, 100%); margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1fr) 390px; align-items: start; }
    .evidence { min-width: 0; padding: 30px 34px 60px; }
    .review { min-width: 0; min-height: calc(100vh - 68px); padding: 30px 28px 44px; border-left: 1px solid #d5dcda; background: #fff; position: sticky; top: 68px; }
    .eyebrow { margin: 0 0 7px; color: #69766f; font-size: 12px; text-transform: uppercase; }
    h2 { font-size: 22px; margin: 0 0 18px; letter-spacing: 0; overflow-wrap: anywhere; }
    h3 { font-size: 14px; margin: 0 0 10px; }
    .summary { margin: 0 0 20px; color: #405049; font-size: 15px; }
    .band { padding: 22px 0 26px; border-top: 1px solid #d5dcda; }
    .facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 4px 0 0; border-top: 1px solid #d5dcda; border-bottom: 1px solid #d5dcda; }
    .fact { padding: 13px 12px 13px 0; min-width: 0; }
    .fact + .fact { border-left: 1px solid #d5dcda; padding-left: 14px; }
    .fact span { display: block; color: #69766f; font-size: 11px; margin-bottom: 4px; }
    .fact strong { display: block; font-size: 14px; overflow-wrap: anywhere; }
    p { line-height: 1.65; }
    pre { margin: 0; padding: 16px; overflow: auto; background: #1d2622; color: #edf4f0; border-radius: 4px; font: 12px/1.58 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
    .code { max-height: 420px; }
    .verification { background: #252a35; max-height: 280px; }
    .timeline { display: grid; gap: 0; margin: 6px 0 28px; border-top: 1px solid #d5dcda; }
    .timeline-item { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 10px; padding: 13px 0; border-bottom: 1px solid #d5dcda; }
    .timeline-index { width: 26px; height: 26px; display: grid; place-items: center; border-radius: 50%; background: #dce9e4; color: #245b48; font-size: 11px; font-weight: 700; }
    .timeline-item strong { display: block; font-size: 14px; margin-bottom: 3px; }
    .timeline-item span { display: block; color: #637069; font-size: 12px; overflow-wrap: anywhere; }
    details { border-top: 1px solid #bbc6c1; border-bottom: 1px solid #bbc6c1; }
    summary { padding: 15px 2px; cursor: pointer; color: #34443d; font-weight: 700; }
    .details-body { padding: 0 0 12px; }
    .trace { display: grid; gap: 10px; }
    .event { border-left: 3px solid #8ca49a; padding: 12px 14px; background: #fff; }
    .event-head { display: flex; gap: 10px; justify-content: space-between; margin-bottom: 7px; color: #55635d; font-size: 11px; }
    .event pre { background: #edf1ef; color: #26312c; max-height: 320px; }
    .score-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border: 1px solid #c8d1cd; border-radius: 5px; overflow: hidden; }
    .score-option { min-width: 0; height: 58px; border: 0; border-left: 1px solid #c8d1cd; background: #fff; color: #26332d; cursor: pointer; }
    .score-option strong, .score-option span { display: block; }
    .score-option strong { font-size: 15px; }
    .score-option span { margin-top: 2px; font-size: 10px; font-weight: 500; }
    .score-option:first-child { border-left: 0; }
    .score-option:hover, .score-option:focus-visible { background: #e8f3ef; outline: 2px solid #08775a; outline-offset: -2px; }
    .score-option[aria-pressed="true"] { background: #08775a; color: #fff; }
    .rubric { min-height: 66px; margin: 12px 0 20px; color: #4d5c55; font-size: 13px; }
    .reason-list { display: grid; gap: 8px; margin-bottom: 18px; }
    .reason-option { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 9px; align-items: start; margin: 0; padding: 9px 10px; border: 1px solid #d5dcda; border-radius: 4px; color: #34443d; cursor: pointer; }
    .reason-option:hover { border-color: #7e9e91; background: #f2f7f5; }
    .reason-option input { width: 16px; height: 16px; margin: 2px 0 0; accent-color: #08775a; }
    .reason-option span { font-size: 12px; line-height: 1.45; }
    label { display: block; margin: 0 0 8px; color: #596660; font-size: 12px; }
    textarea { width: 100%; min-height: 116px; resize: vertical; border: 1px solid #c8d1cd; border-radius: 4px; padding: 11px 12px; color: #17201c; background: #fff; }
    textarea:focus { border-color: #08775a; outline: 2px solid #b9ded2; }
    .save { width: 100%; min-height: 44px; margin-top: 14px; border: 1px solid #075d48; border-radius: 4px; background: #08775a; color: #fff; font-weight: 700; cursor: pointer; }
    .save:hover, .save:focus-visible { background: #06664d; outline: 2px solid #b9ded2; outline-offset: 2px; }
    .save:disabled { opacity: .42; cursor: default; }
    .nav { display: flex; justify-content: space-between; margin-top: 20px; }
    .icon { width: 40px; height: 40px; border: 1px solid #c8d1cd; background: #fff; border-radius: 4px; cursor: pointer; font-size: 19px; }
    .icon:disabled { opacity: .4; cursor: default; }
    .message { margin: 0 0 18px; padding: 11px 12px; border-left: 3px solid #08775a; background: #eaf5f1; font-size: 13px; line-height: 1.45; }
    .message.error { border-color: #ae3d36; background: #f9eceb; }
    .hidden { display: none; }
    @media (max-width: 920px) {
      header { padding: 13px 18px; }
      .bar { width: 90px; }
      main { grid-template-columns: 1fr; }
      .evidence, .review { padding: 24px 20px 36px; }
      .review { min-height: 0; border-left: 0; border-top: 1px solid #d5dcda; position: static; }
      .facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .fact:nth-child(3) { border-left: 0; }
      .fact:nth-child(n+3) { border-top: 1px solid #d5dcda; }
    }
    @media (max-width: 480px) {
      header { align-items: flex-start; }
      .bar { display: none; }
      .facts { grid-template-columns: 1fr; }
      .fact + .fact { border-left: 0; border-top: 1px solid #d5dcda; padding-left: 0; }
      .score-option { height: 44px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Phase 2 定性盲审</h1>
    <div class="progress"><div class="bar"><span id="bar"></span></div><strong id="progress"></strong></div>
  </header>
  <main>
    <section class="evidence">
      <p class="eyebrow" id="round"></p>
      <h2>过程摘要</h2>
      <p class="summary" id="plainSummary"></p>
      <div class="facts">
        <div class="fact"><span>写代码</span><strong id="codeWrites"></strong></div>
        <div class="fact"><span>运行命令</span><strong id="testRuns"></strong></div>
        <div class="fact"><span>失败事件</span><strong id="observedFailures"></strong></div>
        <div class="fact"><span>最终测试</span><strong id="finalTests"></strong></div>
      </div>
      <div class="band">
        <h3>过程时间线</h3>
        <div class="timeline" id="plainTimeline"></div>
      </div>
      <details id="detailedEvidence">
        <summary>查看详细证据</summary>
        <div class="details-body">
          <div class="band">
            <h3>任务说明</h3>
            <p id="taskDescription"></p>
            <pre class="code" id="taskCode"></pre>
          </div>
          <div class="band">
            <h3>最终代码</h3>
            <pre class="code" id="finalCode"></pre>
          </div>
          <div class="band">
            <h3>原始 Trace</h3>
            <div class="trace" id="rawTraceEvents"></div>
          </div>
          <div class="band">
            <h3>官方验证与指标</h3>
            <pre class="verification" id="verification"></pre>
          </div>
        </div>
      </details>
    </section>
    <aside class="review">
      <div id="message" class="message hidden"></div>
      <p class="eyebrow">过程质量</p>
      <h2>评分</h2>
      <div class="score-grid" role="group" aria-label="过程质量评分">
        <button class="score-option" data-score="1" aria-pressed="false"><strong>1</strong><span>不可靠</span></button>
        <button class="score-option" data-score="2" aria-pressed="false"><strong>2</strong><span>较差</span></button>
        <button class="score-option" data-score="3" aria-pressed="false"><strong>3</strong><span>一般</span></button>
        <button class="score-option" data-score="4" aria-pressed="false"><strong>4</strong><span>可靠</span></button>
        <button class="score-option" data-score="5" aria-pressed="false"><strong>5</strong><span>很好</span></button>
      </div>
      <p class="rubric" id="rubric"></p>
      <label>符合的事实</label>
      <div class="reason-list">
        <label class="reason-option"><input type="checkbox" value="步骤直接，没有重复尝试。"><span>步骤直接，没有重复尝试</span></label>
        <label class="reason-option"><input type="checkbox" value="有少量可避免的步骤。"><span>有少量可避免的步骤</span></label>
        <label class="reason-option"><input type="checkbox" value="失败后进行了有效修复。"><span>失败后进行了有效修复</span></label>
        <label class="reason-option"><input type="checkbox" value="失败后的恢复不足。"><span>失败后的恢复不足</span></label>
        <label class="reason-option"><input type="checkbox" value="出现了重复或相似尝试。"><span>出现了重复或相似尝试</span></label>
        <label class="reason-option"><input type="checkbox" value="最终代码与官方验证一致。"><span>最终代码与官方验证一致</span></label>
        <label class="reason-option"><input type="checkbox" value="关键过程证据不足。"><span>关键过程证据不足</span></label>
      </div>
      <label for="customNote">补充（可选）</label>
      <textarea id="customNote"></textarea>
      <button class="save" id="save" disabled>保存并继续</button>
      <div class="nav">
        <button class="icon" id="previous" title="上一条" aria-label="上一条">&larr;</button>
        <button class="icon" id="next" title="下一条" aria-label="下一条">&rarr;</button>
      </div>
    </aside>
  </main>
  <script>
    const token = new URLSearchParams(location.search).get("token") || "";
    const scoreButtons = [...document.querySelectorAll(".score-option")];
    const reasonInputs = [...document.querySelectorAll(".reason-option input")];
    const reasonValues = reasonInputs.map((input) => input.value);
    const rubric = {
      1: "过程缺失、根本不可靠，或没有被最终产物与验证支持。",
      2: "存在重大缺口、重复无效工作，或失败后的恢复明显不足。",
      3: "结果可接受，但推理、工具使用或恢复过程存在实质性弱点。",
      4: "整体可靠，仅有少量可避免步骤或清晰度不足。",
      5: "过程可靠、直接，并被最终产物与验证充分支持。",
    };
    let state = null;
    let selectedScore = null;

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

    function renderRawTrace(events) {
      const container = document.getElementById("rawTraceEvents");
      container.replaceChildren();
      events.forEach((event, index) => {
        const article = document.createElement("article");
        article.className = "event";
        const heading = document.createElement("div");
        heading.className = "event-head";
        const type = document.createElement("strong");
        type.textContent = event.event_type || "event";
        const number = document.createElement("span");
        number.textContent = `#${index + 1}`;
        const content = document.createElement("pre");
        content.textContent = JSON.stringify(event, null, 2);
        heading.append(type, number);
        article.append(heading, content);
        container.append(article);
      });
    }

    function toolName(event) {
      return String(event.content?.tool || "");
    }

    function outputSummary(event) {
      const output = String(event.content?.output || "");
      const match = output.match(/\b\\d+\\s+(?:passed|failed)\b/i);
      return match ? match[0] : "";
    }

    function analyzeEvents(events, verification) {
      let codeWrites = 0;
      let testRuns = 0;
      let failures = 0;
      let sawFailure = false;
      const timeline = [];
      events.forEach((event) => {
        const type = String(event.event_type || "");
        const tool = toolName(event);
        let title = "记录了一步过程";
        let detail = "";
        if (type === "llm_call") {
          title = "AI 查看进展并决定下一步";
        } else if (type === "tool_call" && tool === "write_file") {
          codeWrites += 1;
          title = "写入或修改代码";
        } else if (type === "tool_call" && tool === "execute") {
          testRuns += 1;
          title = "运行命令或测试";
        } else if (type === "tool_call" && tool === "read_file") {
          title = "读取文件";
        } else if (type === "tool_call") {
          title = "使用工具";
          detail = tool;
        } else if (type === "tool_result") {
          const success = event.content?.success !== false;
          if (!success) {
            failures += 1;
            sawFailure = true;
            title = "工具执行失败";
          } else if (sawFailure) {
            title = "失败后再次执行成功";
          } else {
            title = tool === "execute" ? "命令或测试执行完成" : "工具执行完成";
          }
          detail = outputSummary(event);
        } else if (type === "error") {
          failures += 1;
          sawFailure = true;
          title = "调用出现错误";
        }
        timeline.push({title, detail});
      });
      return {
        codeWrites,
        testRuns,
        failures,
        finalTests: `${verification.pytest_passed ?? 0} / ${verification.pytest_total ?? 0}`,
        timeline,
      };
    }

    function renderTimeline(items) {
      const container = document.getElementById("plainTimeline");
      container.replaceChildren();
      items.forEach((item, index) => {
        const row = document.createElement("div");
        row.className = "timeline-item";
        const number = document.createElement("div");
        number.className = "timeline-index";
        number.textContent = String(index + 1);
        const copy = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = item.title;
        const detail = document.createElement("span");
        detail.textContent = item.detail;
        copy.append(title);
        if (item.detail) copy.append(detail);
        row.append(number, copy);
        container.append(row);
      });
    }

    function assembledRationale() {
      const selected = reasonInputs.filter((input) => input.checked).map((input) => input.value);
      const custom = document.getElementById("customNote").value.trim();
      if (custom) selected.push(custom);
      return selected.join("；");
    }

    function updateSaveState() {
      document.getElementById("save").disabled = !selectedScore || !assembledRationale();
    }

    function chooseScore(score) {
      selectedScore = score;
      scoreButtons.forEach((button) => button.setAttribute("aria-pressed", String(Number(button.dataset.score) === score)));
      text("rubric", rubric[score]);
      updateSaveState();
    }

    function render(nextState) {
      state = nextState;
      const packet = state.packet;
      const evidence = packet.evidence || {};
      const task = evidence.task || {};
      const trace = evidence.trace || {};
      const metrics = evidence.metrics || {};
      const verification = evidence.verification || {};
      const analysis = analyzeEvents(trace.events || [], verification);
      const percent = state.total ? (state.completed / state.total) * 100 : 0;
      document.getElementById("bar").style.width = `${percent}%`;
      text("progress", `${state.completed} / ${state.total}`);
      text("round", `第 ${packet.round} 轮 · 第 ${state.index + 1} 条`);
      text("taskDescription", task.description);
      text("taskCode", task.input_code);
      text("finalCode", evidence.final_code);
      text("codeWrites", `${analysis.codeWrites} 次`);
      text("testRuns", `${analysis.testRuns} 次`);
      text("observedFailures", `${analysis.failures} 次`);
      text("finalTests", analysis.finalTests);
      text("plainSummary", `AI 写了 ${analysis.codeWrites} 次代码，运行了 ${analysis.testRuns} 次命令或测试，观察到 ${analysis.failures} 次失败；最终官方测试 ${analysis.finalTests}。`);
      text("verification", JSON.stringify({verification, metrics, trace_summary: {total_tokens: trace.total_tokens, total_duration: trace.total_duration, tool_call_count: trace.tool_call_count}}, null, 2));
      renderTimeline(analysis.timeline);
      renderRawTrace(trace.events || []);
      const savedRationale = state.response.rationale || "";
      reasonInputs.forEach((input) => { input.checked = savedRationale.includes(input.value); });
      const customParts = savedRationale.split("；").filter((part) => part && !reasonValues.includes(part));
      document.getElementById("customNote").value = customParts.join("；");
      selectedScore = null;
      if (state.response.score) chooseScore(Number(state.response.score));
      else {
        scoreButtons.forEach((button) => button.setAttribute("aria-pressed", "false"));
        text("rubric", "选择 1–5 分");
      }
      updateSaveState();
      document.getElementById("previous").disabled = state.index === 0;
      document.getElementById("next").disabled = state.index === state.total - 1;
      const message = document.getElementById("message");
      message.classList.add("hidden");
      message.classList.remove("error");
      if (state.complete) {
        message.textContent = state.valid ? "本轮完成，校验通过。" : state.errors.join("；");
        message.classList.remove("hidden");
        if (!state.valid) message.classList.add("error");
      }
    }

    async function load(index = null) {
      const path = index === null ? "/api/state" : `/api/state?index=${index}`;
      try { render(await request(path)); }
      catch (error) { showError(error); }
    }

    async function submit() {
      if (!state || !selectedScore) return;
      const rationale = assembledRationale();
      document.getElementById("save").disabled = true;
      try {
        render(await request("/api/review", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({packet_id: state.packet.packet_id, score: selectedScore, rationale}),
        }));
      } catch (error) {
        updateSaveState();
        showError(error);
      }
    }

    function showError(error) {
      const message = document.getElementById("message");
      message.textContent = error instanceof Error ? error.message : String(error);
      message.classList.remove("hidden");
      message.classList.add("error");
    }

    scoreButtons.forEach((button) => button.addEventListener("click", () => chooseScore(Number(button.dataset.score))));
    reasonInputs.forEach((input) => input.addEventListener("change", updateSaveState));
    document.getElementById("customNote").addEventListener("input", updateSaveState);
    document.getElementById("save").addEventListener("click", submit);
    document.getElementById("previous").addEventListener("click", () => load(state.index - 1));
    document.getElementById("next").addEventListener("click", () => load(state.index + 1));
    document.addEventListener("keydown", (event) => {
      if (["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
      if (/^[1-5]$/.test(event.key)) chooseScore(Number(event.key));
      if (event.key === "ArrowLeft" && state.index > 0) load(state.index - 1);
      if (event.key === "ArrowRight" && state.index < state.total - 1) load(state.index + 1);
    });
    load();
  </script>
</body>
</html>
"""
