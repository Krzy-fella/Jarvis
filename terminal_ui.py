"""Readable, terminal-width-aware conversation output."""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from presentation import readable_output

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
    return console.input("[bold green]You › [/]").strip()
