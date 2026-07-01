from __future__ import annotations
import asyncio
import typer
import logging
from rich.console import Console
from rich.prompt import Prompt
from app import build_agent
from config import settings
from core.logging_config import init_from_settings
app = typer.Typer(add_completion=False)
console = Console()
logger = logging.getLogger(__name__)

init_from_settings()

@app.command()
def chat(session_id: str = "default", user_id: str | None = None) -> None:
    """Start an interactive Claw chat session."""

    async def _run() -> None:
        agent = build_agent()
        logger.info("CLI chat session started: session_id=%s user_id=%s", session_id, user_id or session_id)
        console.print("[bold cyan]Claw[/bold cyan] interactive mode. Type `exit` to quit.")
        while True:
            text = Prompt.ask("[bold green]You[/bold green]").strip()
            if text.lower() in {"exit", "quit"}:
                logger.info("CLI chat session ended: session_id=%s user_id=%s", session_id, user_id or session_id)
                break
            result = await agent.chat(session_id=session_id, user_id=user_id, message=text)
            console.print(f"[bold magenta]Claw[/bold magenta] {result['reply']}")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
