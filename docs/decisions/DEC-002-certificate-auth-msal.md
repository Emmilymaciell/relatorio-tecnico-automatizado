# DEC-002 — Autenticação de aplicativo por certificado com `msal` + `cryptography`

**Data:** 2026-09-21 · **Status:** SUPERSEDIDA por [DEC-004](DEC-004-client-secret-is-the-actual-credential.md)

> **Decisão revogada. Leia a DEC-004.** Não existe certificado: a TI forneceu um **segredo do
> cliente**, e em 2026-09-22 a Emmily determinou que certificado sai do escopo desta etapa. Todo
> o código descrito abaixo (`load_certificate`, `CertificateTokenProvider`, campos de certificado
> em `Settings`) **foi removido** do repositório; está no histórico do Git se um dia voltar a ser
> necessário. Continuam valendo, na DEC-004, as partes que não dependem do método: `msal` com
> *client credentials*, `pydantic-settings` lendo o `.env`, segredo em `SecretStr`, token nunca
> exposto e autenticação testada por operação read-only.
>
> O texto original fica preservado abaixo como registro histórico.

## Contexto
A identidade "Entra ID - Programa" autentica por **certificado** (não por client secret). O
certificado tem chave privada e possivelmente senha. A senha não pode aparecer em conversa,
log ou Git. O certificado deve ficar fora do repositório.

## Decisão
- `msal.ConfidentialClientApplication` com `client_credential={"private_key", "thumbprint",
  "public_certificate"}`, fluxo *client credentials*, escopo `https://graph.microsoft.com/.default`.
- `cryptography` abre `.pfx/.p12` (com ou sem senha) ou `.pem` e converte a chave para PEM
  **sem senha, somente em memória**; calcula o thumbprint SHA-1 exigido pelo Entra.
- Configuração via `pydantic-settings` lendo `.env`; senha em `SecretStr`; `Settings` recusa
  certificado localizado dentro do repositório.
- `CertificateTokenProvider.token()` é o único ponto que manipula o token; nenhum `repr`, log
  ou exceção o inclui. Erros de autenticação relatam só `error`, `error_description` e
  `correlation_id` do msal.
- Teste de autenticação = operação read-only (`GET /sites/{host}:/sites/exemplo`), nunca imprimir token.

## Evidência
- Briefing, seção 8 (variáveis `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
  `AZURE_CLIENT_CERTIFICATE_PATH`, `AZURE_CLIENT_CERTIFICATE_PASSWORD`).
- `tests/test_auth_offline.py`: carregamento de PFX com senha, PEM, senha errada sem vazamento.

## Alternativas consideradas
- `azure-identity.CertificateCredential`: funciona, mas traz árvore de dependências maior para
  um único fluxo. Rejeitada por enquanto; trocar é trivial se o msal der problema.
- Chamar o endpoint de token manualmente com JWT assinado: reimplementa o que o msal faz. Rejeitada.
- Guardar a senha em variável de ambiente do sistema em vez do `.env`: aceitável (variável de
  ambiente vence o `.env`), fica a critério da Emmily.

## Consequências
- `msal` é dependência obrigatória; importado tardiamente para os testes offline não exigirem rede.
- Se o app no Entra exigir SNI (`x5c`), `public_certificate` já é enviado.
