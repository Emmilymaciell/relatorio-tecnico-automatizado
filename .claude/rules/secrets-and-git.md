# Segredos e Git

## Segredos
- Autenticação: service principal por **client secret** (DEC-004). Três variáveis no `.env`,
  nunca versionado: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`.
  Certificado está fora do escopo; não reintroduzir sem pedido explícito.
- Nada de credencial hardcoded em código, teste, script ou documento.
- O "ID Secreto" e o "ID do Objeto" não são usados na autenticação e não são armazenados aqui.
- Nunca pedir à Emmily o valor do segredo em conversa. Ela preenche o `.env` sozinha.
- `AZURE_CLIENT_SECRET` é segredo absoluto: nunca imprimir, logar, gravar em STATE ou docs,
  incluir em exceção, commitar — nem exibir parcialmente para diagnóstico.
- Autenticação é testada com operação read-only (ex.: resolver o site), nunca exibindo token.
- Antes de qualquer commit: `python scripts/check_secrets.py` deve passar.

## Git
- Repositório local, branch `main`, sem remoto. **Nunca** `push`, `force`, `reset --hard`,
  `rebase`, `amend`, apagar branch, alterar remoto, sem autorização explícita.
- Commit somente em marco lógico ou checkpoint de fase, após: `git status`, revisão de
  arquivos novos, `git diff`, `git diff --staged`, checagem de segredos e de documentos
  corporativos brutos. Mensagens em pt-BR ou inglês técnico curto, prefixo convencional
  (`chore:`, `feat:`, `docs:`, `test:`, `fix:`).
- Terminar com o trailer `Co-Authored-By:` do modelo que está rodando a sessão (o harness informa
  qual é; não fixar um nome de modelo neste arquivo).
- Nunca commitar `.docx/.xlsx/.pdf` corporativos. Fixtures de teste são sintéticas.

## Arquivos Python
O tool Bash deste ambiente pode colapsar `\\` em heredoc. Escrever `.py` com Write/Edit.
