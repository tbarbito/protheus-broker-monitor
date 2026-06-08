# Changelog

Todas as mudancas relevantes deste projeto sao documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e este projeto adota [Versionamento Semantico](https://semver.org/lang/pt-BR/).

## [1.1.0] - 2026-06-08

### Adicionado

- **Suporte a Linux** no modo standard via `systemctl` (systemd). O backend de restart
  agora e selecionado automaticamente conforme o sistema operacional: `sc.exe` no
  Windows e `systemctl restart` no Linux.
- `build.sh`: script de build para gerar o binario standalone Linux (ELF) via PyInstaller,
  espelhando o `build.ps1` do Windows.
- Documentacao de implantacao no Linux: requisitos de systemd, exemplo de unit do AppServer
  Protheus, regra `sudoers` e agendamento via cron e systemd timer.

### Alterado

- `restarter.py` refatorado para despachar entre os backends Windows (`sc.exe`) e
  Linux (`systemctl`) em tempo de execucao, mantendo a interface publica
  (`restart_service`, `get_service_state`) inalterada.
- README reestruturado com secoes separadas de requisitos e build por plataforma.

### Observacoes

- O **modo cluster** continua **exclusivo do Windows** (depende do Windows Failover Cluster
  via PowerShell). Ao habilitar `cluster.enabled: true` em um host Linux, o programa aborta
  com uma mensagem explicativa.

## [1.0.0] - 2026-06-07

### Adicionado

- Versao inicial para **Windows**.
- Monitoramento da pagina de status do Broker Protheus (HTTP + parsing resiliente com BeautifulSoup).
- Reinicio automatico de slaves em quarentena:
  - Modo **standard** via `sc.exe` (Windows Service Control).
  - Modo **cluster** via PowerShell + Windows Failover Cluster (`FailoverClusters`).
- Alertas por e-mail (SMTP) com resumo HTML da operacao.
- Modos de execucao one-shot (Windows Task Scheduler) e daemon (loop continuo).
- Filtro por dias da semana (`allowedWeekdays`) e identificacao de ambiente (`environmentName`).
- Logs diarios com rotacao automatica.
- Build portable via PyInstaller (`build.ps1`).

[1.1.0]: https://github.com/tbarbito/protheus-broker-monitor/releases/tag/v1.1.0
[1.0.0]: https://github.com/tbarbito/protheus-broker-monitor/releases/tag/v1.0.0
