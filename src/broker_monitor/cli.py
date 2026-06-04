from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Config, load_config
from .monitor import SlaveStatus, check_broker, get_quarantined
from .notifier import send_alert
from .restarter import ServiceInfo, resolve_service, restart_service

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

app = typer.Typer(
    name="broker-monitor",
    help="Monitora o Broker Protheus e reinicia slaves em quarentena.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"broker-monitor [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Exibe a versao",
    ),
) -> None:
    pass


@app.command()
def run(
    config_path: Path = typer.Option(
        Path("config.json"), "--config", "-c", help="Caminho do arquivo config.json",
    ),
    daemon: bool = typer.Option(
        False, "--daemon", "-d",
        help="Executa em loop continuo (nao use com Task Scheduler)",
    ),
    interval: int = typer.Option(
        5, "--interval", "-i",
        help="Intervalo em minutos entre verificacoes (apenas com --daemon)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Verifica e exibe o status sem reiniciar servicos nem enviar emails",
    ),
) -> None:
    """
    Verifica o Broker e reinicia slaves em quarentena.

    Modos de uso:

    \b
    # One-shot (ideal para Task Scheduler)
    broker-monitor run --config config.json

    \b
    # Daemon -- loop continuo a cada 5 minutos
    broker-monitor run --config config.json --daemon --interval 5
    """
    if not config_path.exists():
        console.print(f"[red]Config nao encontrado:[/red] {config_path}")
        raise typer.Exit(1)

    try:
        cfg = load_config(config_path)
    except Exception as exc:
        console.print(f"[red]Erro ao ler config:[/red] {exc}")
        raise typer.Exit(1)

    logger = _setup_logger(cfg.log_dir, cfg.log_retention_days)

    if daemon:
        console.print(
            f"\n[bold cyan]broker-monitor {__version__}[/bold cyan] -- modo daemon\n"
            f"Verificando a cada [bold]{interval}[/bold] minuto(s). Ctrl+C para encerrar.\n"
        )
        logger.info(f"Daemon iniciado (intervalo={interval}min, dry_run={dry_run})")
        try:
            while True:
                _run_once(cfg, dry_run, logger)
                console.print(f"\n[dim]Aguardando {interval} minuto(s)...[/dim]\n")
                time.sleep(interval * 60)
        except KeyboardInterrupt:
            console.print("\n[yellow]Daemon encerrado.[/yellow]")
            logger.info("Daemon encerrado pelo usuario.")
    else:
        logger.info(f"Execucao iniciada (dry_run={dry_run})")
        success = _run_once(cfg, dry_run, logger)
        raise typer.Exit(0 if success else 1)


@app.command()
def check(
    config_path: Path = typer.Option(
        Path("config.json"), "--config", "-c", help="Caminho do arquivo config.json",
    ),
) -> None:
    """Exibe o status atual de todos os slaves sem realizar nenhuma acao."""
    if not config_path.exists():
        console.print(f"[red]Config nao encontrado:[/red] {config_path}")
        raise typer.Exit(1)

    try:
        cfg = load_config(config_path)
    except Exception as exc:
        console.print(f"[red]Erro ao ler config:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"\n[cyan]Verificando:[/cyan] {cfg.broker_url}\n")
    reachable, slaves = check_broker(cfg.broker_url)

    if not reachable:
        console.print("[red]Broker inacessivel.[/red]")
        raise typer.Exit(1)

    if not slaves:
        console.print("[yellow]Nenhum slave encontrado na pagina do broker.[/yellow]")
        raise typer.Exit(0)

    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("Slave (IP:Porta)")
    table.add_column("Quarentena")

    for s in slaves:
        status = f"[red]{s.quarantine}[/red]" if s.is_quarantined else "[green]OK[/green]"
        table.add_row(s.address, status)

    console.print(table)
    quarantined = get_quarantined(slaves)

    if quarantined:
        console.print(f"\n[red]{len(quarantined)} slave(s) em quarentena.[/red]")
        raise typer.Exit(1)
    else:
        console.print(f"\n[green]Todos os {len(slaves)} slave(s) OK.[/green]")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_once(cfg: Config, dry_run: bool, logger: logging.Logger) -> bool:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.rule(f"[dim]{ts}[/dim]", style="dim")
    console.print(f"[cyan]Verificando:[/cyan] {cfg.broker_url}")
    logger.info(f"Verificando broker: {cfg.broker_url}")

    reachable, slaves = check_broker(cfg.broker_url)

    if not reachable:
        console.print("[red]Broker inacessivel.[/red]")
        logger.error("Broker inacessivel.")
        if not dry_run:
            _try_send(cfg, [], [], [], [], broker_unreachable=True, logger=logger)
        return False

    logger.info(f"Broker online. Slaves encontrados: {len(slaves)}")
    console.print(f"[green]Broker online.[/green] {len(slaves)} slave(s) encontrado(s).")

    quarantined = get_quarantined(slaves)
    if not quarantined:
        console.print("[green]Nenhum slave em quarentena.[/green]")
        logger.info("Nenhum slave em quarentena.")
        return True

    console.print(f"\n[red]{len(quarantined)} slave(s) em quarentena:[/red]")
    for s in quarantined:
        console.print(f"  [red]--[/red] {s.address}  [{s.quarantine}]")
        logger.warning(f"Quarentena: {s.address} | {s.quarantine}")

    if dry_run:
        console.print("\n[yellow]Modo dry-run: nenhum restart executado.[/yellow]")
        logger.info("dry-run ativo: sem restart.")
        return True

    if not cfg.auto_restart:
        console.print("\n[yellow]autoRestart=false: nenhum restart executado.[/yellow]")
        logger.info("autoRestart=false: sem restart.")
        return True

    restarted: list[ServiceInfo] = []
    failed: list[ServiceInfo] = []
    skipped: list[str] = []

    for slave in quarantined:
        info = resolve_service(
            slave.address,
            cfg.service_name_pattern,
            cfg.slave_range.min,
            cfg.slave_range.max,
        )
        if not info:
            console.print(f"  [yellow]Fora do mapeamento, pulando:[/yellow] {slave.address}")
            logger.warning(f"Fora do mapeamento: {slave.address}")
            skipped.append(slave.address)
            continue

        console.print(f"\n  Reiniciando [bold]{info.service_name}[/bold] ({info.address})...")
        logger.info(f"Reiniciando servico: {info.service_name}")

        ok, state = restart_service(info.service_name, cfg.start_timeout_seconds)
        if ok:
            console.print(f"  [green]OK[/green] -- {info.service_name} -> {state}")
            logger.info(f"Restart OK: {info.service_name} -> {state}")
            restarted.append(info)
        else:
            console.print(f"  [red]FALHOU[/red] -- {info.service_name}: {state}")
            logger.error(f"Restart falhou: {info.service_name} | {state}")
            failed.append(info)

    console.print(
        f"\n[bold]Resumo:[/bold] "
        f"[green]Reiniciados: {len(restarted)}[/green]  "
        f"[red]Falhas: {len(failed)}[/red]  "
        f"[yellow]Pulados: {len(skipped)}[/yellow]"
    )
    logger.info(
        f"Resumo: reiniciados={len(restarted)} falhas={len(failed)} pulados={len(skipped)}"
    )

    if restarted or failed:
        _try_send(cfg, quarantined, restarted, failed, skipped, logger=logger)

    return len(failed) == 0


def _try_send(
    cfg: Config,
    quarantined: list[SlaveStatus],
    restarted: list[ServiceInfo],
    failed: list[ServiceInfo],
    skipped: list[str],
    logger: logging.Logger,
    broker_unreachable: bool = False,
) -> None:
    if not cfg.email.enabled:
        return
    try:
        send_alert(cfg.email, quarantined, restarted, failed, skipped, broker_unreachable)
        console.print("[green]Email de alerta enviado.[/green]")
        logger.info("Email enviado.")
    except Exception as exc:
        console.print(f"[yellow]Falha ao enviar email:[/yellow] {exc}")
        logger.error(f"Falha ao enviar email: {exc}")


def _setup_logger(log_dir: Path, retention_days: int) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"broker_monitor_{datetime.now().strftime('%Y%m%d')}.log"

    logger = logging.getLogger("broker_monitor")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = TimedRotatingFileHandler(
            log_file, when="midnight", backupCount=retention_days, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)

    return logger
