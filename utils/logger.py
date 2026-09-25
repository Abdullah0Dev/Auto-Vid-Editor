"""Consistent, colored console output."""
from rich.console import Console

console = Console()


class _Log:
    def info(self, msg):      console.print(f"[cyan]ℹ[/cyan]  {msg}")
    def ok(self, msg):        console.print(f"[green]✓[/green]  {msg}")
    def warn(self, msg):      console.print(f"[yellow]⚠[/yellow]  {msg}")
    def error(self, msg):     console.print(f"[red]✗[/red]  {msg}")
    def debug(self, msg):     console.print(f"[dim]{msg}[/dim]")
    def step(self, n, t, msg): console.rule(f"[bold]Step {n}/{t} — {msg}")

    def raw(self, text: str):
        """Print raw text with no markup interpretation."""
        console.print(text, end="", markup=False, highlight=False)


log = _Log()