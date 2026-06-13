"""Stateful lap/session lifecycle detection for decoded FH Data Out packets.

The detector only classifies packet boundaries and uncertainty. It intentionally does
not write to storage or depend on the FastAPI/live ingest layer so later milestone
work can decide how to persist the returned actions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


TELEPORT_DISTANCE_METERS = 1_000.0
RESET_DISTANCE_METERS = 100.0
ROUTE_MATCH_DISTANCE_METERS = 35.0
ROUTE_HISTORY_MAX_SAMPLES = 6_000
MEANINGFUL_RACE_TIME_SECONDS = 5.0
RACE_TIME_RESET_CEILING_SECONDS = 1.0
RACE_TIME_RESET_DROP_SECONDS = 3.0
LAST_LAP_EPSILON_SECONDS = 0.001
TIMER_MATCH_TOLERANCE_SECONDS = 0.25


@dataclass(frozen=True)
class _RouteSample:
    index: int
    lap_id: int | None
    lap_number: int | None
    position: tuple[float, float, float]
    current_lap: float
    current_race_time: float


class LapDetector:
    """Detect session and lap lifecycle events from decoded telemetry packets."""

    def __init__(self) -> None:
        self._next_session_id = 1
        self._next_lap_id = 1
        self._active_session_id: int | None = None
        self._active_lap_id: int | None = None
        self._active_lap_number: int | None = None
        self._paused = False
        self._last_position: tuple[float, float, float] | None = None
        self._last_current_lap: float | None = None
        self._last_race_time: float | None = None
        self._max_race_time = 0.0
        self._last_lap_value = 0.0
        self._route_history: list[_RouteSample] = []
        self._next_route_sample_index = 1

    def observe(self, decoded: dict, received_at_ms: int) -> dict:
        """Classify one decoded packet and update detector state.

        Returned actions are intentionally descriptive rather than persistent: callers
        can retain every packet while using ``lap_id=None`` and ``uncertainty`` to
        avoid over-claiming ambiguous free-roam, pause/menu, teleport, or event-exit
        samples.
        """

        is_race_on = bool(_as_int(decoded.get("IsRaceOn"), 0))
        raw_lap_number = _as_optional_int(decoded.get("LapNumber"))
        current_lap = _as_float(decoded.get("CurrentLap"))
        current_race_time = _as_float(decoded.get("CurrentRaceTime"))
        last_lap = _as_float(decoded.get("LastLap"))
        position = _position(decoded)

        if self._detect_event_exit(
            is_race_on=is_race_on,
            current_race_time=current_race_time,
        ):
            return self._finalize_for_event_exit(
                decoded=decoded,
                received_at_ms=received_at_ms,
                is_race_on=is_race_on,
                raw_lap_number=raw_lap_number,
                current_lap=current_lap,
                current_race_time=current_race_time,
                last_lap=last_lap,
                position=position,
            )

        was_paused = self._paused
        session_action = "none"
        if self._active_session_id is None:
            self._start_session(paused=not is_race_on)
            session_action = "start"
        elif is_race_on and self._paused:
            self._paused = False
            session_action = "resume"
        elif not is_race_on:
            if not self._paused:
                session_action = "pause"
            self._paused = True

        previous_lap_number = self._active_lap_number
        active_lap_signal = _has_active_lap_signal(
            is_race_on=is_race_on,
            lap_number=raw_lap_number,
            current_lap=current_lap,
            current_race_time=current_race_time,
        )
        lap_number = raw_lap_number if active_lap_signal else None
        if lap_number is None and active_lap_signal:
            lap_number = 0

        lap_action = "none"
        finalized_lap_id: int | None = None
        finalized_lap_number: int | None = None
        partial_lap_boundary = False
        new_last_lap = self._is_new_last_lap(last_lap)
        resume_split_uncertainty = self._resume_split_uncertainty(
            was_paused=was_paused,
            is_race_on=is_race_on,
            active_lap_signal=active_lap_signal,
            raw_lap_number=raw_lap_number,
            current_lap=current_lap,
            current_race_time=current_race_time,
            position=position,
        )
        position_delta = self._position_delta(position)
        race_control_event = self._classify_race_control_event(
            was_paused=was_paused,
            is_race_on=is_race_on,
            active_lap_signal=active_lap_signal,
            lap_number=lap_number,
            current_lap=current_lap,
            current_race_time=current_race_time,
            position=position,
            position_delta=position_delta,
        )
        if race_control_event is not None:
            resume_split_uncertainty = None
        teleport = (
            is_race_on
            and position_delta is not None
            and position_delta > TELEPORT_DISTANCE_METERS
        )
        direct_teleport_split = (
            teleport
            and resume_split_uncertainty is None
            and race_control_event is None
            and active_lap_signal
            and self._active_lap_id is not None
        )

        if not self._paused and race_control_event is None:
            if (
                (resume_split_uncertainty is not None or direct_teleport_split)
                and active_lap_signal
                and self._active_lap_id is not None
            ):
                current_lap_number = int(lap_number)
                finalized_lap_id = self._active_lap_id
                finalized_lap_number = self._active_lap_number
                self._start_lap(current_lap_number)
                lap_action = "finalize_and_start"
                partial_lap_boundary = resume_split_uncertainty == "partial_lap"
            elif active_lap_signal:
                current_lap_number = int(lap_number)
                if self._active_lap_id is None:
                    self._start_lap(current_lap_number)
                    lap_action = "start"
                elif current_lap_number > int(self._active_lap_number):
                    finalized_lap_id = self._active_lap_id
                    finalized_lap_number = self._active_lap_number
                    self._start_lap(current_lap_number)
                    lap_action = "finalize_and_start"
                elif current_lap_number < int(self._active_lap_number):
                    finalized_lap_id = self._active_lap_id
                    finalized_lap_number = self._active_lap_number
                    self._start_lap(current_lap_number)
                    lap_action = "finalize_and_start"
                    partial_lap_boundary = True
                elif new_last_lap:
                    finalized_lap_id = self._active_lap_id
                    finalized_lap_number = self._active_lap_number
                    self._start_lap(current_lap_number)
                    lap_action = "finalize_and_start"
            elif self._active_lap_id is not None and new_last_lap:
                finalized_lap_id = self._active_lap_id
                finalized_lap_number = self._active_lap_number
                self._active_lap_id = None
                self._active_lap_number = None
                lap_action = "finalize"

        uncertainty: str | None = None
        if self._paused:
            uncertainty = "paused"
        elif race_control_event is not None:
            uncertainty = str(race_control_event["uncertainty"])
        elif resume_split_uncertainty is not None:
            uncertainty = resume_split_uncertainty
        elif teleport:
            uncertainty = "teleport"
        elif not active_lap_signal and lap_action == "none":
            uncertainty = "no_lap_signal"
        elif partial_lap_boundary:
            uncertainty = "partial_lap"

        boundary_confidence = _boundary_confidence(
            uncertainty=uncertainty,
            lap_action=lap_action,
            active_lap_signal=active_lap_signal,
            session_action=session_action,
        )

        packet_lap_id = self._packet_lap_id(
            active_lap_signal=active_lap_signal,
            lap_action=lap_action,
            uncertainty=uncertainty,
        )
        if race_control_event is not None:
            self._discard_route_history_after(
                int(race_control_event["match_route_sample_index"]),
            )
        self._remember_packet(
            is_race_on=is_race_on,
            position=position,
            current_lap=current_lap,
            current_race_time=current_race_time,
            last_lap=last_lap,
        )

        return {
            "session_action": session_action,
            "lap_action": lap_action,
            "lap_number": lap_number,
            "boundary_confidence": boundary_confidence,
            "uncertainty": uncertainty,
            "session_id": self._active_session_id,
            "active_session_id": self._active_session_id,
            "session_active": self._active_session_id is not None,
            "lap_id": packet_lap_id,
            "active_lap_id": self._active_lap_id,
            "previous_lap_number": previous_lap_number,
            "raw_lap_number": raw_lap_number,
            "finalized_lap_id": finalized_lap_id,
            "finalized_lap_number": finalized_lap_number,
            "finalized_session_id": None,
            "received_at_ms": int(received_at_ms),
            "is_race_on": is_race_on,
            "current_lap": current_lap,
            "current_race_time": current_race_time,
            "last_lap": last_lap,
            "position": position,
            "position_delta_m": position_delta,
            "race_control_match_distance_m": (
                None
                if race_control_event is None
                else race_control_event["match_distance_m"]
            ),
            "race_control_discard_after_current_lap": (
                None
                if race_control_event is None
                else race_control_event["discard_after_current_lap"]
            ),
            "race_control_match_current_lap": (
                None
                if race_control_event is None
                else race_control_event["match_current_lap"]
            ),
        }

    def _start_session(self, *, paused: bool) -> None:
        self._active_session_id = self._next_session_id
        self._next_session_id += 1
        self._active_lap_id = None
        self._active_lap_number = None
        self._paused = paused
        self._last_position = None
        self._last_current_lap = None
        self._last_race_time = None
        self._max_race_time = 0.0
        self._last_lap_value = 0.0
        self._route_history = []
        self._next_route_sample_index = 1

    def _start_lap(self, lap_number: int) -> None:
        self._active_lap_id = self._next_lap_id
        self._next_lap_id += 1
        self._active_lap_number = lap_number

    def _detect_event_exit(self, *, is_race_on: bool, current_race_time: float) -> bool:
        if not is_race_on:
            return False
        if self._active_session_id is None or self._last_race_time is None:
            return False
        if self._max_race_time < MEANINGFUL_RACE_TIME_SECONDS:
            return False
        if current_race_time > RACE_TIME_RESET_CEILING_SECONDS:
            return False
        return self._last_race_time - current_race_time >= RACE_TIME_RESET_DROP_SECONDS

    def _finalize_for_event_exit(
        self,
        *,
        decoded: dict,
        received_at_ms: int,
        is_race_on: bool,
        raw_lap_number: int | None,
        current_lap: float,
        current_race_time: float,
        last_lap: float,
        position: tuple[float, float, float],
    ) -> dict:
        finalized_session_id = self._active_session_id
        finalized_lap_id = self._active_lap_id
        finalized_lap_number = self._active_lap_number
        lap_action = "finalize" if self._active_lap_id is not None else "none"
        previous_lap_number = self._active_lap_number
        position_delta = self._position_delta(position)

        self._active_session_id = None
        self._active_lap_id = None
        self._active_lap_number = None
        self._paused = False
        self._last_position = None
        self._last_current_lap = None
        self._last_race_time = None
        self._max_race_time = 0.0
        self._last_lap_value = 0.0
        self._route_history = []
        self._next_route_sample_index = 1

        return {
            "session_action": "finalize",
            "lap_action": lap_action,
            "lap_number": raw_lap_number,
            "boundary_confidence": "heuristic",
            "uncertainty": "event_exit",
            "session_id": finalized_session_id,
            "active_session_id": None,
            "session_active": False,
            "lap_id": None,
            "active_lap_id": None,
            "previous_lap_number": previous_lap_number,
            "raw_lap_number": raw_lap_number,
            "finalized_lap_id": finalized_lap_id,
            "finalized_lap_number": finalized_lap_number,
            "finalized_session_id": finalized_session_id,
            "received_at_ms": int(received_at_ms),
            "is_race_on": is_race_on,
            "current_lap": current_lap,
            "current_race_time": current_race_time,
            "last_lap": last_lap,
            "position": position,
            "position_delta_m": position_delta,
            "race_control_match_distance_m": None,
            "race_control_discard_after_current_lap": None,
            "race_control_match_current_lap": None,
        }

    def _is_new_last_lap(self, last_lap: float) -> bool:
        return (
            last_lap > 0.0
            and abs(last_lap - self._last_lap_value) > LAST_LAP_EPSILON_SECONDS
        )

    def _position_delta(self, position: tuple[float, float, float]) -> float | None:
        if self._last_position is None:
            return None
        return math.dist(self._last_position, position)

    def _resume_split_uncertainty(
        self,
        *,
        was_paused: bool,
        is_race_on: bool,
        active_lap_signal: bool,
        raw_lap_number: int | None,
        current_lap: float,
        current_race_time: float,
        position: tuple[float, float, float],
    ) -> str | None:
        if not (
            was_paused
            and is_race_on
            and active_lap_signal
            and self._active_lap_id is not None
        ):
            return None

        position_delta = self._position_delta(position)
        if position_delta is not None and position_delta > TELEPORT_DISTANCE_METERS:
            return "teleport"

        if (
            raw_lap_number is not None
            and self._active_lap_number is not None
            and raw_lap_number < int(self._active_lap_number)
        ):
            return "partial_lap"

        if self._timer_reset(self._last_current_lap, current_lap):
            return "partial_lap"

        if self._timer_reset(self._last_race_time, current_race_time):
            return "partial_lap"

        return None

    def _timer_reset(self, previous: float | None, current: float) -> bool:
        if previous is None:
            return False
        if previous < MEANINGFUL_RACE_TIME_SECONDS:
            return False
        return previous - current >= RACE_TIME_RESET_DROP_SECONDS

    def _classify_race_control_event(
        self,
        *,
        was_paused: bool,
        is_race_on: bool,
        active_lap_signal: bool,
        lap_number: int | None,
        current_lap: float,
        current_race_time: float,
        position: tuple[float, float, float],
        position_delta: float | None,
    ) -> dict | None:
        if not (
            is_race_on
            and active_lap_signal
            and self._active_lap_id is not None
            and self._route_history
        ):
            return None

        if was_paused:
            match = self._nearest_route_match(position)
            if match is None:
                return None
            # Forza rewind can make race packets disappear temporarily, then
            # resume at an exact earlier route sample. Some race/event reset
            # paths also return near the route after a race-off gap; the user
            # preference is to keep these under the rewind affordance when the
            # telemetry is not clearly distinguishable.
            if _timer_matches(match.current_lap, current_lap) or _timer_matches(
                match.current_race_time,
                current_race_time,
            ):
                return self._race_control_event("rewind", match, position)
            return None

        if position_delta is None:
            return None
        if not (RESET_DISTANCE_METERS <= position_delta < TELEPORT_DISTANCE_METERS):
            return None
        if self._timer_reset(self._last_current_lap, current_lap):
            return None
        if self._timer_reset(self._last_race_time, current_race_time):
            return None
        match = self._nearest_route_match(position, prefer_recent=True)
        if match is None:
            return None
        return self._race_control_event("reset", match, position)

    def _nearest_route_match(
        self,
        position: tuple[float, float, float],
        *,
        prefer_recent: bool = False,
    ) -> _RouteSample | None:
        best_sample: _RouteSample | None = None
        best_distance = math.inf
        samples = reversed(self._route_history) if prefer_recent else self._route_history
        for sample in samples:
            if (
                self._active_lap_id is not None
                and sample.lap_id is not None
                and sample.lap_id != self._active_lap_id
            ):
                continue
            distance = math.dist(sample.position, position)
            if distance > ROUTE_MATCH_DISTANCE_METERS:
                continue
            if prefer_recent:
                return sample
            if distance < best_distance:
                best_distance = distance
                best_sample = sample
        return best_sample

    def _race_control_event(
        self,
        uncertainty: str,
        match: _RouteSample,
        position: tuple[float, float, float],
    ) -> dict:
        return {
            "uncertainty": uncertainty,
            "match_route_sample_index": match.index,
            "match_distance_m": math.dist(match.position, position),
            "match_current_lap": match.current_lap,
            "discard_after_current_lap": match.current_lap,
        }

    def _discard_route_history_after(self, index: int) -> None:
        self._route_history = [
            sample
            for sample in self._route_history
            if sample.lap_id != self._active_lap_id or sample.index <= index
        ]

    def _packet_lap_id(
        self,
        *,
        active_lap_signal: bool,
        lap_action: str,
        uncertainty: str | None,
    ) -> int | None:
        if not active_lap_signal or uncertainty in {"paused", "no_lap_signal"}:
            return None
        if lap_action == "finalize":
            return None
        return self._active_lap_id

    def _remember_packet(
        self,
        *,
        is_race_on: bool,
        position: tuple[float, float, float],
        current_lap: float,
        current_race_time: float,
        last_lap: float,
    ) -> None:
        if not is_race_on:
            return
        self._last_position = position
        self._last_current_lap = current_lap
        self._last_race_time = current_race_time
        self._max_race_time = max(self._max_race_time, current_race_time)
        self._last_lap_value = last_lap
        self._route_history.append(
            _RouteSample(
                index=self._next_route_sample_index,
                lap_id=self._active_lap_id,
                lap_number=self._active_lap_number,
                position=position,
                current_lap=current_lap,
                current_race_time=current_race_time,
            )
        )
        self._next_route_sample_index += 1
        if len(self._route_history) > ROUTE_HISTORY_MAX_SAMPLES:
            del self._route_history[: len(self._route_history) - ROUTE_HISTORY_MAX_SAMPLES]


def _has_active_lap_signal(
    *,
    is_race_on: bool,
    lap_number: int | None,
    current_lap: float,
    current_race_time: float,
) -> bool:
    if not is_race_on:
        return False
    return any(
        (
            lap_number is not None and lap_number > 0,
            current_lap > 0.0,
            current_race_time > 0.0,
        )
    )


def _boundary_confidence(
    *,
    uncertainty: str | None,
    lap_action: str,
    active_lap_signal: bool,
    session_action: str,
) -> str:
    if uncertainty in {"no_lap_signal", "paused", "teleport", "partial_lap", "rewind", "reset"}:
        return "uncertain"
    if lap_action != "none" or active_lap_signal:
        return "game_field"
    if session_action in {"start", "resume"}:
        return "heuristic"
    return "uncertain"


def _position(decoded: dict) -> tuple[float, float, float]:
    return (
        _as_float(decoded.get("PositionX")),
        _as_float(decoded.get("PositionY")),
        _as_float(decoded.get("PositionZ")),
    )


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _as_int(value: Any, default: int) -> int:
    parsed = _as_optional_int(value)
    return default if parsed is None else parsed


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return parsed if math.isfinite(parsed) else default


def _timer_matches(left: float, right: float) -> bool:
    return abs(left - right) <= TIMER_MATCH_TOLERANCE_SECONDS
