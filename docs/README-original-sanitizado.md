# PROG_Relatorio_G2_Automacao

Engenharia reversa e geração **do zero** do *Relatório Mensal do Grupo 2 – Gestão de
Engenharia e Socioambiental* do contrato Programa.

## Finalidade

O projeto tem duas fases distintas:

| Fase | O que faz | Frequência |
|---|---|---|
| **A – Descoberta e certificação** | Investiga nº 01 a nº 14, Lista Mestra, planilhas, imagens, pastas do SharePoint; descobre a fonte, a transformação, a representação e a posição de cada componente; registra regras com evidência e confiança; produz um **modelo certificado** do relatório. | Uma vez |
| **B – Produção mensal** | "Gerar o Relatório G2 Nº N" → DOCX/PDF novo, construído de um documento vazio, a partir do modelo certificado + fontes daquele Relatório G2. | Mensal |

Não é um sistema de "abrir o Word anterior e trocar dados". O builder começa em `Document()`.

## Arquitetura

```
src/prog_g2_report/
  security/     guarda de caminhos locais protegidos + SharePointWriteBlockedError
  settings.py   .env -> Settings (segredo em SecretStr, nunca em repr/log)
  sharepoint/
    auth.py       token de service principal por client secret (msal); nunca exposto
    graph_ro.py   cliente Graph SOMENTE LEITURA: allowlist fechada de operações, só GET
    discovery.py  site -> drive -> pastas -> inventário por metadados; download só autorizado
    models.py     SiteRef / DriveRef / ItemRef (identidade = drive_id + item_id)
  catalog/      esquemas dos catálogos JSONL (componentes, linhagem, anomalias, páginas)

config/         project.yaml, discovery.yaml (sem segredo, sem ID descoberto)
state/          IDs canônicos descobertos, autorizações de download, estado de execução
data/catalog/   *.jsonl — registros rastreáveis da descoberta
data/derived/   extrações locais (texto, medidas); binários não versionados
docs/           architecture/ discovery/ decisions/ specs/ qa/
scripts/        utilitários numerados por ordem de execução
tests/          offline por padrão; `-m network` exige credencial
tmp/            temporários e downloads autorizados (apagados depois; não versionado)
.claude/agents/ subagentes de investigação (read-only)
.claude/rules/  regras absolutas (SharePoint read-only; segredos e Git)
```

Fases detalhadas em [`docs/architecture/PHASES.md`](../docs/architecture/PHASES.md).
Decisões em [`docs/decisions/`](../docs/decisions/). Estado atual em [`STATE.md`](../STATE.md).

## Setup

```powershell
cd "C:\caminho\exemplo\PROG_Relatorio_G2_Automacao"
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
# quando a Fase 3 começar:  .venv\Scripts\python -m pip install -e ".[discovery]"
```

## Autenticação (Entra ID, app "Entra ID - Programa")

Service principal por **client secret**, com três variáveis no `.env`
(ver [DEC-004](../docs/decisions/DEC-004-client-secret-is-the-actual-credential.md)):

```
AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
```

1. Copie `.env.example` para `.env`.
2. Preencha tenant e client id.
3. Cole em `AZURE_CLIENT_SECRET` o campo **"Valor"** do segredo do cliente, gerado no portal.
   Não é o "ID Secreto", que este projeto não usa nem armazena.

O `.env` é ignorado pelo Git. O segredo fica em `SecretStr`, sai dele em um único ponto (para o
msal) e nunca aparece em `repr`, log, exceção ou saída de diagnóstico, nem parcialmente. Segredo
de cliente expira: quando o acesso falhar com 401, suspeite de expiração primeiro.

## Execução

```powershell
.venv\Scripts\python -m pytest                       # testes offline
.venv\Scripts\python scripts\check_secrets.py        # antes de qualquer commit
.venv\Scripts\python scripts\01_verify_readonly_access.py            # Fase 1: autentica e resolve o site
.venv\Scripts\python scripts\01_verify_readonly_access.py --save-ids # grava IDs em state/
```

## Segurança

- **SharePoint é fonte, somente leitura.** O cliente Graph só executa operações de uma
  allowlist fechada e só usa GET; qualquer outra coisa levanta `SharePointWriteBlockedError`.
  Um teste lê a AST do módulo e falha se aparecer escrita.
- A biblioteca sincronizada localmente pelo OneDrive é tratada como o próprio SharePoint:
  escrita lá é recusada pelo código.
- Download de arquivo bruto para disco exige autorização explícita registrada em
  `state/download_authorizations.jsonl` e só pode cair em `tmp/downloads/`.

## Estágio atual

Fase 0 (bootstrap) concluída; Fase 1 (acesso read-only) codificada e testada offline,
aguardando um `.env` com um **novo** segredo do cliente para o primeiro teste de rede.
Ver `STATE.md`.
