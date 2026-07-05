from __future__ import annotations

from dataclasses import dataclass, field

from config import settings
from domain.user.session.manager import Session, Turn


@dataclass
class PreparedContext:
    summary: str
    recent_turns: list[Turn] = field(default_factory=list)
    was_trimmed: bool = False


class ContextManager:
    """Prepare bounded session context for prompt building."""

    def prepare(self, session: Session, *, current_message: str | None = None) -> PreparedContext:
        turns = list(session.turns)

        # 当前用户消息会单独传入推理循环。
        # 若为同一条用户消息，需排除末尾轮次，避免内容重复。
        if current_message is not None and turns:
            last = turns[-1]
            if last.role == "user" and last.content == current_message:
                turns = turns[:-1]

        max_turns = max(1, settings.max_context_turns)
        was_trimmed = len(turns) > max_turns
        if len(turns) > max_turns:
            turns = turns[-max_turns:]

        max_chars = max(200, settings.max_context_chars)
        total_chars = sum(len(turn.content) for turn in turns)
        if total_chars > max_chars:
            trimmed: list[Turn] = []
            running = 0
            for turn in reversed(turns):
                turn_len = len(turn.content)
                if trimmed and running + turn_len > max_chars:
                    was_trimmed = True
                    break
                trimmed.append(turn)
                running += turn_len
            turns = list(reversed(trimmed))
            if len(turns) < len(session.turns):
                was_trimmed = True

        summary = session.summary.strip()
        return PreparedContext(summary=summary, recent_turns=turns, was_trimmed=was_trimmed)
