from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from lantern_house.domain.contracts import RecapBundle
from lantern_house.utils.time import isoformat


class TerminalRenderer:
    def __init__(self) -> None:
        self.console = Console(soft_wrap=True)
        self._color_map: dict[str, str] = {}

    def register_characters(self, color_map: dict[str, str]) -> None:
        self._color_map = dict(color_map)

    def render_message(
        self,
        *,
        when: datetime,
        speaker_slug: str,
        speaker_label: str,
        content: str,
        is_announcer: bool = False,
    ) -> None:
        timestamp = Text(f"[{isoformat(when)}] ", style="dim")
        if is_announcer:
            name = Text(speaker_label, style="bold cyan")
        else:
            name = Text(speaker_label, style=f"bold {self._color_map.get(speaker_slug, 'white')}")
        message = Text(" ") + Text(content, style="white")
        line = Text.assemble(timestamp, name, message)
        self.console.print(line)

    def render_thought_pulse(self, *, when: datetime, speaker_label: str, content: str) -> None:
        text = Text()
        text.append(f"[{isoformat(when)}] ", style="dim")
        text.append(f"[THOUGHT - {speaker_label.upper()}] ", style="bold magenta")
        text.append(content, style="italic bright_white")
        self.console.print(text)

    def render_recap(self, *, when: datetime, bundle: RecapBundle) -> None:
        self.console.print()
        self.console.print(
            Panel(
                self._format_recap_block(bundle.one_hour),
                title=f"RECAP 1H {isoformat(when)}",
                border_style="cyan",
            )
        )
        self.console.print(
            Panel(
                self._format_recap_block(bundle.twelve_hours),
                title="RECAP 12H",
                border_style="blue",
            )
        )
        self.console.print(
            Panel(
                self._format_recap_block(bundle.twenty_four_hours),
                title="RECAP 24H",
                border_style="green",
            )
        )
        self.console.print()

    def _format_recap_block(self, window) -> Text:
        text = Text()
        text.append(f"{window.headline}\n", style="bold")
        text.append("Changed: ", style="bold")
        text.append("; ".join(window.what_changed) or "No major shift.")
        text.append("\nEmotion: ", style="bold")
        text.append("; ".join(window.emotional_shifts) or "Steady tension.")
        text.append("\nClues: ", style="bold")
        text.append("; ".join(window.clues) or "No new clue.")
        text.append("\nQuestions: ", style="bold")
        text.append("; ".join(window.unresolved_questions) or "None.")
        text.append("\nTrust: ", style="bold")
        text.append(window.loyalty_status)
        text.append("\nRomance: ", style="bold")
        text.append(window.romance_status)
        text.append("\nWatch: ", style="bold")
        text.append(window.watch_next)
        return text
