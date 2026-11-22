# DEC-004 — Autenticação por **client secret**; suporte a certificado removido do escopo

**Data:** 2026-09-21 (revisada em 2026-09-22) · **Status:** ACEITA · **Substitui:** DEC-002

## Contexto
O briefing inicial dizia que o app "Entra ID - Programa" autenticava por **certificado**, com senha,
e a DEC-002 foi escrita sobre essa premissa. Ao chegar o momento de preencher o `.env`, a Emmily
confirmou que a TI **não forneceu nenhum arquivo** `.pfx`, `.p12` ou `.pem`. O que foi entregue,
embora descrito como "Certificado", foi um conjunto de service principal: Client ID, Tenant ID,
Object ID, **Client Secret Value** e Secret ID.

Numa primeira correção o projeto passou a aceitar os dois métodos. A Emmily determinou em
2026-09-22 que certificado **não faz parte desta etapa** e que a Fase 1 deve ser a mais simples,
segura e correta possível. Suporte não usado é superfície de ataque e manutenção sem contrapartida.

## Evidência
1. **Os campos denunciam o tipo.** No portal, a aba se chama "Certificados e segredos". A seção
   *Certificados* lista impressão digital, início e expiração — nunca um "Valor". Apenas
   *Segredos do cliente* tem o par **"Valor" + "ID Secreto"**, com o "Valor" visível uma única vez.
2. **Confirmação direta da Emmily** (2026-09-22): nenhum arquivo de certificado foi entregue.

Confiança: **CONFIRMED**.

## Decisão
1. Autenticação é de **service principal por client secret**, com exatamente três variáveis:
   `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`. Nenhuma é hardcoded.
2. **Todo o código de certificado foi removido**: `LoadedCertificate`, `load_certificate`,
   `CertificateTokenProvider`, o enum `AuthMethod` e os campos correspondentes em `Settings`.
   A dependência direta de `cryptography` saiu do `pyproject`.
3. **Secret ID e Object ID não entram na autenticação** e não são armazenados pelo projeto.
   Servem para a Emmily identificar a credencial ao falar com a TI, fora do repositório.
4. O segredo é tratado como absoluto: fica em `SecretStr`, sai dele em um único ponto
   (`_client_credential()`, direto para o msal) e **nunca** aparece em `repr`, `str`,
   serialização pydantic, log, exceção, STATE, docs, commit — nem parcialmente para diagnóstico.
   `_scrub()` remove o valor de qualquer texto de erro antes de ele virar exceção, caso um
   serviço algum dia o devolva no corpo da resposta.
5. Um valor com menos de 20 caracteres é barrado **antes de qualquer chamada de rede**, com a
   mensagem de que provavelmente é o "ID Secreto" colado no lugar do "Valor". A mensagem não
   ecoa o valor.
6. **Nada muda nas proteções read-only.** A DEC-001 continua integralmente em vigor: trocar o
   método de autenticação não autoriza nenhuma operação de escrita no SharePoint.

## Alternativas consideradas
- **Manter os dois métodos** (estado anterior a esta revisão). Rejeitada por decisão da Emmily:
  mais código, mais testes e mais validação para um caminho que não é usado.
- **Migrar para certificado agora.** Rejeitada: a TI não emitiu certificado. Se emitir no futuro,
  a volta é localizada — `ClientSecretTokenProvider` é a única peça a trocar, e o histórico do
  Git guarda a implementação que já funcionava.
- **Guardar o segredo no Gerenciador de Credenciais do Windows.** Continua possível, já que
  variável de ambiente vence o `.env`. Fica a critério da Emmily.

## Consequências
- Segredo de cliente **expira** (tipicamente 6, 12 ou 24 meses). Quando o acesso falhar com 401,
  suspeitar de expiração ou revogação antes de qualquer outra hipótese.
- **Rotação afeta os projetos irmãos.** O mesmo app é usado pelo `PROG_Cerebro_Documental`; ao
  substituir o segredo, o `.env` daquele projeto também precisa ser atualizado, ou ele para.
- O segredo recebido na configuração inicial foi exposto e será substituído pela Emmily. Nenhum
  valor anterior deve ser recuperado de histórico, terminal, conversa ou arquivo.
