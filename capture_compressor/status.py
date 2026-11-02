"""What the engine is doing right now, as shown in the tray."""

from __future__ import annotations

from dataclasses import dataclass

IDLE = "idle"
COMPRESSING = "compressing"
PAUSED = "paused"
ERROR = "error"


@dataclass(frozen=True)
class Status:
    state: str = IDLE
    current_file: str = ""
    queued_count: int = 0
    error: str = ""
    active_encoder: str = ""

    def describe(self) -> str:
        if self.state == ERROR:
            return f"Error: {self.error}"
        description = {
            IDLE: "Idle",
            PAUSED: "Paused",
            COMPRESSING: f"Compressing {self.current_file}",
        }[self.state]
        if self.queued_count:
            description += f" - {self.queued_count} queued"
        return description


def decide_state(current_file: str, error: str, paused: bool) -> str:
    if current_file:
        return COMPRESSING
    if error:
        return ERROR
    if paused:
        return PAUSED
    return IDLE
