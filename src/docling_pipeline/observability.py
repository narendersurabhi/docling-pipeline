"""OpenTelemetry setup: traces, spans, and logs correlated with them (spec 002)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from opentelemetry import _logs, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    ConsoleLogRecordExporter,
    LogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from docling_pipeline import __version__
from docling_pipeline.config import ObservabilityConfig, TelemetryExporter

TRACER_NAME = "docling_pipeline"
CONSOLE_FORMAT = "%(message)s [trace_id=%(trace_id)s span_id=%(span_id)s]"

tracer = trace.get_tracer(TRACER_NAME, __version__)


def format_trace_id(trace_id: int) -> str:
    return trace.format_trace_id(trace_id)


def format_span_id(span_id: int) -> str:
    return trace.format_span_id(span_id)


def current_ids() -> tuple[str, str]:
    """(trace_id, span_id) of the active span as hex, or zeros when there is none."""
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return "0" * 32, "0" * 16
    return format_trace_id(ctx.trace_id), format_span_id(ctx.span_id)


class TraceContextFormatter(logging.Formatter):
    """Adds the active trace_id/span_id to console log lines without mutating the record."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = current_ids()
        record_copy = logging.makeLogRecord(record.__dict__)
        record_copy.trace_id, record_copy.span_id = trace_id, span_id
        return super().format(record_copy)


def build_resource(cfg: ObservabilityConfig) -> Resource:
    return Resource.create(
        {
            "service.name": cfg.service_name,
            "service.version": __version__,
            "deployment.environment.name": cfg.environment,
        }
    )


def _otlp_url(cfg: ObservabilityConfig, signal: str) -> str | None:
    # None lets the exporter honour OTEL_EXPORTER_OTLP_[TRACES|LOGS_]ENDPOINT itself.
    return f"{cfg.otlp_endpoint.rstrip('/')}/v1/{signal}" if cfg.otlp_endpoint else None


def build_span_exporter(cfg: ObservabilityConfig) -> SpanExporter | None:
    if cfg.traces_exporter is TelemetryExporter.CONSOLE:
        return ConsoleSpanExporter()
    if cfg.traces_exporter is TelemetryExporter.OTLP:
        return OTLPSpanExporter(endpoint=_otlp_url(cfg, "traces"), timeout=cfg.otlp_timeout_s)
    return None


def build_log_exporter(cfg: ObservabilityConfig) -> LogRecordExporter | None:
    if cfg.logs_exporter is TelemetryExporter.CONSOLE:
        return ConsoleLogRecordExporter()
    if cfg.logs_exporter is TelemetryExporter.OTLP:
        return OTLPLogExporter(endpoint=_otlp_url(cfg, "logs"), timeout=cfg.otlp_timeout_s)
    return None


def build_providers(
    cfg: ObservabilityConfig,
    span_exporter: SpanExporter | None = None,
    log_exporter: LogRecordExporter | None = None,
    batch: bool = True,
) -> tuple[TracerProvider, LoggerProvider]:
    """Build (not install) providers. Explicit exporters override the configured ones."""
    resource = build_resource(cfg)
    tracer_provider = TracerProvider(
        resource=resource, sampler=ParentBased(TraceIdRatioBased(cfg.sample_ratio))
    )
    logger_provider = LoggerProvider(resource=resource)

    span_exporter = span_exporter or build_span_exporter(cfg)
    if span_exporter is not None:
        processor = BatchSpanProcessor if batch else SimpleSpanProcessor
        tracer_provider.add_span_processor(processor(span_exporter))

    log_exporter = log_exporter or build_log_exporter(cfg)
    if log_exporter is not None:
        processor = BatchLogRecordProcessor if batch else SimpleLogRecordProcessor
        logger_provider.add_log_record_processor(processor(log_exporter))

    return tracer_provider, logger_provider


@dataclass
class Telemetry:
    """Handle returned by `setup_telemetry`. Call `shutdown()` exactly once on exit."""

    tracer_provider: TracerProvider | None = None
    logger_provider: LoggerProvider | None = None
    owns_providers: bool = False
    handlers: list[logging.Handler] = field(default_factory=list)

    def shutdown(self) -> None:
        root = logging.getLogger()
        for handler in self.handlers:
            root.removeHandler(handler)
            handler.close()
        self.handlers.clear()
        for provider in (self.tracer_provider, self.logger_provider):
            if provider is None:
                continue
            try:
                if self.owns_providers:
                    provider.shutdown()
                else:
                    provider.force_flush()
            except Exception:  # NFR-004: telemetry must never break the pipeline
                logging.getLogger(__name__).debug("telemetry shutdown failed", exc_info=True)


def _installed_sdk_providers() -> tuple[TracerProvider, LoggerProvider] | None:
    tp, lp = trace.get_tracer_provider(), _logs.get_logger_provider()
    if isinstance(tp, TracerProvider) and isinstance(lp, LoggerProvider):
        return tp, lp
    return None


def setup_telemetry(
    cfg: ObservabilityConfig,
    console_level: int | None = logging.WARNING,
    console_handler: logging.Handler | None = None,
    span_exporter: SpanExporter | None = None,
    log_exporter: LogRecordExporter | None = None,
    batch: bool = True,
) -> Telemetry:
    """Install global tracer/logger providers and logging handlers.

    Reuses providers already installed in this process (FR-015), since OpenTelemetry
    only allows the global providers to be set once.
    """
    telemetry = Telemetry()
    root = logging.getLogger()
    levels = []

    if console_level is not None:
        handler = console_handler or logging.StreamHandler()
        handler.setLevel(console_level)
        handler.setFormatter(TraceContextFormatter(CONSOLE_FORMAT))
        root.addHandler(handler)
        telemetry.handlers.append(handler)
        levels.append(console_level)

    if cfg.enabled:
        existing = _installed_sdk_providers()
        if existing:
            telemetry.tracer_provider, telemetry.logger_provider = existing
        else:
            tp, lp = build_providers(cfg, span_exporter, log_exporter, batch=batch)
            trace.set_tracer_provider(tp)
            _logs.set_logger_provider(lp)
            telemetry.tracer_provider, telemetry.logger_provider = tp, lp
            telemetry.owns_providers = True

        otel_level = logging.getLevelName(cfg.log_level)
        levels.append(otel_level)
        if not any(isinstance(h, LoggingHandler) for h in root.handlers):
            otel_handler = LoggingHandler(
                level=otel_level, logger_provider=telemetry.logger_provider
            )
            root.addHandler(otel_handler)
            telemetry.handlers.append(otel_handler)

    if levels:
        root.setLevel(min(levels))
    return telemetry
