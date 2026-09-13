"""OTLP/HTTP (JSON) parsing → the PULSE telemetry store interface.

We accept the OpenTelemetry OTLP-JSON payloads emitted by the standard OTLP/HTTP
exporter and map them onto the store's three primitives: metric points, log records,
and (for completeness) span-derived logs. This is the real ingestion path — an OTel
Collector or SDK can point straight at `/api/pulse/v1/{logs,metrics,traces}`.

Only the four modeled metric columns (request_rate, error_rate, p95_latency, cpu) are
persisted as points; any other metric name is ignored (the store schema is fixed).
"""

from __future__ import annotations

from app.pulse.store import METRIC_COLUMNS

_STATUS_ERROR = 2  # OTLP Span status code STATUS_CODE_ERROR


def _anyvalue(v: dict):
    if not isinstance(v, dict):
        return v
    for key in ("stringValue", "boolValue"):
        if key in v:
            return v[key]
    if "intValue" in v:
        try:
            return int(v["intValue"])
        except (TypeError, ValueError):
            return v["intValue"]
    for key in ("doubleValue", "asDouble", "asInt"):
        if key in v:
            return v[key]
    return None


def _attrs(attributes: list | None) -> dict:
    return {a.get("key"): _anyvalue(a.get("value", {})) for a in (attributes or [])}


def _service_name(resource: dict | None) -> str:
    return str(_attrs((resource or {}).get("attributes")).get("service.name") or "unknown")


def parse_logs(payload: dict) -> list[tuple[str, str, str]]:
    """→ list of (service, level, message)."""
    out: list[tuple[str, str, str]] = []
    for rl in payload.get("resourceLogs", []) or []:
        service = _service_name(rl.get("resource"))
        for sl in rl.get("scopeLogs", []) or []:
            for rec in sl.get("logRecords", []) or []:
                level = str(rec.get("severityText") or "INFO").upper()
                body = _anyvalue(rec.get("body", {})) or ""
                out.append((service, level, str(body)[:2000]))
    return out


def parse_metrics(payload: dict) -> list[tuple[str, dict]]:
    """→ list of (service, {metric_column: value}) with all four columns filled.

    Data points may carry their own `service.name` attribute (overriding the resource).
    Values are grouped per service; missing columns default to 0.0 so `add_point`
    (which requires the full set of columns) never KeyErrors."""
    acc: dict[str, dict[str, float]] = {}
    for rm in payload.get("resourceMetrics", []) or []:
        res_service = _service_name(rm.get("resource"))
        for sm in rm.get("scopeMetrics", []) or []:
            for metric in sm.get("metrics", []) or []:
                name = metric.get("name")
                if name not in METRIC_COLUMNS:
                    continue
                points = ((metric.get("gauge") or metric.get("sum") or {})
                          .get("dataPoints", []))
                for dp in points:
                    dp_service = _attrs(dp.get("attributes")).get("service.name")
                    service = str(dp_service or res_service)
                    value = _anyvalue(dp)
                    if value is None:
                        continue
                    acc.setdefault(service, {})[name] = float(value)
    result: list[tuple[str, dict]] = []
    for service, metrics in acc.items():
        result.append((service, {c: float(metrics.get(c, 0.0)) for c in METRIC_COLUMNS}))
    return result


def parse_traces(payload: dict) -> list[tuple[str, str, str]]:
    """→ list of (service, level, message) — spans become structured log lines,
    error spans at ERROR level so they surface in anomaly correlation."""
    out: list[tuple[str, str, str]] = []
    for rs in payload.get("resourceSpans", []) or []:
        service = _service_name(rs.get("resource"))
        for ss in rs.get("scopeSpans", []) or []:
            for span in ss.get("spans", []) or []:
                name = span.get("name", "span")
                status = (span.get("status") or {}).get("code", 0)
                level = "ERROR" if status == _STATUS_ERROR else "INFO"
                dur_ms = None
                try:
                    start = int(span.get("startTimeUnixNano", 0))
                    end = int(span.get("endTimeUnixNano", 0))
                    if end >= start > 0:
                        dur_ms = round((end - start) / 1_000_000, 2)
                except (TypeError, ValueError):
                    dur_ms = None
                msg = f"span {name}" + (f" ({dur_ms}ms)" if dur_ms is not None else "")
                out.append((service, level, msg))
    return out
