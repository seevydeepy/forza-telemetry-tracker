"""Capture state machine and rolling pre-buffer for live telemetry."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from math import isfinite, sqrt
from typing import Any


class CaptureMode(str, Enum):
    """How the tracker decides when packets should be recorded."""

    AUTO = "auto"
    MANUAL = "manual"


class CapturePhase(str, Enum):
    """Recording phase tracked independently from listener health."""

    IDLE = "idle"
    RECEIVING_NOT_RECORDING = "receiving_not_recording"
    RECORDING = "recording"


_MIN_SPEED_MPS = 0.5
_MIN_POSITION_DELTA_METERS = 0.1
_MIN_VALID_PI = 100
_MAX_VALID_PI = 999
_VALID_CAR_CLASSES = set(range(8))
_VALID_DRIVETRAINS = {0, 1, 2}


@dataclass(frozen=True)
class _BufferedPacket:
    raw: bytes
    race_on: bool


class CaptureStateMachine:
    """Decide whether observed FH Data Out packets should be recorded.

    The state machine is intentionally small: it does not own sockets, storage,
    sessions, or lap detection. It only tracks packet receipt, recording state,
    and a rolling packet pre-buffer for callers to flush when a recording starts.
    """

    def __init__(self, mode: str = "auto", prebuffer_packets: int = 300):
        capacity = int(prebuffer_packets)
        if capacity < 0:
            raise ValueError("prebuffer_packets must be non-negative")

        self.mode = _coerce_mode(mode)
        self.phase = CapturePhase.IDLE
        self._prebuffer: deque[_BufferedPacket] = deque(maxlen=capacity)
        self._packets_observed = 0
        self._recorded_packet_observations = 0
        self._last_decoded: dict[str, Any] | None = None
        self._last_packet_race_on: bool | None = None
        self._last_timestamp_ms: int | None = None
        self._last_auto_signals = _empty_auto_signals()
        self._last_auto_reason = "waiting_for_packet"

    def set_mode(self, mode: str) -> None:
        """Switch capture mode and stop active recordings on real mode changes."""

        new_mode = _coerce_mode(mode)
        if new_mode == self.mode:
            return

        self.mode = new_mode
        self._prebuffer.clear()
        if self.phase == CapturePhase.RECORDING:
            self.phase = (
                CapturePhase.RECEIVING_NOT_RECORDING
                if self._packets_observed
                else CapturePhase.IDLE
            )

        if self.mode == CaptureMode.AUTO:
            self._last_decoded = None
            self._last_auto_signals = _empty_auto_signals()
            self._last_auto_reason = "waiting_for_packet"
        if self.mode == CaptureMode.MANUAL and self.phase != CapturePhase.RECORDING:
            self._last_auto_reason = "manual_waiting_for_start"

    def start_manual(self) -> list[bytes]:
        """Start manual recording and return pre-buffered packets once."""

        if self.mode != CaptureMode.MANUAL:
            self.set_mode(CaptureMode.MANUAL)
        if self.phase == CapturePhase.RECORDING:
            return []

        packets_to_flush = [packet.raw for packet in self._prebuffer]
        self._prebuffer.clear()
        self.phase = CapturePhase.RECORDING
        return packets_to_flush

    def stop_manual(self) -> None:
        """Stop active manual recording without affecting auto capture."""

        if self.mode == CaptureMode.MANUAL and self.phase == CapturePhase.RECORDING:
            self.phase = (
                CapturePhase.RECEIVING_NOT_RECORDING
                if self._packets_observed
                else CapturePhase.IDLE
            )

    def observe_packet(self, raw: bytes, decoded: dict) -> tuple[bool, list[bytes]]:
        """Observe one packet and return recording intent plus one-time flush data.

        The current packet is never included in the flush list. Callers should
        write ``packets_to_flush_first`` first, then write ``raw`` when
        ``should_record`` is true.
        """

        self._packets_observed += 1
        previous = self._last_decoded

        if self.phase == CapturePhase.RECORDING:
            self._recorded_packet_observations += 1
            self._remember_packet(decoded)
            return True, []

        if self.mode == CaptureMode.AUTO and self._should_auto_start(decoded, previous):
            packets_to_flush = [
                packet.raw
                for packet in self._prebuffer
                if packet.race_on
            ]
            self._prebuffer.clear()
            self.phase = CapturePhase.RECORDING
            self._recorded_packet_observations += 1
            self._remember_packet(decoded)
            return True, packets_to_flush

        self.phase = CapturePhase.RECEIVING_NOT_RECORDING
        self._prebuffer.append(
            _BufferedPacket(
                raw=bytes(raw),
                race_on=_int_field(decoded, "IsRaceOn") > 0,
            )
        )
        if self.mode == CaptureMode.MANUAL:
            self._last_auto_reason = "manual_waiting_for_start"
        self._remember_packet(decoded)
        return False, []

    def status(self) -> dict:
        """Return state grouped by listener, packet receipt, and recording concerns."""

        recording_active = self.phase == CapturePhase.RECORDING
        has_received_packets = self._packets_observed > 0
        return {
            "mode": self.mode.value,
            "phase": self.phase.value,
            "packet_receipt": {
                "state": "receiving" if has_received_packets else "waiting",
                "has_received_packets": has_received_packets,
                "packets_observed": self._packets_observed,
                "last_timestamp_ms": self._last_timestamp_ms,
                "last_is_race_on": self._last_packet_race_on,
                "last_packet_type": _packet_type_label(self._last_packet_race_on),
            },
            "recording": {
                "active": recording_active,
                "phase": self.phase.value,
                "mode": self.mode.value,
                "total_live_packets_recorded_excluding_prebuffer": self._recorded_packet_observations,
            },
            "prebuffer": {
                "capacity": self._prebuffer.maxlen or 0,
                "size": len(self._prebuffer),
            },
            "auto_detection": {
                "last_signals": dict(self._last_auto_signals),
                "last_reason": self._last_auto_reason,
            },
        }

    def _should_auto_start(self, decoded: dict, previous: dict | None) -> bool:
        signals = {
            "race_on": _int_field(decoded, "IsRaceOn") > 0,
            "moving": _has_movement_signal(decoded, previous),
            "valid_vehicle": _has_valid_vehicle_signal(decoded),
            "race_time_progressing": _has_race_time_progression(decoded, previous),
        }
        self._last_auto_signals = signals
        missing = [name for name, present in signals.items() if not present]
        if missing:
            self._last_auto_reason = "waiting_for_" + ",".join(missing)
            return False

        self._last_auto_reason = "race_like_packet"
        return True

    def _remember_packet(self, decoded: dict) -> None:
        self._last_decoded = dict(decoded)
        self._last_packet_race_on = _int_field(decoded, "IsRaceOn") > 0
        self._last_timestamp_ms = _int_field(decoded, "TimestampMS")


def _coerce_mode(mode: str | CaptureMode) -> CaptureMode:
    if isinstance(mode, CaptureMode):
        return mode
    try:
        return CaptureMode(str(mode).lower())
    except ValueError as exc:
        raise ValueError("mode must be 'auto' or 'manual'") from exc


def _empty_auto_signals() -> dict[str, bool]:
    return {
        "race_on": False,
        "moving": False,
        "valid_vehicle": False,
        "race_time_progressing": False,
    }


def _packet_type_label(race_on: bool | None) -> str:
    if race_on is True:
        return "race"
    if race_on is False:
        return "non_race"
    return "unknown"


def _int_field(decoded: dict, name: str, default: int = 0) -> int:
    try:
        return int(decoded.get(name, default))
    except (TypeError, ValueError):
        return default


def _float_field(decoded: dict, name: str, default: float = 0.0) -> float:
    try:
        value = float(decoded.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if isfinite(value) else default


def _has_valid_vehicle_signal(decoded: dict) -> bool:
    car_class = _int_field(decoded, "CarClass", default=-1)
    performance_index = _int_field(decoded, "CarPerformanceIndex")
    drivetrain = _int_field(decoded, "DrivetrainType", default=-1)
    rpm = _float_field(decoded, "CurrentEngineRpm")

    return (
        car_class in _VALID_CAR_CLASSES
        and _MIN_VALID_PI <= performance_index <= _MAX_VALID_PI
        and drivetrain in _VALID_DRIVETRAINS
        and rpm > 0.0
    )


def has_race_packet_signal(decoded: dict) -> bool:
    """Return whether a packet looks like active race telemetry for warnings."""

    return _int_field(decoded, "IsRaceOn") > 0 and _has_valid_vehicle_signal(decoded)


def _has_movement_signal(decoded: dict, previous: dict | None) -> bool:
    speed = _float_field(decoded, "Speed")
    if speed > _MIN_SPEED_MPS:
        return True

    if previous is None:
        return False

    return _position_delta(decoded, previous) > _MIN_POSITION_DELTA_METERS


def _position_delta(decoded: dict, previous: dict) -> float:
    dx = _float_field(decoded, "PositionX") - _float_field(previous, "PositionX")
    dy = _float_field(decoded, "PositionY") - _float_field(previous, "PositionY")
    dz = _float_field(decoded, "PositionZ") - _float_field(previous, "PositionZ")
    return sqrt(dx * dx + dy * dy + dz * dz)


def _has_race_time_progression(decoded: dict, previous: dict | None) -> bool:
    if previous is None:
        return False

    current = _float_field(decoded, "CurrentRaceTime")
    if current <= 0.0:
        return False

    previous_time = _float_field(previous, "CurrentRaceTime")
    return current > previous_time


__all__ = [
    "CaptureMode",
    "CapturePhase",
    "CaptureStateMachine",
    "has_race_packet_signal",
]
