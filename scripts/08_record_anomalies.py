"""FASE 3 — grava em `data/catalog/anomalies.jsonl` as anomalias verificadas nesta rodada.

    .venv\\Scripts\\python scripts\\08_record_anomalies.py

Cada registro tem evidencia citavel e `should_learn_as_rule=false`. O gerador NUNCA le
este arquivo como fonte de regra (DEC-003).

As anomalias abaixo foram verificadas contra `tmp/extracted/relatorio_1X/structure.json`
e `pages.json`. Reexecutar este script reescreve o catalogo por inteiro, de forma
deterministica.

Rodada 2026-10-01 (Gate A): acrescenta as anomalias candidatas de
`docs/discovery/WAVE1_FINDINGS.md`, secoes A, B, C, D, E, H, I, J, K, M e O. A evidencia de
cada uma e resumida aqui; o detalhe esta na secao citada entre colchetes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.catalog import Anomaly, AnomalyClass, Confidence, Evidence
from prog_g2_report.report_id import format_report
from prog_g2_report.security import assert_write_allowed

CATALOG = REPO_ROOT / "data" / "catalog" / "anomalies.jsonl"


def anomaly(
    number: int,
    month: str,
    component: str,
    observed: str,
    expected: str | None,
    classification: AnomalyClass,
    confidence: Confidence,
    note: str,
    page: int | None = None,
) -> Anomaly:
    return Anomaly(
        report_id=format_report(number, month),
        page=page,
        component=component,
        observed_value=observed,
        expected_value=expected,
        classification=classification,
        confidence=confidence,
        evidence=[Evidence(report_id=format_report(number, month), page=page, note=note)],
    )


ANOMALIES = [
    # ---------------------------------------------------------------- copy-forward
    anomaly(
        14, "2026-08", "APRESENTACAO_NUMERO_RELATORIO",
        "Relatório Mensal N° 13", "Relatório Mensal N° 14",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.CONFIRMED,
        "O parágrafo da Apresentação é idêntico byte a byte ao do relatório nº 13. "
        "O ENCERRAMENTO do próprio documento diz N° 14, e o arquivo se chama '...n°14 - 08 2026.docx'. "
        "O mesmo dado aparece duas vezes no documento e as duas ocorrências divergem.",
    ),
    anomaly(
        13, "2026-07", "APRESENTACAO_MES_REFERENCIA",
        "referente ao período de Agosto/2026", "referente ao período de Julho/2026",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.CONFIRMED,
        "O ENCERRAMENTO do mesmo documento diz 'durante o mês de Julho/2026'. "
        "Nos relatórios nº 11 e nº 12 número e mês batem entre si. Este erro foi copiado "
        "adiante e produziu a anomalia do relatório nº 14.",
    ),
    # ---------------------------------------------------------------- datas
    anomaly(
        13, "2026-07", "ASSINATURA_DATA",
        "Capital, 11 de Julho de 2026", "data em Agosto/2026",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "A data de assinatura é anterior ao fim do próprio período de referência (31/07/2026). "
        "A capa do mesmo documento traz '11de Agosto de 2026': o dia foi mantido e o mês, esquecido.",
    ),
    anomaly(
        13, "2026-07", "CAPA_DATA_EMISSAO",
        "11de Agosto de 2026", "11 de Agosto de 2026",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.HIGH,
        "[WAVE1 §I] Reclassificado de TYPO: não é erro de digitação, é defeito de renderização "
        "da prévia EMF do slide. A fonte da data (Arial Nova Cond Light, do tema) não estava "
        "disponível para quem editou; a fonte substituta mudou de mês a mês e, em julho, "
        "comeu o espaço. O Word exporta a prévia guardada, não re-renderiza o slide. "
        "DEC-011 elimina a prévia.",
        page=1,
    ),
    anomaly(
        14, "2026-08", "CAPA_DATA_ILEGIVEL_NO_PDF",
        "data da capa ilegível no PDF publicado", "'DD de Mês de AAAA' legível",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "[WAVE1 §I] Mesmo mecanismo do nº 13: a prévia EMF guardada saiu com fonte substituta "
        "e a data não se lê no PDF (conferido com MuPDF e pdfium). DEC-011 resolve com texto "
        "do Word em posição absoluta sobre fundo estático.",
        page=1,
    ),
    # ---------------------------------------------------------------- composição
    anomaly(
        12, "2026-06", "CONTROLE_DE_PRODUTOS_INCOMPLETO",
        "2 páginas de Controle de Produtos, 49 documentos",
        "cobertura dos 107 documentos que a Lista Mestra atribui ao relatório",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.HIGH,
        "Maio tem 9 páginas de Controle de Produtos, julho 13 e agosto 11; junho tem 2. "
        "58 dos 107 documentos da Lista Mestra não aparecem. Não usar junho como referência "
        "para a regra de composição do Controle de Produtos.",
    ),
    # ---------------------------------------------------------------- texto
    anomaly(
        12, "2026-06", "ENCERRAMENTO_NUMERO_POR_EXTENSO",
        "43 (quarenta e trâs) páginas", "43 (quarenta e três) páginas",
        AnomalyClass.TYPO, Confidence.CONFIRMED,
        "Os relatórios nº 13 e nº 14 escrevem 'quarenta e três' para o mesmo valor.",
    ),
    anomaly(
        13, "2026-07", "P2.4_FRASE_TRUNCADA_MEDICOES",
        "Quanto às medições, ... Na RD-101. As análises tiveram como objetivo",
        "frase completa, como no relatório nº 12",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "Sobrou 'Na RD-101.' órfã após exclusão de conteúdo. O relatório nº 12 traz a versão íntegra.",
    ),
    anomaly(
        14, "2026-08", "P2.4_FRASE_TRUNCADA_MEDICOES",
        "Quanto às medições, ... Na RD-101. As análises tiveram como objetivo",
        "frase completa",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.CONFIRMED,
        "Mesmo defeito do relatório nº 13, propagado para agosto sem correção.",
    ),
    anomaly(
        14, "2026-08", "P2.2_DUP_PARENTESE",
        "Documentação para Declaração de Utilidade Pública (DUP_ e Estudos Hidrológicos",
        "(DUP)",
        AnomalyClass.TYPO, Confidence.CONFIRMED,
        "Underline no lugar do parêntese de fechamento; no mesmo parágrafo o predicado "
        "'encontram-se aprovados' aparece duas vezes.",
    ),
    anomaly(
        14, "2026-08", "P2.4_RELATORIO_CONSOLIDADO_GRAFIA",
        "Relatório Consolidade de Gestão das Não Conformidades",
        "Relatório Consolidado de Gestão das Não Conformidades",
        AnomalyClass.TYPO, Confidence.CONFIRMED,
        "'Consolidade' não é palavra. A mesma frase está truncada: falta o complemento "
        "'a situação das não conformidades desde o início das obras', presente nos nº 11 e nº 12.",
    ),
    anomaly(
        14, "2026-08", "P2.2_DUP_RD101_SEM_VALOR",
        "Publicação pela Casa Civil:", "valor de status após os dois-pontos",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "As outras três rodovias trazem valor no mesmo bloco de status da DUP.",
    ),
    anomaly(
        11, "2026-05", "P2.4_LAU_TEXTO_CONTRADITORIO",
        "encontram-se pendentes condicionantes que devem ser sanadas, a saber:",
        "texto coerente com os itens seguintes",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.HIGH,
        "Os quatro itens logo abaixo dizem 'Não apresenta condicionantes em atraso'. "
        "Os relatórios nº 12 e nº 13 usam formulação coerente.",
    ),
    # ---------------------------------------------------------------- cabeçalho e rodapé
    anomaly(
        11, "2026-05", "CABECALHO_ESPACAMENTO",
        "PROGRAMA | CONSÓRCIO ESTRUTURADOR DO P R OGRAMA",
        "PROGRAMA | CONSÓRCIO ESTRUTURADOR DO PROGRAMA",
        AnomalyClass.TYPO, Confidence.CONFIRMED,
        "Em header1.xml do relatório nº 11 a palavra PROGRAMA sai com espaços entre letras. "
        "As demais partes do mesmo documento e todos os outros meses trazem a forma correta.",
    ),
    anomaly(
        11, "2026-05", "RODAPE_NUMERACAO_SECAO_PAISAGEM",
        "footer2.xml sem o campo PAGE", "rodapé com numeração, como nas demais seções",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "No relatório nº 11 o rodapé da seção paisagem não tem o campo PAGE: aquelas páginas "
        "saem sem número. Nos relatórios nº 12 em diante todas as partes de rodapé têm o campo. "
        "Corrigido a partir de junho.",
    ),
    # ---------------------------------------------------------------- Lista Mestra
    anomaly(
        14, "2026-08", "LISTA_MESTRA_EDICAO_RETROATIVA",
        "NT-798.1, NT-799.1, NT-800.1, NT-805.1 e NT-806.1 acrescentadas ao relatório nº 14 "
        "depois da emissão",
        None,
        AnomalyClass.TRUE_MODEL_CHANGE, Confidence.CONFIRMED,
        "NÃO é defeito do relatório: é comportamento normal da planilha, que é viva. "
        "O histórico de versões prova: no snapshot do instante de publicação (DEC-012: v331, "
        "PDF de 08/09/2026 18:51Z) a Lista Mestra tinha 135 códigos distintos (149 linhas) no "
        "relatório nº 14, e o Controle de Produtos do PDF tem exatamente os mesmos, com zero "
        "divergências nos dois sentidos. As 5 notas entraram na planilha depois. "
        "Consequência: reconstrução histórica usa o snapshot, nunca a planilha atual.",
    ),
    anomaly(
        11, "2026-05", "ANEXO_DUPLICADO_ENTRE_RELATORIOS",
        "AT-632.1 anexada nos relatórios nº 11 e nº 12",
        "um único relatório, conforme a Lista Mestra (nº 12)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "O mesmo documento foi anexado duas vezes, com nomes ligeiramente diferentes. "
        "[WAVE1 §H] É o 1 anexo fora da lista por mês em maio e junho: a correspondência "
        "anexos × Lista Mestra não é 100% nos dois sentidos, e há risco de causalidade inversa "
        "(lista preenchida depois do anexo).",
    ),
    anomaly(
        11, "2026-05", "ANEXO_RODOVIA_DIVERGENTE",
        "PA-598.1 arquivado em 'Parecer Técnico/RD-102A/'",
        "pasta RD-101, conforme a coluna Empreendimento",
        AnomalyClass.UNRESOLVED, Confidence.MEDIUM,
        "Única divergência de rodovia em 686 arquivos verificados. Não é possível dizer se o "
        "erro está na Lista Mestra ou no arquivamento.",
    ),
    # [WAVE1 §D] substitui P2.4_FAIXA_RO_INCORRETA (TYPO): a causa é uma única semana.
    anomaly(
        13, "2026-07", "P2.4_FAIXA_RO_SEMANA_OMITIDA",
        "texto: RD-103 RO-540.1 a RO-543.1; RD-102A RO-540.1 a RO-543.1; RD-101 RO-539.1 a "
        "RO-542.1; RD-104 RO-534.1 a RO-537.1",
        "faixas da Lista Mestra do nº 13, que incluem a semana 25/07–31/07 nas 4 rodovias",
        AnomalyClass.INTERNAL_INCONSISTENCY, Confidence.CONFIRMED,
        "Lista Mestra, coluna Período e anexos põem no nº 13 o relatório semanal da semana "
        "25/07–31/07 das 4 rodovias; o texto do mesmo nº 13 a omite. Hipóteses 'entregue após a "
        "emissão' e 'linha adicionada depois' descartadas: a v134 de 11/08 já tinha "
        "N° Relatório = 13. O texto só diverge quando a semana começa no dia 25 de um mês de "
        "31 dias (ocorreu só em julho/2026).",
    ),
    anomaly(
        14, "2026-08", "P2.4_FAIXA_RO_SEMANA_REPETIDA",
        "texto: RD-101 RO-543.1 a RO-547.1 (idem 1º código nas outras 3 rodovias); período "
        "iniciado em 25/07",
        "RD-101 RO-544.1 a RO-547.1; período iniciado depois de 31/07, como na Lista Mestra",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.CONFIRMED,
        "O nº 14 continuou a faixa do texto do nº 13 e citou de novo a semana 25/07–31/07, que "
        "a Lista Mestra e os anexos atribuem ao nº 13. A regra pela Lista Mestra reproduz 76/76 "
        "da Lista Mestra e dos anexos. Nunca inferir faixa por continuidade com o mês anterior.",
    ),
    anomaly(
        11, "2026-05", "P2.4_RO_FIM_DE_PERIODO",
        "fim de período '25/05'", "maior fim do Período dos RO do relatório",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.MEDIUM,
        "[WAVE1 §D] O fim do período citado no nº 11 coincide com a data de corte, não com o "
        "fim da última semana (sábado→sexta) dos RO do relatório.",
    ),
    anomaly(
        11, "2026-05", "LISTA_MESTRA_RO_DATA_ENTREGA_ANTERIOR",
        "Data Entrega 2026-05-08 em 3 RO", "data de entrega posterior ao início da semana",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.HIGH,
        "[WAVE1 §D] Em 3 relatórios semanais a Data Entrega da Lista Mestra é anterior ao início "
        "da semana do campo Período. Dado da fonte, não do texto; validação não bloqueante.",
    ),
    anomaly(
        14, "2026-08", "LISTA_MESTRA_GRAFIA_MANIFESTACAO",
        "'Notificação de Não Conformidade' (11 linhas) e 'Notificação de não conformidade' (130)",
        "uma grafia única, a da lista de validação",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "Duas grafias do mesmo valor na coluna Manifestação. Só a minúscula está na aba "
        "'Listas', que define os domínios válidos. Afeta qualquer agrupamento por tipo.",
    ),
    anomaly(
        14, "2026-08", "CONTROLE_DE_PRODUTOS_CABECALHO_COLUNA_2",
        "Parecer", "cabeçalho da coluna na Lista Mestra do snapshot (DEC-010 §6)",
        AnomalyClass.TRUE_MODEL_CHANGE, Confidence.HIGH,
        "[WAVE1 §K, §A] Revisto: o quadro é recorte do Excel, então o rótulo é o cabeçalho da "
        "fonte no snapshot, não texto gerado. A própria Lista Mestra trazia 'Parecer' (v134.0, "
        "julho) e passou a 'Manifestação' (v335.0). Os nº 11 e nº 12 traziam 'Tipo'. Deixa de "
        "ser decisão da Emmily; o builder copia o cabeçalho do snapshot. Que 'Parecer' seja "
        "também um valor da coluna continua sendo defeito da planilha, não do relatório.",
    ),
    anomaly(
        12, "2026-06", "P2.2_DASHBOARD_ORDENACAO",
        "linhas em ordem decrescente de revisão", "ordem por disciplina, como nos demais meses",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "No print do painel o cursor de ordenação está sob a coluna de revisão. O operador "
        "clicou no cabeçalho antes de capturar a tela. Os relatórios nº 11, nº 13 e nº 14 "
        "trazem a ordem por disciplina.",
    ),
    anomaly(
        12, "2026-06", "P2.2_DASHBOARD_LARGURA",
        "17,38 cm e 17,47 cm", "17,50 cm, a largura útil do texto",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "Duas das quatro imagens do mês saíram com largura diferente das demais. "
        "Redimensionamento manual impreciso.",
    ),
    # ---------------------------------------------------------------- forma consolidada
    anomaly(
        14, "2026-08", "P2.1_IDENTIFICACAO_RODOVIA",
        "RD-102: reunião com o Consórcio CLX/TRAFEX", "RD-102A",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "Todas as demais menções no corpo usam RD-102A. A forma curta é estável nos quatro "
        "meses neste bloco: é forma consolidada, não erro de um mês. Decidir com a Emmily "
        "se o gerador normaliza ou preserva.",
    ),
    anomaly(
        13, "2026-07", "P2.1_IDENTIFICACAO_RODOVIA",
        "RD-102: reunião com o Consórcio CLX/TRAFEX", "RD-102A",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[golden nº 13, builder EE] Mesma forma curta da agenda do 2.1 registrada para o nº 14 "
        "(PDF nº 13, p. 5; DOCX nº 13 idem). Catalogada também no nº 13 para que a allowance do "
        "golden temporal cite uma anomalia do próprio relatório (PEND-13-002).",
        page=5,
    ),
    anomaly(
        14, "2026-08", "TITULO_ANEXOS_ESPACOS",
        "'ANEXOS     '", "'ANEXOS'",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "Cinco espaços à direita nos relatórios nº 13 e nº 14; sem espaços nos nº 11 e nº 12. "
        "Resíduo de edição, sem efeito visual.",
    ),
    # Crase em 'referente a + feminino' no texto gerado (DEC-007, QA4-H): forma idêntica nos
    # nº 11–14 (content_blocks identical_in), por isso FORMAT_VARIATION de forma consolidada.
    *[
        anomaly(
            number, month, "CRASE_REFERENTE_AS",
            "'Referente as atividades periódicas' (2.1.2, P2.1_CRONO_LEAD); 'Ainda referente as "
            "Condicionantes Ambientais' (2.4.2, P2.4_GAMB); 'Referente as Condicionantes da "
            "Licença' (2.4.2, P2.4_LAU_HEAD)",
            "'Referente às atividades periódicas'; 'Ainda referente às Condicionantes "
            "Ambientais'; 'Referente às Condicionantes da Licença'",
            AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
            "[QA4-H; DEC-007] 'referente a' + substantivo feminino plural sem crase, idêntico "
            "nos nº 11–14 nos três blocos (texto gerado, não citação SOURCE_VERBATIM). O "
            "gerado escreve 'às' (text_standardized dos blocos). Varredura dos textos emitidos "
            "(model.emitted_texts): nenhuma outra ocorrência de 'referente a(s) + feminino'; "
            "'referente(s) a cada' e 'Referente a <Mês>/<AAAA>' estão corretos.",
        )
        for number, month in ((11, "2026-05"), (12, "2026-06"), (13, "2026-07"),
                              (14, "2026-08"))
    ],
    # ================================================================ rodada 2026-10-01
    # ---------------------------------------------------------------- A: Controle de Produtos
    # [WAVE1 §M, Gate B] Os dois "defeitos" do nº 13 abaixo eram erro do diagnóstico (§A comparou
    # contra v134/v335, não contra o snapshot de publicação). Com a v162 (DEC-012) ambos são
    # explicados pela regra — corpo = body_rows, índice = index_rows — e saem como defeito do
    # relatório. Ficam só como METHOD_ERROR, para a mesma evidência não ser regra e defeito.
    anomaly(
        13, "2026-07", "DIAGNOSTICO_CONTROLE_PRODUTOS_BM_RD104",
        "diagnóstico §A: '3 linhas BM da RD-104 repetidas no bloco do 2.4'",
        "corpo = body_rows (DEC-012): as 3 linhas BM-007/008/009.1 da RD-104 existem na v162",
        AnomalyClass.METHOD_ERROR, Confidence.HIGH,
        "[WAVE1 §A, §M] A comparação de §A usou snapshots errados para julho. Na v162 (última "
        "versão antes do CreationDate do PDF) as três linhas 'Em elaboração' da RD-104 têm "
        "N° Relatório = 13; o Controle de Produtos do 2.4 as lista uma vez cada. Não é defeito "
        "do relatório; a regra body_rows reproduz o bloco.",
    ),
    anomaly(
        13, "2026-07", "DIAGNOSTICO_INDICE_ANEXOS_BM_RD102A",
        "diagnóstico §A: '3 linhas BM da RD-102A ausentes do índice de ANEXOS'",
        "índice = index_rows = body_rows ∧ Status Entrega == 'Entregue' (DEC-012)",
        AnomalyClass.METHOD_ERROR, Confidence.HIGH,
        "[WAVE1 §M] As linhas BM-007/008/009.1 da RD-102A (e da RD-104) estavam 'Em elaboração' "
        "e sem data na v162: o filtro do índice as exclui. O índice e o total do encerramento "
        "(165) são reproduzidos pela regra; não há omissão a registrar como defeito.",
    ),
    anomaly(
        14, "2026-08", "INDICE_ANEXOS_RECORTE_ENCOLHIDO",
        "dois recortes do índice de ANEXOS redimensionados à mão",
        "todos os recortes na mesma escala (17,5 cm de largura)",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[WAVE1 §A] Dos 5 recortes do índice, dois foram encolhidos manualmente para caber na "
        "página. O builder usa paginação gulosa e escala única (DEC-010).",
    ),
    anomaly(
        13, "2026-07", "INDICE_ANEXOS_RECORTE_ENCOLHIDO",
        "1º recorte do índice de ANEXOS redimensionado à mão (16,57 cm de largura)",
        "todos os recortes na mesma escala (17,5 cm de largura)",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[golden nº 13, builder EE] DOCX nº 13: o recorte que divide a página com o título "
        "ANEXOS tem 16,57 cm; os outros recortes do documento têm 17,5 cm. No PDF (p. 38) os "
        "desenhos vão até 19,68 cm contra 20,64 cm nas demais páginas. Mesma prática do nº 14; o "
        "builder usa escala única (DEC-010).",
        page=38,
    ),
    # ---------------------------------------------------------------- B: painéis ambientais
    anomaly(
        13, "2026-07", "P2.4_PAINEL_AMBIENTAL_DATADO_APOS_EMISSAO",
        "painel 'Atualizado em 12/08/2026'", "data não posterior à capa (11/08/2026)",
        AnomalyClass.INTERNAL_INCONSISTENCY, Confidence.CONFIRMED,
        "[WAVE1 §B] O painel ambiental do nº 13 foi atualizado depois da data de emissão da "
        "capa. Coerente com o PDF gerado em 14/08 (DEC-012): a data da capa não é o instante "
        "da montagem.",
    ),
    anomaly(
        12, "2026-06", "P2.4_PAINEL_LICENCAS_EMITIDAS",
        "'24 emitidas' com 23 vigentes", "contagens coerentes entre si",
        AnomalyClass.INTERNAL_INCONSISTENCY, Confidence.MEDIUM,
        "[WAVE1 §B] Dentro do mesmo painel, o total de emitidas não fecha com o de vigentes. "
        "Qual número está errado é UNKNOWN (não há snapshot da planilha para junho).",
    ),
    anomaly(
        11, "2026-05", "P2.4_PAINEL_AMBIENTAL_RUIDO_INTERFACE",
        "elementos da interface do Power BI capturados no print", "painel limpo",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.HIGH,
        "[WAVE1 §B] Captura de tela do nº 11 inclui ruído de interface (cabeçalho de visual, "
        "cursor). DEC-009 reconstrói o painel a partir do dado.",
    ),
    anomaly(
        14, "2026-08", "LICENCA_AMBIENTAL_NUMERO_CLX_DIVERGENTE",
        "nº de licença da CLX diferente entre as abas da planilha", "um único número",
        AnomalyClass.INTERNAL_INCONSISTENCY, Confidence.HIGH,
        "[WAVE1 §B] Na fonte '04_Acompanhamento - Licenca Ambiental.xlsx' (snapshot v310) o "
        "número de licença da CLX não coincide entre abas. O painel usa a aba 'Licenças'.",
    ),
    anomaly(
        14, "2026-08", "LICENCA_AMBIENTAL_EMPRESAS_GRAFIA_RODOVIA",
        "Empresas!M 'RD 102a'", "'RD-102A'",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[WAVE1 §B] Grafia da rodovia na aba 'Empresas' da fonte ambiental; normalizar ao "
        "ler (mesma normalização de 'RD-102 A' da planilha de projetos).",
    ),
    # ---------------------------------------------------------------- C: não conformidade
    anomaly(
        12, "2026-06", "P2.4_PA_EM_ELABORACAO_JA_ATRIBUIDOS",
        "'constam em elaboração os Pareceres Técnicos PA-633.1, PA-634.1 e PA-635.1'",
        "pareceres citados como emitidos: a Lista Mestra os atribui ao nº 12",
        AnomalyClass.INTERNAL_INCONSISTENCY, Confidence.HIGH,
        "[WAVE1 §C] O texto do nº 12 diz 'em elaboração' para documentos que a Lista Mestra "
        "atribui ao próprio nº 12 (planilha atual; não há snapshot de junho).",
    ),
    anomaly(
        7, "2026-01", "P2.4_PAINEL_NC_PROMETIDO",
        "'encontra-se em desenvolvimento uma apresentação em Power BI' para as NC",
        "painel nunca publicado",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "[WAVE1 §C] Nenhum relatório, do nº 01 ao nº 14, traz painel de não conformidades. "
        "A promessa não é evidência de componente: P2.4_NONCONFORMITY_PANEL sai do modelo.",
    ),
    # ---------------------------------------------------------------- E: planilha de projetos
    anomaly(
        14, "2026-08", "P2.2_PAVIMENTACAO_RD101_STATUS_DEFASADO",
        "Pavimentação da RD-101 'pendente' no texto", "'em análise', como na v438 do snapshot",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.HIGH,
        "[WAVE1 §E] Única contradição dos blocos de status do nº 14: o texto foi redigido com "
        "as versões v429–v436, horas antes da última atualização da planilha de projetos.",
    ),
    anomaly(
        14, "2026-08", "P2.2_OAE_RD101_ACEITO_INCOMPLETO",
        "'aceito' da OAE da RD-101 cita uma das duas disciplinas",
        "as duas disciplinas aceitas",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[WAVE1 §E] Frase copiada do mês anterior sem acrescentar a segunda disciplina.",
    ),
    # Golden nº 13/14 com o extrator 3.1 (builder RR): disciplinas dos campos do 2.2 e o status
    # "aprovado com ressalva" passam a ser fatos; as diferenças abaixo ficam visíveis.
    anomaly(
        13, "2026-07", "P2.2_OAE_RD101_ACEITO_INCOMPLETO",
        "RD-101, OAE: 'o Projeto de Obra de Arte Especial (OAE) se encontra aceito em 1º nível'",
        "OAE e Memoriais de Cálculo Estrutural e Quantitativo aceitos (Projetos v328: as duas "
        "disciplinas com 'Disciplina ACEITA?' = Sim, recebidas em 06/07/2026)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[golden nº 13, builder RR] Mesma frase do nº 14 (já catalogada lá): uma das duas "
        "disciplinas aceitas. O gerado enumera as duas pela planilha (status_sets.accepted).",
    ),
    anomaly(
        14, "2026-08", "P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO",
        "RD-104, Viário Principal: 'o Projeto Geométrico e Interseções e o Projeto de "
        "Terraplenagem encontram-se aprovados com ressalva'",
        # expected = FATO da planilha por disciplina (DEC-015), não a regra do modelo (QA3-E:
        # a forma antiga citava reservation_qualifier e era circular).
        "Projetos v438, Status (AVALIAÇÃO) por disciplina da RD-104, Viário Principal: Projeto "
        "Geométrico e Interseções = Aprovado (sem ressalva); Projeto de Terraplenagem = "
        "Aprovado com ressalva",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[p22_highway_block.yaml new_anomaly_candidates; golden nº 14, builder RR; QA3-E; "
        "DEC-015] A planilha distingue a ressalva por disciplina (v438: 10 disciplinas com "
        "ressalva nas 4 rodovias), e os nº 11 e nº 12 a escreviam por disciplina. O nº 13 e o "
        "nº 14 generalizam: só esta frase, igual nos dois meses, qualifica, e a estende ao "
        "Geométrico; as outras 9 aprovações com ressalva da v438 saem sem o qualificador "
        "(inclusive sob 'Todas as disciplinas encontram-se aprovadas'). Ver o mesmo registro "
        "do nº 13.",
        page=21,
    ),
    anomaly(
        13, "2026-07", "P2.2_APROVADOS_COM_RESSALVA_GENERALIZADO",
        "RD-104, Viário Principal: 'o Projeto Geométrico e Interseções e o Projeto de "
        "Terraplenagem encontram-se aprovados com ressalva'",
        "Projetos v328, Status (AVALIAÇÃO) por disciplina da RD-104, Viário Principal: Projeto "
        "Geométrico e Interseções = Aprovado (sem ressalva); Projeto de Terraplenagem = "
        "Aprovado com ressalva",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[golden nº 13, builder RR; QA3-E; DEC-015] Frase idêntica à do nº 14; as outras 12 "
        "aprovações com ressalva da v328 (13 no total, nas 4 rodovias) saem sem o qualificador "
        "no próprio nº 13.",
        page=21,
    ),
    anomaly(
        13, "2026-07", "P2.2_PREDICADO_REPETIDO",
        "RD-101, Fase de Estudos: 'Aprovação: encontram-se aprovados o Relatório de Atividades "
        "Preliminares, [...] e Estudos Hidrológicos encontram-se aprovados;'",
        "predicado uma vez ('Aprovação: o Relatório de Atividades Preliminares, [...] e os "
        "Estudos Hidrológicos encontram-se aprovados;', templates.approval.plural)",
        AnomalyClass.TYPO, Confidence.CONFIRMED,
        "[golden nº 13, builder RR] 'encontram-se aprovados' antes e depois da enumeração no "
        "mesmo item; o nº 14 repete a frase com o mesmo defeito (registrado lá em "
        "P2.2_DUP_PARENTESE, junto com o '(DUP_').",
    ),
    anomaly(
        13, "2026-07", "P2.2_ROTULO_DISCIPLINAS_EM_REVISAO",
        "RD-103, Viário Principal: 'Disciplinas em revisão: o Projeto de Terraplenagem "
        "encontra-se em revisão pela empresa executora.'",
        "'Disciplinas pendentes de aprovação: Projeto de Terraplenagem;' (padrão vigente, "
        "templates.pending_approval, 4 de 4 formas idênticas no nº 14)",
        AnomalyClass.TRUE_MODEL_CHANGE, Confidence.CONFIRMED,
        "[p22_highway_block.yaml status_sets.pending_approval.history; golden nº 13, builder "
        "RR] Não é erro de julho: os nº 12 e 13 rotulavam o mesmo conjunto (aceito, reprovado, "
        "reentrega vencida) como 'em revisão pela empresa executora'; em agosto o rótulo passou a "
        "'pendentes de aprovação'. O modelo segue o padrão vigente.",
        page=19,
    ),
    anomaly(
        13, "2026-07", "P2.2_PENDENTES_NAO_ENTREGUES_ADOCAO",
        "nº 13 sem as linhas 'Disciplinas pendentes de aprovação' (só 1 'em revisão') e com "
        "'Disciplinas não entregues' só na RD-103 (sem o Projeto de Paisagismo)",
        "linhas presentes sempre que o conjunto não é vazio (line_presence.pending_approval e "
        "not_delivered): 7 pendentes (RD-103 Principal e Secundário, RD-102A Secundário, RD-101 "
        "Estudos e Principal, RD-104 Principal e Secundário) e 4 não entregues pela v328",
        AnomalyClass.TRUE_MODEL_CHANGE, Confidence.HIGH,
        "[p22_highway_block.yaml line_presence e measurement.status_set_level.no13_v328; golden "
        "nº 13, builder RR] As linhas foram adotadas em agosto (4 de 4 rodovias) e julho é a "
        "transição (só RD-103, incompleta: Paisagismo da RD-103 não recebido na v328). O gerado "
        "segue o padrão vigente (DEC-007).",
    ),
    anomaly(
        13, "2026-07", "P2.4_NC_FRASE_TRUNCADA",
        "'...relatórios mensais, que compilam e atualizam, de forma acumulada.'",
        "'..., de forma acumulada, a situação das não conformidades desde o início das obras.' "
        "(nº 11 e nº 12)",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "[golden nº 13, builder RR] O complemento some no nº 13 e o nº 14 copia a frase "
        "truncada (registrada no nº 14 em P2.4_RELATORIO_CONSOLIDADO_GRAFIA). O gerado escreve a "
        "frase completa, o que acrescenta um 'não' aos fatos da seção.",
    ),
    # Análise PROGRAMA de P2.2_DESAPROPRIACAO/INTERFERENCIAS × aba Projetos (QA2-E, builder QQ):
    # 9 de 12 iguais na v438; as 3 abaixo contradizem os bullets 'em análise pelo PROGRAMA' do
    # P2.2_HIGHWAY_BLOCK do mesmo relatório (RD-104 Viário Secundário; RD-102A Viário Secundário).
    anomaly(
        14, "2026-08", "P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA",
        "'RD-104: ... Análise Programa: Não aprovado' (matriz Projeto de Desapropriação)",
        "'Análise Programa: Em análise'",
        AnomalyClass.INTERNAL_INCONSISTENCY, Confidence.CONFIRMED,
        "[QA2-E] Projetos v438 (snapshot DEC-012): Projeto de Desapropriação da RD-104 recebido "
        "em 26/08, análise iniciada, Status (AVALIAÇÃO) vazio = 'Em análise'. O próprio nº 14, "
        "no bloco da RD-104 (Viário Secundário), diz 'Projeto de Desapropriação [...] encontram-se "
        "em análise pelo Programa'. A Análise Programa passa a ser derivada da planilha "
        "(inputs.p22_external_status.schema.derived.prog).",
    ),
    anomaly(
        14, "2026-08", "P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA",
        "'RD-102A: ... Análise Programa: Não aprovado' (matriz de interferências)",
        "'Análise Programa: Em análise'",
        AnomalyClass.INTERNAL_INCONSISTENCY, Confidence.CONFIRMED,
        "[QA2-E] Projetos v438: Projeto de Interferência de Iluminação e Rede Elétrica da "
        "RD-102A recebido em 28/08, análise iniciada, sem avaliação = 'Em análise'. O bloco da "
        "RD-102A do mesmo relatório (Viário Secundário) lista o Projeto de Interferência em "
        "'Disciplinas em análise'.",
    ),
    anomaly(
        14, "2026-08", "P2.2_EXTERNAL_PROG_CONTRADIZ_PLANILHA",
        "'RD-104: ... Análise Programa: Não aprovado' (matriz de interferências)",
        "'Análise Programa: Em análise'",
        AnomalyClass.INTERNAL_INCONSISTENCY, Confidence.CONFIRMED,
        "[QA2-E] Projetos v438: Projeto de Interferência de Iluminação e Rede Elétrica da RD-104 "
        "recebido em 26/08, análise iniciada, sem avaliação = 'Em análise'. O bloco da RD-104 do "
        "mesmo relatório diz '[...] Projeto de Interferência de Iluminação e Rede Elétrica "
        "encontram-se em análise pelo Programa'.",
    ),
    # Análise Programa das matrizes × ressalva da planilha (QA4-H, builder XX; DEC-015 estendida à
    # matriz no modelo v0.14): o publicado omite a ressalva que Projetos!S registra.
    anomaly(
        14, "2026-08", "P2.2_EXTERNAL_PROG_RESSALVA_OMITIDA",
        "'Análise Programa: Aprovado' (DUP da RD-103, RD-101 e RD-104; Projeto de Desapropriação "
        "da RD-102A) e 'Análise Programa: Aprovado e encaminhado a GFD' (Projeto de "
        "Interferência da RD-103 e da RD-101)",
        "Projetos v438, Status (AVALIAÇÃO): DUP RD-103 'Aprovada com ressalva', RD-101 "
        "'Aprovado com Ressalvas', RD-104 'Aprovada com ressalva'; Projeto de Desapropriação "
        "RD-102A 'Aprovado com ressalva'; Projeto de Interferência RD-103 e RD-101 'Aprovado "
        "com ressalvas'",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.HIGH,
        "[QA4-H; DEC-015] A planilha do snapshot do texto do 2.2 (v438, DEC-012) qualifica as 6 "
        "aprovações com ressalva; o bloco por rodovia gerado as escreve 'aprovado(a) com "
        "ressalva' (templates.approval.reservation_qualifier). A matriz publicada diz só "
        "'Aprovado'. O gerado escreve 'Aprovado com ressalva' (interferências: 'Aprovado com "
        "ressalva e encaminhado a GFD': as 2 interferências aprovadas da v438 têm ressalva e "
        "o nº 14 as dá por encaminhadas, logo o encaminhamento independe da ressalva). "
        "Matriz e corpo do 2.2 dão o mesmo status à mesma disciplina.",
    ),
    # ---------------------------------------------------------------- H: ordem física
    anomaly(
        11, "2026-05", "CONTROLE_DE_PRODUTOS_ORDEM_POR_CODIGO",
        "índice de ANEXOS ordenado por código", "ordem física da Lista Mestra (padrão jul/ago)",
        AnomalyClass.TRUE_MODEL_CHANGE, Confidence.CONFIRMED,
        "[WAVE1 §H] Não é erro: em maio o índice estava perfeitamente ordenado por código "
        "(HISTORICAL_PATTERN). Julho e agosto seguem a ordem física (as 4 sequências do PDF de "
        "agosto são idênticas às do snapshot). A regra de ordem física é CONFIRMED só para o "
        "padrão vigente; o acerto estrito por data é 89,5%, não 94%.",
    ),
    anomaly(
        12, "2026-06", "CONTROLE_DE_PRODUTOS_JPG",
        "Controle de Produtos inserido como JPG", "EMF vetorial, como em maio, julho e agosto",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[WAVE1 §H] Maio já era vetorial: o JPG de junho é a exceção, não a origem do padrão. "
        "Por isso o texto das tabelas de junho não é extraível do PDF.",
    ),
    # ---------------------------------------------------------------- I: OOXML de base
    anomaly(
        14, "2026-08", "CABECALHO_RODAPE_LARGURA_TABELAS",
        "larguras diferentes das tabelas de cabeçalho/rodapé entre seções",
        "mesma largura útil por orientação",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[WAVE1 §I] Herança de edição; sem efeito visual relevante. O builder usa a largura "
        "útil da seção.",
    ),
    anomaly(
        14, "2026-08", "SECOES_TITLEPG_SEM_USO",
        "titlePg e referências 'first' nas seções 1 e 2", "titlePg só na seção 0 (capa)",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[WAVE1 §I] As seções 1 e 2 declaram primeira página diferente sem usá-la.",
    ),
    anomaly(
        14, "2026-08", "REALCE_PARAGRAFOS_DE_IMAGEM",
        "realce amarelo em parágrafos de imagem", "sem realce",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[WAVE1 §I] Resíduo de revisão; invisível sob a imagem, mas presente no XML.",
    ),
    # ---------------------------------------------------------------- J: conteúdo textual
    anomaly(
        13, "2026-07", "P2.4_BM_CODIGOS_RD103",
        "RD-103: BM-004.1, BM-005.1, BM-006.1 (Março–Maio/2026) + BM-010.1",
        "BM-007.1, BM-008.1, BM-009.1, BM-010.1 (Lista Mestra do nº 13)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[WAVE1 §J, §O] Códigos do nº 12 mantidos com os meses atualizados; BM-010.1 apendado "
        "no fim. 3 de 4 códigos BM da RD-103 errados no original.",
    ),
    anomaly(
        13, "2026-07", "P2.4_BM_SEPARADOR_MISTO",
        "separadores '-' e '–' misturados na lista de BM", "separador único ' - '",
        AnomalyClass.TYPO, Confidence.HIGH,
        "[WAVE1 §O] Única ocorrência do separador misto; o padrão nº 12–14 é ' - '.",
    ),
    anomaly(
        13, "2026-07", "P2.4_RCA_RODOVIA_DIVERGENTE",
        "'a) RD-104: ... RCA-512.1, referente à Análise do Relatório de Controle Ambiental "
        "da rodovia RD-102A'",
        "'... da rodovia RD-104' (Lista Mestra: RCA-512.1 = RD-104)",
        AnomalyClass.TYPO, Confidence.HIGH,
        "[WAVE1 §J, §O] Rodovia trocada dentro do próprio item da RD-104.",
    ),
    anomaly(
        13, "2026-07", "P2.4_BM_EM_ELABORACAO_ORDEM",
        "ordem dos itens da lista de BM em elaboração: RD-104 (abril a junho/2026) antes de "
        "RD-102A (março a maio/2026)",
        "ORDER_ALPHA: RD-102A antes de RD-104 (config/data_rules/p24_blocks.yaml "
        "P2.4_BM_LIST.adjacent_note)",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[golden nº 13, builder LL/MM] Única ocorrência da forma em lista do bloco "
        "P2.4_BM_EM_ELABORACAO (nº 11–12 frase genérica; ausente no nº 14): um mês só não muda "
        "a ordem do modelo. O P2.4_BM_LIST do mesmo relatório e dos nº 11–14 segue ORDER_ALPHA, "
        "e o próprio parágrafo dos BM entregues, logo acima, também. A ordem de julho é "
        "variação de formato; o default técnico continua ORDER_ALPHA.",
    ),
    anomaly(
        13, "2026-07", "P2.4_PONTO_DUPLO",
        "'boletins de medição processados..'", "'processados.'",
        AnomalyClass.TYPO, Confidence.CONFIRMED,
        "[WAVE1 §J, §O] Ponto duplo no bloco de pareceres de medição.",
    ),
    anomaly(
        13, "2026-07", "P2.4_RA_RD104_SEM_DOIS_PONTOS",
        "'RD-104 RA-…'", "'RD-104: RA-…'",
        AnomalyClass.TYPO, Confidence.CONFIRMED,
        "[WAVE1 §J, §O] As outras três rodovias do mesmo bloco trazem dois-pontos. Primeiro mês "
        "com RA; o defeito nasce aqui.",
    ),
    anomaly(
        14, "2026-08", "P2.4_RA_RD104_SEM_DOIS_PONTOS",
        "'RD-104 RA-509.1;'", "'RD-104: RA-509.1.'",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.CONFIRMED,
        "[WAVE1 §J, §O] Mesmo defeito do nº 13, propagado. Resíduo do renderizador do 2.4 no "
        "nº 14 (fatos 100%).",
    ),
    anomaly(
        12, "2026-06", "P2.4_RO_RD102A_SEM_PONTO_VIRGULA",
        "'RD-102A: RO-536.1 a RO-539.1'", "'RD-102A: RO-536.1 a RO-539.1;'",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.CONFIRMED,
        "[WAVE1 §J] Item de lista sem a pontuação dos demais; também no nº 11.",
    ),
    anomaly(
        12, "2026-06", "P2.2_MARCADOR_DIGITADO",
        "'• Disciplinas do Viário Principal:' com marcador digitado", "marcador só da numeração",
        AnomalyClass.TYPO, Confidence.CONFIRMED,
        "[WAVE1 §J] O caractere '•' foi digitado no texto, além do marcador da lista.",
    ),
    anomaly(
        12, "2026-06", "P2.1_RESUMO_PONTO_FINAL",
        "'...itens P2.1, P2.2 e P2.4' sem ponto final (nº 12–14)",
        "'...itens P2.1, P2.2 e P2.4.' com ponto, como no nº 11",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[WAVE1 §J] Pontuação perdida no nº 12 e copiada adiante. Texto gerado: padronizar "
        "(DEC-007). O trecho anômalo é a FALTA do ponto no fim do parágrafo (Gate B tentativa 3).",
    ),
    anomaly(
        14, "2026-08", "REALCE_RESIDUAL_TEXTO",
        "realce amarelo na marca do parágrafo da Apresentação e no run 'A ' do P2.1",
        "sem realce",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[WAVE1 §J] Resíduo de revisão em parágrafos de texto (distinto do realce em "
        "parágrafos de imagem, §I).",
    ),
    anomaly(
        14, "2026-08", "PARAGRAFOS_VAZIOS_COMO_ESPACAMENTO",
        "3 PargrafodaLista vazios (188–190) no 2.2 e 14 (293–306) no 2.4",
        "espaçamento pelo estilo",
        AnomalyClass.FORMAT_VARIATION, Confidence.CONFIRMED,
        "[WAVE1 §J] Parágrafos vazios usados para empurrar conteúdo; o builder não os reproduz.",
    ),
    anomaly(
        13, "2026-07", "ASSINATURA_SIGNATARIO",
        "signatário diferente do dos nº 11 e nº 12", None,
        AnomalyClass.TRUE_MODEL_CHANGE, Confidence.CONFIRMED,
        "[WAVE1 §J] Não é defeito: o signatário mudou a partir do nº 13. Consequência: o nome "
        "é entrada (signatory_name), nunca constante do modelo.",
    ),
    # ---------------------------------------------------------------- K: resumo executivo
    anomaly(
        13, "2026-07", "P2.1_RESUMO_OFICIO_SEM_DOCUMENTO",
        "'..., Ofício, Pareceres Técnicos, ...' na lista de documentos do P2.4",
        "tipo citado só se houver OF na Lista Mestra do relatório",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.HIGH,
        "[WAVE1 §K] O resumo cita 'Ofício' sem nenhum documento OF no relatório.",
    ),
    anomaly(
        14, "2026-08", "P2.1_RESUMO_OFICIO_SEM_DOCUMENTO",
        "'..., Ofício, Pareceres Técnicos, ...' na lista de documentos do P2.4",
        "tipo citado só se houver OF na Lista Mestra do relatório",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[WAVE1 §K] Parágrafo idêntico ao do nº 13.",
    ),
    anomaly(
        13, "2026-07", "P2.1_RESUMO_BM_RODOVIAS",
        "'Boletins de Medição referentes às rodovias RD-101, RD-103 e RD-104'",
        "rodovias com BM na Lista Mestra do nº 13",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[WAVE1 §K] Lista de rodovias copiada do nº 12. (O fragmento 'Na RD-101.' do mesmo "
        "parágrafo já está em P2.4_FRASE_TRUNCADA_MEDICOES.)",
    ),
    anomaly(
        14, "2026-08", "P2.1_RESUMO_BM_CONCORDANCIA",
        "Boletins de Medição referentes às rodovias RD-104.",
        "forma singular quando os BM são de uma só rodovia, como em P2.4_RM",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "[Gate B tentativa 3, W3] Lista Mestra v331/v335: os 3 BM entregues do nº 14 são da "
        "RD-104; o texto manteve o plural 'às rodovias' dos nº 12–13 (3 rodovias). O fragmento "
        "'Na RD-101.' do mesmo parágrafo já está em P2.4_FRASE_TRUNCADA_MEDICOES.",
    ),
    # ---------------------------------------------------------------- temas sem documento
    # Frases que enumeram temas de pareceres sem relação com os PA do mês (QA-C, 2026-10-01).
    # Contagem pela Descrição dos PA do 2.4 na Lista Mestra v335 (render_maps.p24_pa_themes).
    anomaly(
        12, "2026-06", "P2.1_S7_TEMAS_SEM_SUPORTE",
        "frase fixa do S7 com os seis temas de pareceres do P2.4 em todo relatório",
        "só os temas com PA do 2.4 que os sustente pela Descrição (keyword_map)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA-C] Nº 12: PA do 2.4 sustentam 3 dos 6 temas (conformidade ambiental, desapropriação, "
        "obra); saúde e segurança do trabalho, condicionantes e evidências de encerramento sem PA. "
        "A frase é idêntica nos nº 12–14, independente dos documentos do mês.",
    ),
    anomaly(
        13, "2026-07", "P2.1_S7_TEMAS_SEM_SUPORTE",
        "frase fixa do S7 com os seis temas de pareceres do P2.4 em todo relatório",
        "só os temas com PA do 2.4 que os sustente pela Descrição (keyword_map)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA-C] Nº 13: PA do 2.4 sustentam 4 dos 6 temas; condicionantes e evidências de "
        "encerramento sem PA. Frase idêntica à do nº 12.",
    ),
    anomaly(
        14, "2026-08", "P2.1_S7_TEMAS_SEM_SUPORTE",
        "frase fixa do S7 com os seis temas de pareceres do P2.4 em todo relatório",
        "só os temas com PA do 2.4 que os sustente pela Descrição (keyword_map)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA-C] Nº 14: PA do 2.4 sustentam 4 dos 6 temas; condicionantes ambientais e áreas "
        "sujeitas à desapropriação sem nenhum PA. Frase idêntica à dos nº 12–13.",
    ),
    anomaly(
        14, "2026-08", "P2.4_PARECERES_MEDICAO_ATESTE_SEM_PA",
        "frase do P2.4_PARECERES_MEDICAO cita o tema de ateste da documentação de medição sem "
        "nenhum PA desse tema no relatório",
        "tema citado só com PA que o sustente pela Descrição",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA-C] Nº 14: PA de controle tecnológico (PA-691..693, 711..713) e de eventograma "
        "(PA-708, 716, 735), nenhum de ateste; a frase é a do nº 13, que tinha PA-637, 638 e 644.",
    ),
    anomaly(
        13, "2026-07", "P2.4_PARECERES_AMB_TEMAS_SEM_SUPORTE",
        "frase fixa do P2.4_PARECERES_AMB com os seis temas ambientais em todo relatório",
        "só os temas com PA do 2.4 que os sustente pela Descrição",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA-C] Nº 13: nenhum PA de condicionantes nem de ocorrência ambiental no 2.4.",
    ),
    anomaly(
        14, "2026-08", "P2.4_PARECERES_AMB_TEMAS_SEM_SUPORTE",
        "frase fixa do P2.4_PARECERES_AMB com os seis temas ambientais em todo relatório",
        "só os temas com PA do 2.4 que os sustente pela Descrição",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA-C] Nº 14: nenhum PA de condicionantes nem de ocorrência ambiental no 2.4; frase "
        "idêntica à do nº 13.",
    ),
    # QA2-C (Gate D, 2ª rodada, 2026-10-02): mais dois textos fixos do 2.4 que afirmam temas sem
    # documento do mês. Contagem pela Descrição na Lista Mestra v335 (nº 12–14) e v134 (nº 13),
    # com os mapas config/data_rules/p24_blocks.yaml#P2.4_PARECERES_MEDICAO_2/slots e
    # #P2.4_ATAS/slots/themes.
    anomaly(
        13, "2026-07", "P2.4_PARECERES_MEDICAO_2_TEMAS_SEM_SUPORTE",
        "frase fixa do P2.4_PARECERES_MEDICAO_2 com controles geotécnicos e destaque para obras "
        "de arte corrente em todo relatório",
        "só os controles e o destaque com PA do 2.4 que os sustente pela Descrição",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA2-C] Nº 13 (1º mês da frase): os PA de medição são de controle tecnológico e "
        "topográfico (PA-636, 646, 654, 657, 663..670, 683..685), ateste (PA-637, 638, 644) e "
        "eventograma (PA-639, 640, 653, 659, 662, 678); nenhum PA geotécnico nem de obras de "
        "arte corrente.",
    ),
    anomaly(
        14, "2026-08", "P2.4_PARECERES_MEDICAO_2_TEMAS_SEM_SUPORTE",
        "frase fixa do P2.4_PARECERES_MEDICAO_2 com controles geotécnicos e destaque para obras "
        "de arte corrente em todo relatório",
        "só os controles e o destaque com PA do 2.4 que os sustente pela Descrição",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA2-C] Nº 14: PA de controle tecnológico e topográfico (PA-691..693, 711..713) e de "
        "eventograma (PA-708, 716, 735); nenhum geotécnico nem de obras de arte corrente. Frase "
        "idêntica à do nº 13.",
    ),
    anomaly(
        12, "2026-06", "P2.4_ATAS_TEMAS_SEM_SUPORTE",
        "frase fixa do P2.4_ATAS com dez temas de tratativas atribuídos às atas em todo relatório",
        "só os temas com AT do 2.4 que os sustente pela Descrição; sem tema, só a moldura factual",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA2-C] Nº 12 (1º mês da frase; o nº 11 tinha só a moldura): as 16 AT do 2.4 têm a "
        "Descrição 'Reunião de alinhamento da obra e acompanhamento dos serviços', que não cita "
        "nenhum dos dez temas.",
    ),
    anomaly(
        13, "2026-07", "P2.4_ATAS_TEMAS_SEM_SUPORTE",
        "frase fixa do P2.4_ATAS com dez temas de tratativas atribuídos às atas em todo relatório",
        "só os temas com AT do 2.4 que os sustente pela Descrição; sem tema, só a moldura factual",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA2-C] Nº 13: as 15 AT do 2.4 (AT-659.1..174.1) têm a mesma Descrição genérica; "
        "frase idêntica à do nº 12.",
    ),
    anomaly(
        14, "2026-08", "P2.4_ATAS_TEMAS_SEM_SUPORTE",
        "frase fixa do P2.4_ATAS com dez temas de tratativas atribuídos às atas em todo relatório",
        "só os temas com AT do 2.4 que os sustente pela Descrição; sem tema, só a moldura factual",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA2-C] Nº 14: AT-676.1 (RD-104) e AT-677.1 (RD-103), ambas 'Reunião de alinhamento da "
        "obra e acompanhamento dos serviços'; frase idêntica à dos nº 12–13.",
    ),
    # Varredura do QA2-C no 2.1–2.4: o S1 atribui às reuniões seis tratativas fixas. Contagem
    # pela Descrição das AT do 2.1 na Lista Mestra v335 (nº 12–14) e v134 (nº 13), com
    # config/data_rules/p21_executive_summary.yaml#render_maps/p21_meeting_topics.
    anomaly(
        12, "2026-06", "P2.1_S1_TEMAS_REUNIOES_SEM_SUPORTE",
        "frase fixa do S1 com seis tratativas atribuídas às reuniões em todo relatório",
        "só as tratativas citadas na Descrição das AT do 2.1 (render_maps.p21_meeting_topics)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA2-C varredura] Nº 12: as 9 AT do 2.1 (AT-641.1..156.1) são 'Reunião de alinhamento "
        "técnico': sustentam só o alinhamento das atividades técnicas; entregas de projeto "
        "executivo, pendências, prazos, devolutivas e suporte técnico/contratual sem AT.",
    ),
    anomaly(
        13, "2026-07", "P2.1_S1_TEMAS_REUNIOES_SEM_SUPORTE",
        "frase fixa do S1 com seis tratativas atribuídas às reuniões em todo relatório",
        "só as tratativas citadas na Descrição das AT do 2.1 (render_maps.p21_meeting_topics)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA2-C varredura] Nº 13: as 6 AT do 2.1 (AT-658.1..175.1) são 'Reunião de alinhamento "
        "técnico'; frase idêntica à do nº 12.",
    ),
    anomaly(
        14, "2026-08", "P2.1_S1_TEMAS_REUNIOES_SEM_SUPORTE",
        "frase fixa do S1 com seis tratativas atribuídas às reuniões em todo relatório",
        "só as tratativas citadas na Descrição das AT do 2.1 (render_maps.p21_meeting_topics)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[QA2-C varredura] Nº 14: nenhuma AT no 2.1 (a cláusula das Atas já sai vazia); as seis "
        "tratativas ficam sem documento. Frase idêntica à dos nº 12–13.",
    ),
    # Frase 'Paralelamente…' do S5 com atividades sem documento do 2.4 no mês (revisor W4,
    # MINOR 4). Contagem pela Lista Mestra v335 (nº 12, 14) e v134 (nº 13) com
    # render_maps.p24_activities (prefixo do Documento ou palavra-chave da Descrição).
    anomaly(
        12, "2026-06", "P2.1_S5_ATIVIDADES_SEM_SUPORTE",
        "frase fixa do S5 com as sete atividades do P2.4 em todo relatório",
        "só as atividades com documento do 2.4 que as sustente (render_maps.p24_activities)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[W4 MINOR 4] Nº 12: documentos do 2.4 sustentam 5 das 7 atividades; interferências "
        "identificadas em campo e acompanhamento contratual das obras sem documento. A frase é "
        "idêntica nos nº 12–14.",
    ),
    anomaly(
        13, "2026-07", "P2.1_S5_ATIVIDADES_SEM_SUPORTE",
        "frase fixa do S5 com as sete atividades do P2.4 em todo relatório",
        "só as atividades com documento do 2.4 que as sustente (render_maps.p24_activities)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[W4 MINOR 4] Nº 13: 6 das 7 atividades sustentadas; interferências identificadas em "
        "campo sem documento. Frase idêntica à do nº 12.",
    ),
    anomaly(
        14, "2026-08", "P2.1_S5_ATIVIDADES_SEM_SUPORTE",
        "frase fixa do S5 com as sete atividades do P2.4 em todo relatório",
        "só as atividades com documento do 2.4 que as sustente (render_maps.p24_activities)",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[W4 MINOR 4] Nº 14: 6 das 7 atividades sustentadas; interferências identificadas em "
        "campo sem documento (acompanhamento contratual pelo PA-704.1, requisição do TCE-UF). "
        "Frase idêntica à dos nº 12–13.",
    ),
    anomaly(
        13, "2026-07", "P2.1_RESUMO_DISCIPLINAS_P22",
        "frases sobre disciplinas do 2.2 iguais às do nº 12", "situação das disciplinas em julho",
        AnomalyClass.COPY_FORWARD_ERROR, Confidence.HIGH,
        "[WAVE1 §K] Frases do resumo sobre o 2.2 copiadas do mês anterior.",
    ),
    anomaly(
        13, "2026-07", "P2.1_CLAUSULA_DISCIPLINAS_REMOVIDA",
        "'Foram tratadas disciplinas como Documentação para Declaração de Utilidade Pública, "
        "[...] Projeto de Paisagismo e Projeto de Interferências.' (fim do parágrafo do 2.2 no "
        "resumo executivo, 2.1.2)",
        "cláusula ausente (padrão vigente do nº 14)",
        AnomalyClass.TRUE_MODEL_CHANGE, Confidence.CONFIRMED,
        "[QA4-H, HNK-13-020; WAVE1 §N] Não é erro de julho: a cláusula existe nos nº 12 e 13 e "
        "saiu no nº 14 (Agosto/2026), que é o padrão vigente; o modelo não a emite "
        "(p21_executive_summary.yaml#render_maps/p22_disciplines emit=false; content_blocks "
        "P2.1_SUMMARY_S3_P22 observed.disciplines_clause). A ausência no gerado do nº 13 é "
        "mudança de modelo, não correção da cópia de junho (P2.1_RESUMO_DISCIPLINAS_P22, que "
        "segue registrada como fato histórico do nº 13).",
    ),
    anomaly(
        14, "2026-08", "CONTROLE_PRODUTOS_DESCRICAO_CORTADA",
        "NT-734.1: 'Nota Técnica de Análise de Projeto Executivo - Projeto de Paisagismo, "
        "Projeto de Pavimentação e Projeto de' (2.2 p. 24 e índice de ANEXOS p. 39)",
        "'... Projeto de Pavimentação e Projeto de Interferência' (Lista Mestra v335.0, "
        "Descrição completa)",
        AnomalyClass.HISTORICAL_DEFECT, Confidence.CONFIRMED,
        "[QA2-D (a), builder MM] O recorte publicado tem altura de linha 27,6 pt e a Descrição "
        "precisa de 3 linhas (AutoFit do Excel 41,4 pt): a 3ª linha não é desenhada. Defeito de "
        "renderização do quadro, não dado: a regra nova (DEC-010 §4, max(27,6 pt, AutoFit)) "
        "mostra a descrição inteira. No mesmo relatório NT-765.1 tem a 3ª linha cortada pela "
        "borda (texto ainda extraível). O nº 13 publicado não corta (alturas variáveis).",
        page=24,
    ),
    # ---------------------------------------------------------------- M: snapshot
    anomaly(
        14, "2026-08", "SNAPSHOT_DEC008_ACERTO_ACIDENTAL",
        "DEC-008 (fim do dia da capa) escolheu v335 e bateu com o PDF",
        "critério DEC-012: última versão <= CreationDate do PDF (v331)",
        AnomalyClass.METHOD_ERROR, Confidence.CONFIRMED,
        "[WAVE1 §M] Anomalia de método, não do relatório: o v335 acertou agosto por "
        "estabilidade da planilha entre v331 e v335, não pelo critério; em julho o mesmo "
        "critério falha (PDF gerado 3 dias depois da capa). Não usar como evidência do DEC-008.",
    ),
    anomaly(
        13, "2026-07", "LISTA_MESTRA_REATRIBUICAO_RETROATIVA",
        "v294 (04/09) move 6 linhas de N° Relatório 13 para 14",
        "linhas publicadas no corpo do nº 13 mantêm o número",
        AnomalyClass.UNRESOLVED, Confidence.HIGH,
        "[WAVE1 §M] BM-007/008/009.1 da RD-102A e da RD-104, 'Em elaboração' e sem data em "
        "julho, saíram do índice do nº 13 pelo filtro de status e foram reatribuídas ao nº 14 "
        "depois da publicação. Pode ser prática legítima da planilha viva; reconstrução do nº 13 "
        "usa v162.",
    ),
]


def main() -> int:
    target = assert_write_allowed(CATALOG)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for item in ANOMALIES:
            fh.write(item.model_dump_json(exclude_none=True) + "\n")

    by_class: dict[str, int] = {}
    for item in ANOMALIES:
        by_class[item.classification.value] = by_class.get(item.classification.value, 0) + 1
    print(f"{len(ANOMALIES)} anomalias registradas em {target.relative_to(REPO_ROOT)}")
    for name, count in sorted(by_class.items()):
        print(f"  {name}: {count}")
    assert all(not a.should_learn_as_rule for a in ANOMALIES), "anomalia não pode virar regra"
    print("  todas com should_learn_as_rule=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
