# Log de sessões

Histórico compacto, **append-only**. Uma entrada por sessão, escrita pelo `/session-close`.

O **estado atual** vive em `STATE.md`; aqui fica só o histórico. Não transformar este arquivo
em documentação: cada entrada cabe em poucas linhas. Decisões duráveis vão para
`docs/decisions/`, descobertas para `docs/discovery/`, não para cá.

Formato:

```
## AAAA-MM-DD — Nome da sessão
**Objetivo:** uma linha.
**Resultado:** o que efetivamente ficou pronto.
**Validação:** comandos e resultados reais.
**HEAD final:** hash — mensagem.
**Próximo passo:** ação executável.
```

---

## 2026-09-21 — Bootstrap do repositório
**Objetivo:** criar o projeto, as regras e as proteções de acesso.
**Resultado:** estrutura, `CLAUDE.md`, regras em `.claude/rules/`, quatro subagentes, guarda de
caminhos protegidos, cliente Graph somente leitura com allowlist, autenticação por certificado.
**Validação:** 37 testes offline; ruff e varredura de segredos limpos.
**HEAD final:** `ec92364` — bootstrap do repositório.
**Próximo passo:** preencher o `.env` e verificar o acesso de leitura.

## 2026-09-22 — Credencial, acesso e inventário
**Objetivo:** corrigir o método de autenticação e inventariar o acervo.
**Resultado:** autenticação por client secret (DEC-004), acesso verificado, inventário das duas
árvores mensais (DEC-005), corpus de 14 relatórios, Lista Mestra localizada.
**Validação:** 70 testes offline; ruff e segredos limpos.
**HEAD final:** `1a3f3f7` — acesso verificado e corpus inventariado.
**Próximo passo:** arqueologia dos relatórios de maio a agosto.

## 2026-09-22 — Arqueologia de maio a agosto de 2026
**Objetivo:** descobrir como o Relatório G2 é montado.
**Resultado:** anatomia completa dos quatro meses, Lista Mestra confirmada como manifesto
(DEC-006), 21 anomalias catalogadas, nomenclatura "Relatório G2" adotada.
**Validação:** 89 testes offline; ruff e segredos limpos.
**HEAD final:** `9504352` — engenharia reversa de maio a agosto.
**Próximo passo:** provar a linhagem das imagens.

## 2026-09-27 — Linhagem das fontes e especificação candidata
**Objetivo:** fechar a Fase 4 e esboçar o modelo.
**Resultado:** histórico de versões da Lista Mestra (DEC-008), ordenação e filtros provados,
cadeia de dados do produto 2.2 até a célula, capa identificada, visuais reconstruídos (DEC-009),
matriz de reprodutibilidade, cinco rascunhos de especificação e plano do builder.
**Validação:** 92 testes offline; ruff e segredos limpos.
**HEAD final:** `9bd17db` — consolidação da linhagem e da especificação.
**Próximo passo:** fechar o GAP-001, capturando o metarquivo do Controle de Produtos.

## 2026-09-27 — Correção da guarda do ID Secreto (fora desta conversa)
**Objetivo:** fechar resíduos da migração para client secret.
**Resultado:** commit feito pela Emmily, registrado aqui na reconciliação de 2026-10-01. Remove
textos que ainda falavam em certificado, inclusive o diagnóstico de erro 401, e corrige um bug
real: a guarda contra colar o "ID Secreto" no lugar do "Valor" usava limite de 20 caracteres,
mas o ID Secreto é um GUID de 36 e passava. Agora há checagem de forma.
**Validação:** registrada no próprio commit.
**HEAD final:** `c19b851` — remoção de resíduos de certificado e guarda do ID Secreto.
**Próximo passo:** o sprint de linhagem, que seguiu na mesma data.

## 2026-10-01 — Protocolo de abertura e encerramento de sessão
**Objetivo:** tornar a continuidade independente da conversa.
**Resultado:** `/session-start` e `/session-close` em `.claude/skills/`, com procedimentos
auxiliares carregados sob demanda; este log como única estrutura nova; seção no `CLAUDE.md`;
12 testes que validam o frontmatter contra os campos oficiais e as frases de parada.
**Limitação conhecida:** a garantia de que o `session-start` não escreve é **textual**, reforçada
por teste, e não estrutural. O campo `disallowed-tools` existe, mas não está documentado se o
efeito termina com a skill; se persistisse, a sessão ficaria sem escrita depois de autorizado o
trabalho. Preferiu-se a instrução explícita.
**Validação:** `pytest` → 104 passed; `ruff` limpo; `check_secrets.py` limpo. A mensagem do
commit diz 113 testes por engano.
**HEAD final:** `4a9fd37` — protocolo de sessão.
**Próximo passo:** fechar o GAP-001 (ver `STATE.md`).

## 2026-10-01 — Autopilot: Wave 1, Gate A, início do builder
**Objetivo:** modo orquestrador com subagentes paralelos até o modelo certificado.
**Resultado:** 13 investigações (Wave 1) fecharam a Fase 4: GAP-001 (EMF via Excel, DEC-010),
linhagem do 2.2 e do 2.4 provada, snapshot pelo instante de publicação (DEC-012), capa (DEC-011),
slots de IA (DEC-013). Gate A PASS. Modelo v0.9 CANDIDATE com validador em código. Gate B
reprovado pelo revisor independente (10 objeções, correção em curso). Builders P, T e U
integrados; Q, R, V, X, Y em worktrees.
**Pendência humana:** autorização para persistir snapshots antes da poda do SharePoint (GAP-015).
**Validação:** pytest verde (incluindo `-m golden`), ruff e segredos limpos.
**Próximo passo:** ver `STATE.md` (seção EM VOO e NEXT_EXACT_ACTION).

## 2026-10-02 — Autopilot: builder, golden e Gates B/D
**Resultado:** builder completo e integrado (≈60 agentes no total). Gate B PASS (modelo 0.12 →
0.14 `BUILDER_READY`; DEC-013 a DEC-015). Golden do nº 14 PASS com o comparador v4.1 (diff de
texto estrito + 113 hunks aprovados, âncora posicional, checagem de visibilidade): 43 = 43
páginas; QA de fontes 180/181 fatos; QA visual 0 MAJOR. nº 13 reprova só pelo resíduo da Lista
Mestra v134 × v162 (GAP-015). Quatro rodadas de QA adversarial endureceram o comparador
(v1 → v4.1).
**Pendência humana:** GAP-015 (persistir snapshots antes da poda); certificação (Gate E).
**Interrupção:** notebook desligado com a verificação focada do Gate D (QA5) em curso.
**Próximo passo:** `STATE.md` → NEXT_EXACT_ACTION.

## 2026-10-04 — Fechamento da frente de autenticação (verificação, sem nova implementação)
**Objetivo:** confirmar que a migração para client secret está completa e encerrar a frente —
guarda contra colar o "ID Secreto", remoção de resíduos ativos de certificado, mensagens de
diagnóstico coerentes e testes correspondentes.
**Estado final:** tudo já estava implementado e commitado; **nada foi reimplementado**. Os quatro
itens foram conferidos no código atual:
1. `auth.py` recusa valor com forma de GUID antes de ir à rede (`_RE_GUID`), além do comprimento
   mínimo. O limite de 20 caracteres sozinho não separava os dois campos — o "ID Secreto" é um
   GUID de 36 e passava.
2. Nenhum resíduo **ativo** de certificado no código. Permanecem, de propósito, as guardas que
   impedem versionar `.pfx`/`.p12`/`.pem` (`check_secrets.py`, `test_bootstrap.py`) e a `DEC-002`
   marcada como revogada pela `DEC-004`.
3. O diagnóstico de HTTP 401 aponta `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`
   e a confusão "Valor" × "ID Secreto", não mais thumbprint de certificado.
4. Testes cobrem GUID em minúsculo, maiúsculo e entre chaves, e que a mensagem não ecoa o valor
   nem parcialmente.
**Decisões:** nenhuma nova. Valem a `DEC-004` (client secret é a credencial real; certificado fora
de escopo) e a regra de que Secret ID e Object ID não entram na autenticação.
**HEAD:** `7ab840a` — `docs: STATE with production readiness in flight`. Os commits da frente são
`58d7302`, `c8f1814` e `c19b851`, todos ancestrais de `main`.
**Validação:** `pytest tests/test_auth_client_secret.py tests/test_check_secrets.py
tests/test_bootstrap.py` → **46 passed**; `ruff check . --no-cache` → limpo;
`scripts/check_secrets.py` → 223 arquivos, limpo; `git status` → árvore limpa.
**Não executado — `pytest` completo.** Trava sem emitir uma linha; durante a execução havia um
`EXCEL.EXE` no sistema. `addopts` exclui só `-m "not office"`, e dois arquivos tocam COM **sem**
o marcador: `tests/test_excel_reconnect.py` e `tests/test_product_control.py`. Hipótese
**PROVÁVEL** (não isolada rodando cada um, para não travar de novo). Risco residual: a suíte
completa não foi verde nesta sessão; as suítes da frente de autenticação foram.
**Segurança:** `.env` ignorado (`.gitignore:4`) e não rastreado; nenhum valor de segredo exibido,
logado ou gravado; nenhuma tentativa de recuperar o segredo anterior — ele foi exposto e será
substituído; nenhuma autenticação real executada; SharePoint permanece **somente leitura** (sem
verbo de escrita na allowlist do cliente Graph).
**STATE.md:** não alterado nesta sessão, para não conflitar com a frente de produção
("production readiness in flight"). **Precisa ser reconciliado depois** — ele não registra o
fechamento desta frente nem a limitação do `pytest` completo.
**Próxima ação:** marcar `tests/test_excel_reconnect.py` e `tests/test_product_control.py` com
`@pytest.mark.office` (ou isolar o COM), para que `pytest` sem argumentos volte a terminar. Fora
do escopo desta frente. A frente de autenticação só reabre quando a Emmily inserir manualmente o
novo `AZURE_CLIENT_SECRET` no `.env` e pedir o teste de autenticação real.
