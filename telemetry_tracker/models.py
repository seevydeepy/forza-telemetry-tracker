"""Shared telemetry tracker data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ListenerState = Literal["starting", "waiting", "receiving", "recording", "error"]
ToastLevel = Literal["info", "success", "warning", "error"]


@dataclass(frozen=True)
class ListenerStatus:
    state: ListenerState
    udp_host: str
    udp_port: int
    packets_received: int = 0
    packets_recorded: int = 0
    message: str = "waiting for telemetry"

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "udp_host": self.udp_host,
            "udp_port": self.udp_port,
            "packets_received": self.packets_received,
            "packets_recorded": self.packets_recorded,
            "message": self.message,
        }


@dataclass(frozen=True)
class ToastEvent:
    level: ToastLevel
    message: str
    sticky: bool = False

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "message": self.message,
            "sticky": self.sticky,
        }
