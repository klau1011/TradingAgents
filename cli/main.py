import sys
from enum import StrEnum
from typing import Annotated

import typer
from rich.markup import escape

from cli.display import console
from cli.models import AnalystType, AssetType
from cli.prompts import filter_analysts_for_asset_type, parse_analysts
from cli.run import run_analysis
from tradingagents.backtest import iter_grid, run_backtest, summarize
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.openai_client import SIGNED_IN_PROVIDERS
from tradingagents.portfolio import load_portfolio

# prompt_toolkit's win32 output module is importable only on Windows (it asserts
# the platform at import time), so gate on the platform rather than catching the
# failure — that way a genuinely broken prompt_toolkit on Windows still surfaces
# instead of silently disabling the handler below. Off Windows this stays an
# empty tuple, which `except` accepts and never matches (#1138).
if sys.platform == "win32":  # pragma: no cover - platform dependent
    from prompt_toolkit.output.win32 import NoConsoleScreenBufferError

    _NO_CONSOLE_ERRORS: tuple[type[BaseException], ...] = (NoConsoleScreenBufferError,)
else:
    _NO_CONSOLE_ERRORS = ()

app = typer.Typer(
    name="TradingAgents",
    help="TradingAgents CLI: Multi-Agents LLM Financial Trading Framework",
    add_completion=True,  # Enable shell completion
)


@app.callback(invoke_without_command=True)
def analyze(
    ctx: typer.Context,
    checkpoint: bool | None = typer.Option(
        None,
        "--checkpoint/--no-checkpoint",
        help="Enable/disable checkpoint-resume (save state after each node so a "
        "crashed run can resume). Omit to honor TRADINGAGENTS_CHECKPOINT_ENABLED.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running (force fresh start).",
    ),
    portfolio: str = typer.Option(
        None,
        "--portfolio",
        help="JSON file with current holdings and cash, so the trader, risk and "
        "portfolio agents size against your actual position.",
    ),
    ticker: str = typer.Option(None, "--ticker", help="Ticker to analyze, e.g. NVDA or 0700.HK; skips the prompt"),
    date: str = typer.Option(None, "--date", help="Analysis date, YYYY-MM-DD; skips the prompt"),
    analysts: str = typer.Option(
        None, "--analysts", help="Comma-separated analysts, e.g. market,news; skips the prompt"
    ),
    save: bool | None = typer.Option(
        None, "--save/--no-save", help="Save the report under results_dir without asking"
    ),
    show: bool | None = typer.Option(
        None, "--show/--no-show", help="Show the full report at the end without asking"
    ),
    html: bool | None = typer.Option(
        None, "--html/--no-html",
        help="Save the report as one HTML page too, complete_report.html, without asking (default: yes)",
    ),
):
    """Run an analysis. This is what a bare `tradingagents` does.

    Flags answer their questions; with provider, models, depth and language also
    set through TRADINGAGENTS_* variables, the run asks nothing.
    """
    if ctx.invoked_subcommand is not None:
        return
    if clear_checkpoints:
        from tradingagents.graph.checkpointer import clear_all_checkpoints
        n = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
        console.print(f"[yellow]Cleared {n} checkpoint(s).[/yellow]")
    portfolio_context = None
    if portfolio:
        try:
            portfolio_context = load_portfolio(portfolio)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from None

    try:
        flags = {"ticker": ticker, "date": date, "analysts": analysts, "save": save, "show": show, "html": html}
        run_analysis(checkpoint=checkpoint, portfolio=portfolio_context, flags=flags)
    except _NO_CONSOLE_ERRORS:
        # A terminal with no console buffer cannot host the interactive prompts.
        # Emit one actionable line on stderr instead of a prompt_toolkit
        # traceback; plain text, since rich may not render here either (#1138).
        typer.echo(
            "Error: no Windows console available. The interactive CLI needs a real "
            "console buffer — run it from Windows Terminal, PowerShell, or cmd.exe "
            "rather than a piped or embedded terminal.",
            err=True,
        )
        raise typer.Exit(code=1) from None


@app.command()
def backtest(
    tickers: str = typer.Argument(..., help="Comma-separated tickers, e.g. NVDA,AAPL"),
    start: str = typer.Option(..., "--start", help="First analysis date, YYYY-MM-DD"),
    end: str = typer.Option(..., "--end", help="Last analysis date, YYYY-MM-DD"),
    every: int = typer.Option(7, "--every", help="Days between analysis dates"),
    analysts: str = typer.Option(
        None, "--analysts", help="Comma-separated analysts to run: market, sentiment, news, fundamentals; omit for all the asset type allows"
    ),
    asset_type: str = typer.Option("stock", "--asset-type", help="stock or crypto"),
    portfolio: str = typer.Option(
        None, "--portfolio", help="JSON file with holdings and cash, held constant across the grid"
    ),
    run_id: str = typer.Option(
        None, "--run-id", help="Continue an earlier sweep: its cells are skipped and its log reused"
    ),
):
    """Score past decisions over a grid of tickers and dates."""

    try:
        dates = iter_grid(start, end, every)
        book = load_portfolio(portfolio) if portfolio else None
        kind = AssetType(asset_type.strip().lower())
        # The analysts are named and checked as for an analysis; without a
        # choice, every analyst the asset type allows runs.
        chosen = (parse_analysts(analysts, kind) if analysts
                  else filter_analysts_for_asset_type(list(AnalystType), kind))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    names = [t.strip() for t in tickers.split(",") if t.strip()]
    if not names:
        console.print("[red]No ticker to analyze; pass them comma-separated, e.g. NVDA,AAPL[/red]")
        raise typer.Exit(code=1)

    def show_progress(done, total, ticker, date):
        console.print(f"[dim][{done}/{total}] {ticker} {date}[/dim]")

    kwargs = {"asset_type": kind.value, "portfolio": book, "run_id": run_id, "progress": show_progress,
              "selected_analysts": [a.value for a in chosen]}

    try:
        result = run_backtest(names, dates, DEFAULT_CONFIG, **kwargs)
    except Exception as exc:  # a missing key or an unknown analyst is a setup error
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(summarize(result).render())
    console.print(f"\nRan {result.cells_run} cells, skipped {result.skipped}. Log: {result.log_path}")
    console.print(f"Continue or settle this sweep: --run-id {result.run_id}")
    for ticker, date, reason in result.failures:
        console.print(f"[yellow]failed:[/yellow] {ticker} {date}: {reason}")
    for ticker, reason in result.settlement_failures:
        console.print(f"[yellow]unsettled:[/yellow] {ticker}: {reason}")


# The plans `login` and `logout` take: the providers signed in to, not keyed.
Plan = StrEnum("Plan", {name: name for name in SIGNED_IN_PROVIDERS})


@app.command()
def login(plan: Annotated[Plan, typer.Argument(help="The plan to sign in with")]):
    """Sign in with your ChatGPT Plus or Pro plan, for the chatgpt provider."""
    from tradingagents.llm_clients import chatgpt_auth

    try:
        # One unwrapped line, so the sign-in address can be copied whole.
        email = chatgpt_auth.sign_in(
            say=lambda line: console.print(line, soft_wrap=True, markup=False, highlight=False))
    except chatgpt_auth.ChatGPTAuthError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(code=1) from None
    console.print(f"[green]Signed in to ChatGPT as {escape(email)}.[/green]")


@app.command()
def logout(plan: Annotated[Plan, typer.Argument(help="The plan to sign out of")]):
    """Sign out of your ChatGPT plan: revoke this machine's access and forget it."""
    from tradingagents.llm_clients import chatgpt_auth

    outcome = chatgpt_auth.sign_out()
    if outcome == "revoked":
        console.print("Signed out of ChatGPT.")
    elif outcome == "forgotten":
        console.print("[yellow]Signed out here, but OpenAI could not be reached to revoke the sign-in; "
                      "it stays valid at OpenAI until it expires.[/yellow]")
    else:
        console.print("Not signed in to ChatGPT.")


_TICKERS_ARG = typer.Argument(..., help="Tickers to evaluate.")


@app.command()
def evaluate(
    tickers: list[str] = _TICKERS_ARG,
    from_date: str = typer.Option(..., "--from", help="Backtest start date, YYYY-MM-DD."),
    to_date: str = typer.Option(..., "--to", help="Backtest end date, YYYY-MM-DD."),
    cadence_days: int = typer.Option(
        21, "--cadence-days",
        help="Business days between sampled trade dates (~21 = monthly).",
    ),
    holding_days: int = typer.Option(
        5, "--holding-days",
        help="Forward window (trading days) for the realized return/alpha outcome.",
    ),
    analysts: str = typer.Option(
        "market,news,fundamentals", "--analysts",
        help="Comma-separated analysts. Default excludes 'social' to avoid "
        "look-ahead leakage from StockTwits/Reddit.",
    ),
    include_social: bool = typer.Option(
        False, "--include-social",
        help="Add the social/sentiment analyst (WARNING: leaks 'now' social data "
        "into historical dates).",
    ),
    cost: float = typer.Option(
        0.0, "--cost",
        help="Round-trip transaction cost per directional call, as a return "
        "fraction (0.001 = 10 bps).",
    ),
    out: str | None = typer.Option(
        None, "--out",
        help="Output directory (default ~/.tradingagents/backtests/<stamp>/).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the cost-confirmation prompt."),
):
    """Backtest the analysis: score ratings vs forward alpha over a date range."""
    from datetime import datetime
    from pathlib import Path

    from tradingagents.evaluation import (
        render_report,
        run_backtest,
        sample_dates,
        summarize,
    )

    selected = [a.strip().lower() for a in analysts.split(",") if a.strip()]
    if include_social and "social" not in selected:
        selected.append("social")
    if "social" in selected:
        console.print(
            "[yellow]WARNING:[/yellow] the social analyst reads 'now' (StockTwits/"
            "Reddit), which leaks future information into historical backtest dates."
        )

    dates = sample_dates(from_date, to_date, cadence_days)
    if not dates:
        console.print("[red]No business days in the given range.[/red]")
        raise typer.Exit(1)
    n_points = len(tickers) * len(dates)

    if out:
        out_dir = Path(out)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path.home() / ".tradingagents" / "backtests" / stamp
    results_path = out_dir / "results.jsonl"

    console.print(
        f"[bold]{n_points}[/bold] evaluation points "
        f"({len(tickers)} ticker(s) × {len(dates)} dates) — analysts: {', '.join(selected)}."
    )
    console.print(
        "[yellow]Each point is a full multi-agent LLM run (minutes and $ each).[/yellow]"
    )
    if not yes and not typer.confirm("Proceed?", default=False):
        raise typer.Abort()

    rows = run_backtest(
        tickers, from_date, to_date,
        cadence_days=cadence_days,
        holding_days=holding_days,
        selected_analysts=selected,
        config=DEFAULT_CONFIG.copy(),
        results_path=results_path,
    )

    report = render_report(
        summarize(rows, cost=cost),
        meta={
            "tickers": ", ".join(tickers),
            "range": f"{from_date} -> {to_date}",
            "cadence_days": cadence_days,
            "holding_days": holding_days,
            "analysts": ", ".join(selected),
        },
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    console.print()
    console.print(report)
    console.print(f"\n[green]Saved:[/green] {results_path}  |  {out_dir / 'report.md'}")


if __name__ == "__main__":
    app()
