from __future__ import annotations

import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import EmailConfig
from .monitor import SlaveStatus
from .restarter import ServiceInfo


def send_alert(
    cfg: EmailConfig,
    quarantined: list[SlaveStatus],
    restarted: list[ServiceInfo],
    failed: list[ServiceInfo],
    skipped: list[str],
    broker_unreachable: bool = False,
    env_name: str = "",
    broker_url: str = "",
) -> None:
    if not cfg.enabled:
        return

    subject, body = _build_email(
        quarantined, restarted, failed, skipped, broker_unreachable, env_name, broker_url
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.from_addr
    msg["To"] = ", ".join(cfg.to_addrs)
    msg.attach(MIMEText(body, "html", "utf-8"))

    smtp_cls = smtplib.SMTP_SSL if cfg.use_ssl else smtplib.SMTP
    with smtp_cls(cfg.smtp_server, cfg.smtp_port) as smtp:
        if not cfg.use_ssl:
            smtp.ehlo()
            smtp.starttls()
        if cfg.username:
            smtp.login(cfg.username, cfg.password)
        smtp.sendmail(cfg.from_addr, cfg.to_addrs, msg.as_string())


def _build_email(
    quarantined: list[SlaveStatus],
    restarted: list[ServiceInfo],
    failed: list[ServiceInfo],
    skipped: list[str],
    broker_unreachable: bool = False,
    env_name: str = "",
    broker_url: str = "",
) -> tuple[str, str]:
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    env_tag = f" [{env_name}]" if env_name else ""
    url_line = f"<p><b>URL do Broker:</b> <a href='{broker_url}'>{broker_url}</a></p>" if broker_url else ""

    if broker_unreachable:
        subject = f"[BROKER MONITOR]{env_tag} Broker inacessivel - {ts}"
        content = (
            "<p>O monitoramento nao conseguiu acessar a pagina de status do Broker.</p>"
            f"{url_line}"
            "<p>Verifique se o servico do Broker esta no ar.</p>"
        )
    else:
        subject = f"[BROKER MONITOR]{env_tag} {len(quarantined)} slave(s) em quarentena - {ts}"

        rows = "".join(
            f"<tr><td style='padding:6px'>{s.address}</td>"
            f"<td style='padding:6px;color:red'>{s.quarantine}</td></tr>"
            for s in quarantined
        )
        content = f"""
        {url_line}
        <p>Detectado(s) <b>{len(quarantined)} slave(s) em quarentena</b>:</p>
        <table border='1' cellpadding='0' cellspacing='0' style='border-collapse:collapse'>
          <tr style='background:#f2f2f2'><th style='padding:6px'>Slave (IP:Porta)</th><th style='padding:6px'>Status</th></tr>
          {rows}
        </table>
        """

        if restarted:
            items = "".join(f"<li>{s.display_name} ({s.address})</li>" for s in restarted)
            content += f"<p style='margin-top:14px'><b style='color:green'>Reiniciados com sucesso ({len(restarted)}):</b><ul>{items}</ul></p>"

        if failed:
            items = "".join(f"<li>{s.display_name} ({s.address})</li>" for s in failed)
            content += f"<p style='margin-top:14px'><b style='color:red'>FALHA no restart ({len(failed)}) -- intervencao manual necessaria:</b><ul>{items}</ul></p>"

        if skipped:
            items = "".join(f"<li>{addr}</li>" for addr in skipped)
            content += f"<p style='margin-top:14px'><b>Fora do mapeamento ({len(skipped)}):</b><ul>{items}</ul></p>"

    html = f"""
    <html><body style='font-family:Calibri,sans-serif;font-size:14px'>
      <h2 style='color:#cc0000'>Protheus Broker Monitor</h2>
      {content}
      <hr/>
      <p style='font-size:11px;color:gray'>Gerado automaticamente em {ts} por broker-monitor</p>
    </body></html>
    """

    return subject, html
