# protheus-broker-monitor

Monitora o Broker do Protheus e reinicia automaticamente os slaves em quarentena.
Suporta execucao pontual via **Windows Task Scheduler** e modo **daemon** continuo.

## Funcionalidades

- Verifica a pagina de status do Broker e detecta slaves em quarentena
- Reinicia automaticamente os servicos Windows correspondentes via `sc.exe`
- Envia email HTML de alerta com o resumo da operacao
- Grava logs diarios com rotacao automatica
- Modo `--dry-run` para verificar sem executar nenhuma acao
- Comando `check` para inspecao rapida do status atual

## Requisitos

- Windows com Python 3.11+
- O script deve ser executado como **Administrador** (necessario para gerenciar servicos Windows)

## Instalacao

```bash
pip install git+https://github.com/tbarbito/protheus-broker-monitor.git
```

Ou com `uv`:

```bash
uv tool install git+https://github.com/tbarbito/protheus-broker-monitor.git
```

## Configuracao

Copie `config.example.json` para `config.json` e preencha com os valores do seu ambiente:

```bash
copy config.example.json config.json
```

> **Importante:** o `config.json` esta no `.gitignore`. Nunca faca commit -- ele contem credenciais SMTP.

### Referencia completa do config.json

```json
{
  "brokerUrl": "https://seu-servidor:10000/totvs_broker_query/status",
  "logDir": "C:\\Logs\\broker-monitor",
  "logRetentionDays": 7,
  "autoRestart": true,
  "startTimeoutSeconds": 60,
  "serviceNamePattern": "TotvsAppSlv{:02d}PRD",
  "slaveRange": {
    "min": 1,
    "max": 7
  },
  "email": {
    "enabled": true,
    "smtpServer": "smtp.seu-servidor.com",
    "smtpPort": 587,
    "useSSL": false,
    "from": "monitor@sua-empresa.com",
    "to": ["admin@sua-empresa.com"],
    "username": "monitor@sua-empresa.com",
    "password": "sua-senha-smtp"
  }
}
```

| Campo | Tipo | Padrao | Descricao |
|---|---|---|---|
| `brokerUrl` | string | **obrigatorio** | URL completa da pagina de status do Broker Protheus |
| `logDir` | string | `logs` | Diretorio onde os arquivos de log serao gravados |
| `logRetentionDays` | int | `7` | Numero de dias para manter os arquivos de log |
| `autoRestart` | bool | `true` | Se `false`, apenas registra os slaves em quarentena sem reiniciar |
| `startTimeoutSeconds` | int | `60` | Tempo maximo (em segundos) aguardando o servico atingir estado RUNNING apos o start |
| `serviceNamePattern` | string | `TotvsAppSlv{:02d}PRD` | Padrao do nome do servico Windows. `{:02d}` sera substituido pelo numero do slave (ex: `03`) |
| `slaveRange.min` | int | `1` | Numero minimo do slave (porta minima = 10000 + min) |
| `slaveRange.max` | int | `7` | Numero maximo do slave (porta maxima = 10000 + max) |
| `email.enabled` | bool | `false` | Habilita o envio de emails de alerta |
| `email.smtpServer` | string | - | Endereco do servidor SMTP |
| `email.smtpPort` | int | `587` | Porta do servidor SMTP |
| `email.useSSL` | bool | `false` | Usa SMTP_SSL (porta 465). Se `false`, usa STARTTLS (porta 587) |
| `email.from` | string | - | Endereco de origem dos emails |
| `email.to` | array | - | Lista de destinatarios |
| `email.username` | string | - | Usuario para autenticacao SMTP |
| `email.password` | string | - | Senha para autenticacao SMTP |

### Como o numero do slave e calculado

O slave e identificado pela porta do endereco `IP:porta` retornado pelo Broker:

```
numero_slave = porta - 10000
nome_servico = serviceNamePattern.format(numero_slave)

Exemplo: porta 10003 -> slave 3 -> "TotvsAppSlv03PRD"
```

## Uso

### Verificar status sem executar nenhuma acao

```bash
broker-monitor check --config config.json
```

### Execucao pontual (one-shot)

Verifica o broker, reinicia slaves em quarentena e encerra:

```bash
broker-monitor run --config config.json
```

### Modo dry-run

Verifica e exibe o que faria, sem reiniciar nem enviar email:

```bash
broker-monitor run --config config.json --dry-run
```

### Modo daemon

Executa em loop continuo, verificando a cada N minutos:

```bash
broker-monitor run --config config.json --daemon --interval 5
```

Pressione `Ctrl+C` para encerrar.

---

## Agendamento via Windows Task Scheduler

O modo one-shot e o ideal para uso com o Task Scheduler. Configure assim:

1. Abra o **Agendador de Tarefas** (`taskschd.msc`)
2. Clique em **Criar Tarefa** (nao "Criar Tarefa Basica")
3. Aba **Geral**:
   - Nome: `Protheus Broker Monitor`
   - Marque **Executar com os privilegios mais altos**
   - Configurar para: `Windows 10` (ou a versao do servidor)
4. Aba **Disparadores** > Novo:
   - Iniciar a tarefa: `De acordo com uma agenda`
   - Repita a tarefa a cada: `5 minutos` por `Indefinidamente`
   - Status: **Habilitado**
5. Aba **Acoes** > Nova:
   - Programa: caminho completo do `broker-monitor.exe`
     (ex: `C:\Users\SeuUsuario\AppData\Roaming\uv\tools\protheus-broker-monitor\Scripts\broker-monitor.exe`)
   - Argumentos: `run --config C:\Scripts\broker-monitor\config.json`
6. Aba **Configuracoes**:
   - Marque **Se a tarefa ja estiver em execucao, a seguinte regra se aplica**: `Nao iniciar uma nova instancia`

> **Dica:** Para encontrar o caminho do executavel apos instalar com `uv`, execute `where broker-monitor` no terminal.

---

## Modo daemon como alternativa ao Task Scheduler

Se preferir nao usar o Task Scheduler, inicie o daemon manualmente ou via script de inicializacao:

```bash
broker-monitor run --config C:\Scripts\broker-monitor\config.json --daemon --interval 5
```

Para manter o daemon ativo apos reinicializacao do servidor, crie uma tarefa no Agendador com:

- Disparador: **Na inicializacao do sistema**
- Acao: `broker-monitor run --config ... --daemon --interval 5`

---

## Logs

Os logs sao gravados em `logDir` com o formato `broker_monitor_YYYYMMDD.log`:

```
[2026-06-04 08:00:01] [INFO] Verificando broker: https://...
[2026-06-04 08:00:02] [WARNING] Quarentena: 10.0.0.1:10003 | QUARANTINE_TIMEOUT
[2026-06-04 08:00:02] [INFO] Reiniciando servico: TotvsAppSlv03PRD
[2026-06-04 08:00:05] [INFO] Restart OK: TotvsAppSlv03PRD -> RUNNING
[2026-06-04 08:00:05] [INFO] Email enviado.
```

Arquivos mais antigos que `logRetentionDays` dias sao removidos automaticamente.

## Licenca

MIT
