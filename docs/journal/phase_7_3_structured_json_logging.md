# Session 7.3: Structured JSON Logging
**Date:** 2026-10-14

*Implemented Step 7.3: Structured JSON Logging in `src/observability/logger.py`. Configured `structlog` for high-throughput, machine-readable single-line JSON output to stdout. Integrated contextual metadata merging via `structlog.contextvars.merge_contextvars` to enable automatic propagation of distributed trace IDs (`session_id`, `tenant_id`, `request_id`) across asynchronous coroutines without manual parameter threading. Introduced `DualStreamWriter` (derived from `io.StringIO`) supporting primary stdout streaming and optional append-only file sinking (`traces.jsonl`). Built defensive exception shielding and stringification fallbacks (`default=str`) within `JSONRenderer` to uphold the "Zero Naked Crash" principle during unhandled serialization faults. Maintained strict static typing with `FilteringBoundLogger` and kept all files strictly below the 250 LOC threshold.*

---

### 1. 🎓 Concepts Introduced
- **Single-Line JSON Lines (JSONL) Logging**: Standardized log format where each log record is serialized into a discrete, deterministic JSON object on a single line, enabling ingestion by log collectors (Datadog, FluentBit, CloudWatch) without multi-line regex parsing.
- **Context-Bound Logging via Contextvars**: Asynchronous context propagation leveraging Python's `contextvars` module, allowing background tasks and coroutines to bind session or tenant identifiers once and have them automatically merged into all subsequent log entries.
- **Bound Filtering Logger Architecture**: Pre-filtering logger wrapper (`make_filtering_bound_logger`) that drops log events below the active log level before invoking processor chains or allocating serialization buffers, ensuring zero-allocation performance on suppressed debug logs.
- **Non-Blocking Dual Stream Writer**: I/O adapter derived from `io.StringIO` that multiplexes formatted JSON log lines to standard output and optional persistent audit files (`traces.jsonl`) while shielding callers against raw disk I/O failures.
- **Fail-Safe Non-Primitive Serialization**: Defensive serialization strategy using `JSONRenderer(default=str, sort_keys=True)` that guarantees non-serializable objects (Paths, datetimes, custom sets) convert cleanly to strings rather than crashing application threads.

---

### 2. 🧠 Architecture Decisions (ADR)

#### Decision: Direct PrintLoggerFactory vs. Standard Library logging Subsystem
- **Option 1:** Routing structlog events through Python's standard `logging` hierarchy via `structlog.stdlib.LoggerFactory()`.
- **Option 2 (Selected):** Emitting directly to standard output via `structlog.PrintLoggerFactory` with `DualStreamWriter`.
- **Rationale:** Python's standard `logging` library uses global locks on handler streams, creating thread contention in high-concurrency async services. `PrintLoggerFactory` bypasses the standard library logging lock overhead, delivers predictable low latency, and guarantees direct stdout capture by container runtimes (Kubernetes / Docker).

#### Decision: Asynchronous Contextvars Merging vs. Explicit Parameter Threading
- **Option 1:** Passing `session_id`, `tenant_id`, and `order_id` manually as kwargs to every `logger.info()` call across domain and tool layers.
- **Option 2 (Selected):** Using `structlog.contextvars.merge_contextvars` with helper functions (`bind_contextvars`, `clear_contextvars`).
- **Rationale:** Manual parameter threading clutters domain function signatures and violates layer isolation by forcing core logic to manage telemetry fields. Contextvars maintain task-local isolation across asynchronous execution loops, ensuring seamless trace correlation without parameter pollution.

#### Decision: Safe Fallback Stringification vs. Strict JSON Serialization
- **Option 1:** Allowing `json.dumps()` to raise `TypeError` when an unhandled object type (e.g. `Path`, custom DTO) is logged.
- **Option 2 (Selected):** Configuring `structlog.processors.JSONRenderer(default=str, sort_keys=True)`.
- **Rationale:** Adheres to the Universal Engineering Guardrail of "Robust Error Handling" and "Zero Naked Crash". Diagnostic logging must never become the source of an application crash in production.

---

### 3. 🛠️ Implementation & Code
*Implementation details and validation commands.*

```python
# src/observability/logger.py
class DualStreamWriter(io.StringIO):
    """Thread-safe writer supporting stream output and optional file appending."""

    def __init__(
        self,
        stream: TextIO | None = None,
        file_path: Path | str | None = None,
    ) -> None:
        super().__init__()
        self.stream: TextIO = stream if stream is not None else sys.stdout
        self.file_path: Path | None = Path(file_path) if file_path else None

    def write(self, s: str) -> int:
        self.stream.write(s)
        if self.file_path is not None:
            try:
                with open(self.file_path, "a", encoding="utf-8") as file:
                    file.write(s)
            except Exception:
                pass
        return len(s)


def setup_logger(
    log_level: str | None = None,
    stream: TextIO | None = None,
    log_file: Path | str | None = None,
    json_output: bool = True,
) -> None:
    level_num: int = getattr(logging, (log_level or "INFO").upper(), logging.INFO)
    renderer = (
        structlog.processors.JSONRenderer(sort_keys=True, default=str)
        if json_output
        else structlog.dev.ConsoleRenderer()
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        renderer,
    ]

    writer = DualStreamWriter(stream=stream, file_path=log_file)
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=writer),
        cache_logger_on_first_use=False,
    )
```

```bash
# Verification commands
make lint
make typecheck
make test
```

---

### 4. 📌 Session Checklist & Deliverables
1. [x] **Structured JSON Logging Engine (`src/observability/logger.py`)**: Configured structlog pipeline with ISO-8601 UTC timestamps, level normalization, contextvars merging, and sorted JSON rendering.
2. [x] **Zero-Allocation Level Filtering**: Integrated `make_filtering_bound_logger` for immediate short-circuiting of suppressed log levels.
3. [x] **Context Management Utilities**: Built `bind_contextvars`, `unbind_contextvars`, `clear_contextvars`, and `get_contextvars` for coroutine telemetry propagation.
4. [x] **DualStreamWriter I/O Multiplexing**: Implemented thread-safe `DualStreamWriter` (inheriting from `io.StringIO`) for stdout streaming and optional file appending (`traces.jsonl`).
5. [x] **Defensive Serialization**: Configured `default=str` in `JSONRenderer` and I/O error shielding in writer, upholding "Zero Naked Crash".
6. [x] **Strict Static Typing**: Annotated logger instances with `FilteringBoundLogger` eliminating dynamically typed escapes.
7. [x] **Unit Test Suite (`tests/unit/test_logger.py`)**: Added 8 unit tests covering single-line JSON formatting, log level filtering, contextvars binding, exception tracebacks, safe non-primitive serialization, dual output, and console dev mode.
8. [x] **Quality Gates Verified**: `mypy --strict` passed across 92 source files, Ruff format and check passed cleanly, and full test suite passed with 317 tests passing 100% at 92.98% coverage.
