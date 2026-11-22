# Sanitização desta versão pública

Cópia sanitizada de um projeto em uso real. Nada aqui é dado de cliente ou de terceiro: o que aparece como exemplo é inventado. Detalhe completo da sanitização: relatório interno da autora.

## O que foi removido

Relatórios publicados, catálogos JSONL do acervo SharePoint, evidências por relatório; as citações do Termo de Referência e os candidatos a anomalia dos relatórios reais em `config/g2_content_blocks.yaml`.

## O que foi trocado

**Códigos de documento → fictícios** (+500 por prefixo); `config/g2_content_blocks.yaml` reduzido (citações → texto fictício, evidências reduzidas à confiança); programa, parceiro, órgãos, rodovias → genéricos; IDs do Graph → exemplo.

## O que é fictício

`data/catalog/work_sources.jsonl` (IDs inventados), planilhas sintéticas geradas pelos testes, cliente Graph falso.

## Como verificar

```bat
py -3.12 -m pytest tests -q        # testes office/golden/network ficam desmarcados por padrão
```

Varreduras (2026-11-19): gitleaks `dir` só com falsos positivos justificados; busca por caminho local, e-mail, nomes do cliente e links privados sem ocorrências reais.
