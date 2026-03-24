from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, TypeVar

from lantern_house.config import FailSafeConfig
from lantern_house.utils.time import ensure_utc, isoformat, utcnow

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AdaptiveServiceError(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        expected_inputs: list[str] | None = None,
        retry_advice: str | None = None,
        context: dict[str, Any] | None = None,
        recoverable: bool = True,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.expected_inputs = expected_inputs or []
        self.retry_advice = (
            retry_advice or "Retry after correcting the input or allowing the service to recover."
        )
        self.context = context or {}
        self.recoverable = recoverable


@dataclass(slots=True)
class AdaptiveFailure:
    operation: str
    reason: str
    recoverable: bool = True
    expected_inputs: list[str] = field(default_factory=list)
    retry_advice: str = "Retry after correcting the input or allowing the service to recover."
    context: dict[str, Any] = field(default_factory=dict)
    failure_streak: int = 1
    next_retry_at: str | None = None
    fallback_used: str | None = None
    exception_type: str | None = None
    traceback_excerpt: str | None = None

    def caller_message(self) -> str:
        expected = f" Expected: {'; '.join(self.expected_inputs)}." if self.expected_inputs else ""
        retry = f" {self.retry_advice}" if self.retry_advice else ""
        return f"{self.reason}.{expected}{retry}".strip()


@dataclass(slots=True)
class AdaptiveCallResult[T]:
    ok: bool
    value: T | None = None
    failure: AdaptiveFailure | None = None
    used_fallback: bool = False


@dataclass(slots=True)
class OperationState:
    failure_streak: int = 0
    next_retry_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_good_value: Any = None


class FailSafeExecutor:
    def __init__(self, config: FailSafeConfig) -> None:
        self.config = config
        self._state: dict[str, OperationState] = {}

    def call(
        self,
        operation: str,
        func: Callable[[], T],
        *,
        context: dict[str, Any] | None = None,
        expected_inputs: list[str] | None = None,
        retry_advice: str | None = None,
        fallback: T | Callable[[], T] | None = None,
        fallback_label: str | None = None,
    ) -> AdaptiveCallResult[T]:
        if not self.config.enabled:
            return AdaptiveCallResult(ok=True, value=func())

        now = utcnow()
        state = self._state.setdefault(operation, OperationState())
        if self._pause_active(state=state, now=now):
            return self._cooldown_result(
                operation=operation,
                state=state,
                context=context,
                expected_inputs=expected_inputs,
                retry_advice=retry_advice,
                fallback=fallback,
                fallback_label=fallback_label,
            )

        try:
            value = func()
        except Exception as exc:
            return self._recover(
                operation=operation,
                state=state,
                error=exc,
                context=context,
                expected_inputs=expected_inputs,
                retry_advice=retry_advice,
                fallback=fallback,
                fallback_label=fallback_label,
                now=now,
            )

        self._mark_success(state=state, value=value, now=now)
        return AdaptiveCallResult(ok=True, value=value)

    async def call_async(
        self,
        operation: str,
        func: Callable[[], Awaitable[T]],
        *,
        context: dict[str, Any] | None = None,
        expected_inputs: list[str] | None = None,
        retry_advice: str | None = None,
        fallback: T | Callable[[], T] | None = None,
        fallback_label: str | None = None,
    ) -> AdaptiveCallResult[T]:
        if not self.config.enabled:
            return AdaptiveCallResult(ok=True, value=await func())

        now = utcnow()
        state = self._state.setdefault(operation, OperationState())
        if self._pause_active(state=state, now=now):
            return self._cooldown_result(
                operation=operation,
                state=state,
                context=context,
                expected_inputs=expected_inputs,
                retry_advice=retry_advice,
                fallback=fallback,
                fallback_label=fallback_label,
            )

        try:
            value = await func()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return self._recover(
                operation=operation,
                state=state,
                error=exc,
                context=context,
                expected_inputs=expected_inputs,
                retry_advice=retry_advice,
                fallback=fallback,
                fallback_label=fallback_label,
                now=now,
            )

        self._mark_success(state=state, value=value, now=now)
        return AdaptiveCallResult(ok=True, value=value)

    def _recover(
        self,
        *,
        operation: str,
        state: OperationState,
        error: Exception,
        context: dict[str, Any] | None,
        expected_inputs: list[str] | None,
        retry_advice: str | None,
        fallback: T | Callable[[], T] | None,
        fallback_label: str | None,
        now,
    ) -> AdaptiveCallResult[T]:
        state.failure_streak += 1
        state.last_failure_at = now
        if state.failure_streak >= self.config.max_consecutive_failures_before_pause:
            state.next_retry_at = now + timedelta(
                seconds=self._cooldown_seconds(state.failure_streak)
            )
        else:
            state.next_retry_at = None

        failure = self._build_failure(
            operation=operation,
            error=error,
            context=context,
            expected_inputs=expected_inputs,
            retry_advice=retry_advice,
            failure_streak=state.failure_streak,
            next_retry_at=state.next_retry_at,
            fallback_used=fallback_label or self._fallback_name(state=state, fallback=fallback),
        )
        self._log_failure(failure)
        value, used_fallback = self._resolve_fallback(state=state, fallback=fallback)
        return AdaptiveCallResult(
            ok=False,
            value=value,
            failure=failure,
            used_fallback=used_fallback,
        )

    def _cooldown_result(
        self,
        *,
        operation: str,
        state: OperationState,
        context: dict[str, Any] | None,
        expected_inputs: list[str] | None,
        retry_advice: str | None,
        fallback: T | Callable[[], T] | None,
        fallback_label: str | None,
    ) -> AdaptiveCallResult[T]:
        failure = AdaptiveFailure(
            operation=operation,
            reason="Repeated failures triggered a temporary cooldown to protect the live runtime",
            recoverable=True,
            expected_inputs=expected_inputs or [],
            retry_advice=retry_advice
            or "Retry after the cooldown window or after correcting the input.",
            context=context or {},
            failure_streak=state.failure_streak,
            next_retry_at=isoformat(state.next_retry_at) if state.next_retry_at else None,
            fallback_used=fallback_label or self._fallback_name(state=state, fallback=fallback),
        )
        value, used_fallback = self._resolve_fallback(state=state, fallback=fallback)
        return AdaptiveCallResult(
            ok=False,
            value=value,
            failure=failure,
            used_fallback=used_fallback,
        )

    def _resolve_fallback(
        self,
        *,
        state: OperationState,
        fallback: T | Callable[[], T] | None,
    ) -> tuple[T | None, bool]:
        if self.config.keep_last_good_value and state.last_good_value is not None:
            return state.last_good_value, True
        if callable(fallback):
            try:
                return fallback(), True
            except Exception as exc:
                log_call_failure(
                    "failsafe.resolve_fallback",
                    exc,
                    context={"failure_streak": state.failure_streak},
                    expected_inputs=[
                        "A fallback callable that can produce a safe replacement value."
                    ],
                    retry_advice=(
                        "Fix the fallback producer or allow the runtime to continue without "
                        "that replacement value."
                    ),
                )
                return None, False
        if fallback is not None:
            return fallback, True
        return None, False

    def _fallback_name(
        self,
        *,
        state: OperationState,
        fallback: T | Callable[[], T] | None,
    ) -> str | None:
        if self.config.keep_last_good_value and state.last_good_value is not None:
            return "last-good-value"
        if fallback is not None:
            return "configured-fallback"
        return None

    def _build_failure(
        self,
        *,
        operation: str,
        error: Exception,
        context: dict[str, Any] | None,
        expected_inputs: list[str] | None,
        retry_advice: str | None,
        failure_streak: int,
        next_retry_at,
        fallback_used: str | None,
    ) -> AdaptiveFailure:
        if isinstance(error, AdaptiveServiceError):
            reason = error.reason
            expected = error.expected_inputs or expected_inputs or []
            advice = error.retry_advice or retry_advice
            merged_context = {**(context or {}), **error.context}
            recoverable = error.recoverable
        else:
            reason = str(error) or error.__class__.__name__
            expected = expected_inputs or []
            advice = retry_advice
            merged_context = context or {}
            recoverable = True
        return AdaptiveFailure(
            operation=operation,
            reason=reason,
            recoverable=recoverable,
            expected_inputs=expected,
            retry_advice=advice
            or "Retry after correcting the input or allowing the dependency to recover.",
            context=merged_context,
            failure_streak=failure_streak,
            next_retry_at=isoformat(next_retry_at) if next_retry_at else None,
            fallback_used=fallback_used,
            exception_type=error.__class__.__name__,
            traceback_excerpt="".join(traceback.format_exception_only(type(error), error)).strip(),
        )

    def _log_failure(self, failure: AdaptiveFailure) -> None:
        logger.error(
            "Recovered failed call: %s",
            failure.operation,
            extra={
                "operation": failure.operation,
                "recoverable": failure.recoverable,
                "expected_inputs": failure.expected_inputs,
                "retry_advice": failure.retry_advice,
                "context": failure.context,
                "failure_streak": failure.failure_streak,
                "next_retry_at": failure.next_retry_at,
                "fallback_used": failure.fallback_used,
                "exception_type": failure.exception_type,
                "traceback_excerpt": failure.traceback_excerpt,
            },
        )

    def _mark_success(self, *, state: OperationState, value: Any, now) -> None:
        state.failure_streak = 0
        state.next_retry_at = None
        state.last_success_at = now
        if self.config.keep_last_good_value:
            state.last_good_value = value

    def _pause_active(self, *, state: OperationState, now) -> bool:
        if state.next_retry_at is None:
            return False
        return ensure_utc(state.next_retry_at) > ensure_utc(now)

    def _cooldown_seconds(self, failure_streak: int) -> int:
        exponent = max(0, failure_streak - self.config.max_consecutive_failures_before_pause)
        delay = self.config.base_retry_delay_seconds * (2**exponent)
        return min(self.config.max_retry_delay_seconds, delay)


def log_call_failure(
    operation: str,
    error: Exception,
    *,
    context: dict[str, Any] | None = None,
    expected_inputs: list[str] | None = None,
    retry_advice: str | None = None,
    fallback_used: str | None = None,
) -> None:
    if isinstance(error, AdaptiveServiceError):
        expected = error.expected_inputs or expected_inputs or []
        advice = error.retry_advice or retry_advice
        recoverable = error.recoverable
        merged_context = {**(context or {}), **error.context}
    else:
        expected = expected_inputs or []
        advice = retry_advice
        recoverable = True
        merged_context = context or {}

    logger.error(
        "Recovered failed call: %s",
        operation,
        extra={
            "operation": operation,
            "recoverable": recoverable,
            "expected_inputs": expected,
            "retry_advice": advice
            or "Retry after correcting the input or allowing the dependency to recover.",
            "context": merged_context,
            "fallback_used": fallback_used,
            "exception_type": error.__class__.__name__,
            "traceback_excerpt": "".join(
                traceback.format_exception_only(type(error), error)
            ).strip(),
        },
    )
