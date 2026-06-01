"""Typer-based CLI."""

from __future__ import annotations

import os
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Optional

import click
import typer

from .api import AppContext
from .config_paths import ConfigContext, PROFILE_ENV, resolve_config_context
from .errors import DotfillError
from .logging_config import configure_logging
from .models import SessionState
from .open_paths import open_directory
from .resolver import build_app_state
from .server import run_server

app = typer.Typer(
    name="dotfill",
    help="Manage a project's `.env` file safely.",
    invoke_without_command=True,
    no_args_is_help=False,
)
config_app = typer.Typer(help="Show or open dotfill configuration paths.")
app.add_typer(config_app, name="config")


def _make_session() -> SessionState:
    return SessionState(token=secrets.token_urlsafe(32))


@app.callback()
def _main(
    ctx: typer.Context,
    env_path: Annotated[
        Optional[Path],
        typer.Option(
            "--env-path",
            help="Path to the .env file; overrides TOML target/default path",
        ),
    ] = None,
    config_root: Annotated[
        Optional[Path],
        typer.Option("--config-root", help="Root directory for dotfill config"),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option("--profile", help="Named profile under config root"),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable debug logging")
    ] = False,
) -> None:
    configure_logging(verbose=verbose)
    ctx.ensure_object(dict)
    entry_context: ConfigContext | None = ctx.obj.get("entry_config_context")
    if entry_context is not None:
        if config_root is not None or profile is not None:
            raise typer.BadParameter(
                "--config-root/--profile cannot be used with a direct config directory"
            )
        config_context = entry_context
    else:
        entry_config_root = ctx.obj.get("entry_config_root")
        entry_profile = ctx.obj.get("entry_profile")
        entry_default_profile = ctx.obj.get("entry_default_profile")
        effective_profile = profile if profile is not None else entry_profile
        if (
            effective_profile is None
            and entry_default_profile is not None
            and PROFILE_ENV not in os.environ
        ):
            effective_profile = entry_default_profile
        config_context = resolve_config_context(
            config_root=config_root if config_root is not None else entry_config_root,
            profile=effective_profile,
        )

    ctx.obj["env_path"] = (
        env_path if env_path is not None else ctx.obj.get("entry_env_path")
    )
    ctx.obj["config_context"] = config_context
    before_config_load = ctx.obj.get("entry_before_config_load")
    if before_config_load is not None:
        before_config_load(config_context)
    # If no subcommand is invoked, launch the dashboard.
    if ctx.invoked_subcommand is None:
        _launch_dashboard(ctx.obj["config_context"], ctx.obj["env_path"])


def _launch_dashboard(config_context: ConfigContext, env_path: Path | None) -> None:
    session = _make_session()
    context = AppContext(
        session=session,
        config_context=config_context,
        env_path=env_path,
    )
    try:
        run_server(context)
    except DotfillError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command()
def serve(
    ctx: typer.Context,
    port: Annotated[
        Optional[int], typer.Option("--port", help="Bind to a specific port")
    ] = None,
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Don't open the browser")
    ] = False,
) -> None:
    """Start the local web server (default action)."""
    env_path: Path | None = ctx.obj["env_path"]
    config_context: ConfigContext = ctx.obj["config_context"]
    session = _make_session()
    context = AppContext(
        session=session,
        config_context=config_context,
        env_path=env_path,
    )
    try:
        run_server(context, port=port, open_browser=not no_browser)
    except DotfillError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command()
def status(ctx: typer.Context) -> None:
    """Print a one-shot summary of effective state for this `.env`."""
    env_path: Path | None = ctx.obj["env_path"]
    config_context: ConfigContext = ctx.obj["config_context"]
    session = _make_session()
    try:
        state = build_app_state(
            config_context,
            session,
            env_path_override=env_path,
        )
    except DotfillError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"env: {state.env_path}")
    typer.echo(f"config: {state.config_context.config_dir}")
    if state.config_context.profile:
        typer.echo(f"profile: {state.config_context.profile}")
    typer.echo("identities:")
    for i in state.identities:
        eff = i.effective_value or "(unresolved)"
        typer.echo(f"  {i.name:<12} {eff}  [{i.source}]")
    typer.echo("derived:")
    for d in state.derived:
        cur = d.current_value or "(missing)"
        typer.echo(f"  {d.variable_name:<24} {cur}  [{d.status}]")
    typer.echo("services:")
    for s in state.services:
        token = s.masked_token or "(none)"
        typer.echo(f"  {s.display_name:<14} {s.token_var:<24} {token}  [{s.test_status}]")


@config_app.command("path")
def config_path(
    ctx: typer.Context,
    root: Annotated[bool, typer.Option("--root", help="Print config root")] = False,
    common: Annotated[
        bool, typer.Option("--common", help="Print config_common.toml path")
    ] = False,
    user: Annotated[bool, typer.Option("--user", help="Print config.toml path")] = False,
) -> None:
    """Print resolved config paths."""
    config_context: ConfigContext = ctx.obj["config_context"]
    if root:
        typer.echo(config_context.config_root)
    elif common:
        typer.echo(config_context.common_config_path)
    elif user:
        typer.echo(config_context.user_config_path)
    else:
        typer.echo(config_context.config_dir)


@config_app.command("open")
def config_open(ctx: typer.Context) -> None:
    """Open the resolved config directory."""
    config_context: ConfigContext = ctx.obj["config_context"]
    open_directory(config_context.config_dir, create=True)


def run_cli(
    *,
    argv: Sequence[str] | None = None,
    program_name: str = "dotfill",
    obj: dict[str, object] | None = None,
) -> int:
    """Run the Typer app and return an exit code without calling sys.exit."""
    try:
        result = app(
            args=list(argv) if argv is not None else None,
            prog_name=program_name,
            standalone_mode=False,
            obj={} if obj is None else obj,
        )
        if isinstance(result, int):
            return result
    except typer.Exit as exc:
        return int(exc.exit_code or 0)
    except click.ClickException as exc:
        exc.show(file=sys.stderr)
        return int(exc.exit_code)
    except DotfillError as exc:
        typer.echo(f"error: {exc}", err=True)
        return 2
    except Exception as exc:
        show = getattr(exc, "show", None)
        exit_code = getattr(exc, "exit_code", None)
        if callable(show) and isinstance(exit_code, int):
            show(file=sys.stderr)
            return exit_code
        raise
    except KeyboardInterrupt:
        return 130
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return 1
    return 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
