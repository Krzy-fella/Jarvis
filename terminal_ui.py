"""Readable, terminal-width-aware conversation output."""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from presentation import readable_output
from privacy import redact

_message_history = []

console = Console()


def show_reply(message: str) -> None:
    console.print()
    console.print(Panel(
        Markdown(message or "(No text response)", code_theme="monokai"),
        title="JARVIS", title_align="left", border_style="cyan",
        padding=(1, 2), width=min(console.width, 100),
    ))
    console.print()


def show_output(tool: str, output: str) -> None:
    console.print(Panel(
        Text(readable_output(output)), title=Text(f"Result · {tool}"), title_align="left",
        border_style="dim", padding=(1, 2), width=min(console.width, 100),
    ))
    console.print()


def show_error(message: str) -> None:
    console.print()
    console.print(Text(f"Error: {message}", style="red"))
    console.print()


def read_message() -> str:
    """Readline provides editable Up/Down recall without recording approvals/menus.

    History is process-local, bounded and redacted; never written to a history file.
    Python builds without readline retain the ordinary input fallback.
    """
    try:
        import readline
    except ImportError:
        return console.input("[bold green]You › [/]").strip()
    previous = [readline.get_history_item(i + 1) for i in range(readline.get_current_history_length())]
    readline.clear_history()
    readline.set_auto_history(False)
    for message in _message_history:
        readline.add_history(message)
    try:
        value = console.input("[bold green]You › [/]").strip()
        saved = redact(value)
        if value.lower() == '/forget all':
            _message_history.clear()
        elif saved and (not _message_history or _message_history[-1] != saved):
            _message_history.append(saved)
            del _message_history[:-100]
        return value
    finally:
        readline.clear_history()
        for item in previous:
            readline.add_history(item)
        readline.set_auto_history(True)
