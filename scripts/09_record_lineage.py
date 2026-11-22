"""FASE 3/4 — grava em `data/catalog/source_lineage.jsonl` a linhagem verificada.

    .venv\\Scripts\\python scripts\\09_record_lineage.py

Cada entrada aponta a fonte primaria de um componente, a transformacao aplicada e a
evidencia que sustenta a afirmacao. Sem prova, `status=UNKNOWN` — nunca inventar linhagem.

Reexecutar reescreve o catalogo inteiro, de forma deterministica.

Rodada 2026-10-01 (Gate A): aplica `docs/discovery/WAVE1_FINDINGS.md` §A, §B, §C, §D, §E, §H
e §M e as DEC-010 a DEC-012. Entradas refutadas foram corrigidas no lugar (o conflito fica
registrado na propria evidencia); as faixas de RO e os quadros ambientais UNKNOWN foram
substituidos pelas entradas rastreadas.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prog_g2_report import REPO_ROOT
from prog_g2_report.catalog import Confidence, Evidence, SourceLineage
from prog_g2_report.security import assert_write_allowed

CATALOG = REPO_ROOT / "data" / "catalog" / "source_lineage.jsonl"

PROJECTS_WORKBOOK = "03 - Acompanhamento de Projetos Executivo.xlsx, aba 'Projetos'"
MASTER_LIST = (
    "b!EXEMPLO-DRIVE-ID"
    ":01EXEMPLOITEMID000000000000000000"
)
ENVIRONMENTAL = (
    "04_Acompanhamento - Licenca Ambiental.xlsx (item 01EXEMPLOITEMID000000000000000000)"
)
ALL_FOUR = "Relatórios G2 nº 11 a nº 14 (Maio a Agosto/2026)"
JUL_AUG = "Relatórios G2 nº 13 e nº 14 (Julho e Agosto/2026)"


def lineage(
    component: str,
    report: str,
    source: str,
    status: str,
    confidence: Confidence,
    note: str,
    **kwargs,
) -> SourceLineage:
    return SourceLineage(
        component=component,
        report_id=report,
        source=source,
        status=status,
        confidence=confidence,
        evidence=[Evidence(report_id=report, note=note)],
        **kwargs,
    )


LINEAGE = [
    # ------------------------------------------------------------ regra de seleção
    lineage(
        "REGRA_SELECAO_DOCUMENTOS", ALL_FOUR,
        "Lista Mestra '00_ Lista mestre.xlsx'", "TRACED", Confidence.CONFIRMED,
        "A coluna 'N° Relatório' é o único seletor. O mês civil da data de entrega NÃO "
        "seleciona: PA-726.1, entregue em 01/09/2026, pertence ao relatório nº 14, enquanto "
        "PA-728.1, entregue em 02/09/2026, pertence ao nº 15. Prever o relatório pela data "
        "acerta apenas 90% dos casos entre maio e agosto de 2026.",
        source_ref=MASTER_LIST, sheet="Controle Geral", range="K (N° Relatório)",
        filter="N° Relatório == N",
    ),
    lineage(
        "REGRA_SELECAO_STATUS_ENTREGA", ALL_FOUR,
        "Lista Mestra '00_ Lista mestre.xlsx'", "PARTIAL", Confidence.MEDIUM,
        "REVISTO por DEC-012 / WAVE1 §M: 'Status Entrega' NÃO filtra o corpo (Controle de "
        "Produtos por produto = todas as linhas do relatório), mas FILTRA o índice de ANEXOS e o "
        "total do encerramento (só 'Entregue'): em julho (v162) as 6 linhas excluídas são "
        "BM-007/008/009.1 da RD-102A e da RD-104, 'Em elaboração'; em agosto (v331) as 149 "
        "estão entregues. CONFLITO registrado: a afirmação anterior ('no nº 12 há 4 documentos "
        "Em elaboração e todos estão anexados') vem da planilha ATUAL, sem snapshot de junho, "
        "e não vale como contraprova. Coluna do filtro (Status × Data Entrega preenchida): "
        "MEDIUM, as duas coincidem em v162 e v331.",
        source_ref=MASTER_LIST, sheet="Controle Geral", range="I (Status Entrega)",
        filter="corpo: nenhum; índice e encerramento: Status Entrega == 'Entregue'",
    ),
    lineage(
        "MASTER_LIST_SNAPSHOT", JUL_AUG,
        "histórico de versões da Lista Mestra no SharePoint", "TRACED", Confidence.HIGH,
        "DEC-012 (revê DEC-008): reconstrução histórica usa a última versão com "
        "lastModifiedDateTime <= CreationDate do PDF publicado. Julho: PDF 14/08 17:26:35Z → "
        "v162 (14/08 17:24:37Z, mesmo autor do docx; qualquer de v155 a v293 reproduz os 4 "
        "blocos). Agosto: PDF 08/09 18:51:16Z → v331 (3/48/98/149). O v335 do DEC-008 acertou "
        "agosto por estabilidade, não pelo critério (anomalia de método). Varridas 430 versões "
        "em memória. Produção mensal: snapshot = estado no instante da geração, registrado no "
        "manifesto (version_id + lastModified). Risco: retenção de 500 versões (GAP-015).",
        source_ref=MASTER_LIST, transformation="seleção de versão por instante de referência",
    ),
    # ------------------------------------------------------------ anexos
    lineage(
        "ANEXOS_COMPOSICAO", ALL_FOUR,
        "Lista Mestra '00_ Lista mestre.xlsx'", "TRACED", Confidence.CONFIRMED,
        "Correspondência nos relatórios nº 11, nº 12 e nº 13: 149/149, 122/122 e 165/165 "
        "linhas da Lista Mestra com arquivo anexado; no nº 14, 149 de 154 na planilha atual "
        "(as 5 faltantes foram lançadas em 21 e 22/09). Ressalvas (WAVE1 §H, §M): maio e junho "
        "têm 1 anexo fora da lista (AT-632.1), com risco de causalidade inversa; e o índice usa "
        "index_rows = N° Relatório == n ∧ Status Entrega == 'Entregue' no snapshot DEC-012 "
        "(julho v162 = 165, agosto v331 = 149).",
        source_ref=MASTER_LIST, sheet="Controle Geral", range="B4:M1442",
        filter="N° Relatório == N ∧ Status Entrega == 'Entregue' (DEC-012)",
        transformation="cada linha vira um anexo; um documento pode virar um arquivo ou uma "
        "pasta com várias peças",
        report_position="/G2/Anexos/",
    ),
    lineage(
        "ANEXOS_PASTA_NIVEL_1_PRODUTO", ALL_FOUR,
        "Lista Mestra, coluna Produto", "TRACED", Confidence.CONFIRMED,
        "686 arquivos verificados nos quatro relatórios, zero divergências entre a coluna "
        "Produto e a pasta P2.x do arquivo.",
        source_ref=MASTER_LIST, sheet="Controle Geral", range="B (Produto)",
        transformation="'2.4 GERENCIAMENTO TÉCNICO' vira a pasta 'P2.4 - Gerenciamento Tecnico "
        "de Obra'; note que o nome da pasta perde os acentos e ganha o sufixo 'de Obra'",
    ),
    lineage(
        "ANEXOS_PASTA_NIVEL_2_MANIFESTACAO", ALL_FOUR,
        "Lista Mestra, colunas Manifestação e Descrição", "TRACED", Confidence.HIGH,
        "O nome da pasta não é igual ao valor da coluna: 'Parecer' vira 'Parecer Técnico', "
        "'Relatório Semanal de Acompanhamento de Obras' vira 'Relatório Semanal de Obras'. "
        "'Nota Técnica' se divide em duas pastas conforme a Descrição começar por 'de "
        "Aceitação' ou 'de Análise', com zero cruzamentos em 128 arquivos.",
        source_ref=MASTER_LIST, sheet="Controle Geral", range="E (Manifestação) + F (Descrição)",
        transformation="mapa de renomeação, que varia entre meses e precisa de versão",
    ),
    lineage(
        "ANEXOS_PASTA_NIVEL_3_RODOVIA", ALL_FOUR,
        "Lista Mestra, coluna Empreendimento", "PARTIAL", Confidence.HIGH,
        "A rodovia vira subpasta. O nível é suprimido quando o tipo tem poucos documentos no "
        "mês. Uma única divergência em 686 arquivos: PA-598.1 consta como RD-101 na Lista "
        "Mestra e está arquivado em RD-102A; qual dos dois está certo é UNKNOWN.",
        source_ref=MASTER_LIST, sheet="Controle Geral", range="G (Empreendimento)",
    ),
    # ------------------------------------------------------------ corpo do relatório
    lineage(
        "CONTROLE_DE_PRODUTOS", ALL_FOUR,
        "Lista Mestra, recorte colado do Excel", "TRACED", Confidence.CONFIRMED,
        "Recorte das colunas Documento, Manifestação, Descrição, Empreendimento, Data Entrega "
        "e Status Entrega, colado como EMF vetorial com o autofiltro do Excel visível. No "
        "relatório nº 13 os 148 códigos do documento batem exatamente com os 148 da Lista "
        "Mestra. Nenhum documento do relatório existe fora da Lista Mestra, em nenhum mês.",
        source_ref=MASTER_LIST, sheet="Controle Geral", range="D:I, filtrado por N° Relatório",
        transformation="Excel filtrado → copiar → colar especial como metarquivo (EMF)",
        report_position="dentro de P2.1, P2.2 e P2.4, e consolidado em ANEXOS",
        width_cm=17.5, alignment="center",
    ),
    lineage(
        "CONTROL_OF_PRODUCTS", JUL_AUG,
        "Lista Mestra no snapshot, recortada pelo próprio Excel", "TRACED", Confidence.CONFIRMED,
        "DEC-010 / WAVE1 §A, prova em scripts/12_probe_emf_export.py: snapshot → filtro "
        "explícito (filtro salvo descartado) → linhas por recorte → Range.CopyPicture(xlScreen, "
        "xlPicture) → GetClipboardData(14) (CF_ENHMETAFILE) → parte OPC image/x-emf inline → "
        "Word → PDF. EMF vetorial (EMR_EXTTEXTOUTW; só as setas do autofiltro são bitmap). "
        "Um EMF por página, linhas 1–3 repetidas. nº 14: 2.1=3; 2.2=25+23; 2.4=32+34+32; "
        "anexos=31+31+39+33+15, 0 divergências; 11/11 recortes idênticos ao histórico em frame "
        "e bounds (0,001 cm). PDF do Word: Arial Nova Cond 7,23 pt (histórico 7,24). "
        "Contagens: 149 = linhas (3+48+98), 135 = códigos distintos. Rótulos = cabeçalho do "
        "snapshot. xlPrinter não reproduz; xlScreen depende de DPI (1920×1080, 120 dpi).",
        source_ref=MASTER_LIST, sheet="Controle Geral",
        filter="corpo: N° Relatório == n por Produto; índice: + Status Entrega == 'Entregue'",
        sort="ordem física da linha (padrão jul/ago)",
        transformation="Excel COM CopyPicture(xlScreen) → EMF → wp:inline 17,5 cm, altura pelo "
        "aspecto de rclBounds; altura de linha 27,6 pt; paginação gulosa até 26,2 cm",
        report_position="P2.1, P2.2, P2.4 e ANEXOS",
        width_cm=17.5, alignment="center",
    ),
    lineage(
        "ENCERRAMENTO_CONTAGEM_ANEXOS", ALL_FOUR,
        "Lista Mestra, contagem de linhas", "TRACED", Confidence.CONFIRMED,
        "O número declarado é a contagem de LINHAS ENTREGUES da Lista Mestra do relatório, não "
        "de arquivos na pasta nem de códigos distintos. Junho declara 122 e a lista tem 122; "
        "julho declara 165 = index_rows de v162 (as 6 'Em elaboração' ficam fora); agosto "
        "declara 149 = v331 (3+48+98, 135 códigos distintos). Os arquivos físicos são sempre "
        "mais numerosos.",
        source_ref=MASTER_LIST, sheet="Controle Geral", range="K (N° Relatório)",
        filter="N° Relatório == N ∧ Status Entrega == 'Entregue' (DEC-012)",
        transformation="COUNT(index_rows) no snapshot DEC-012",
        report_position="parágrafo final do ENCERRAMENTO",
    ),
    lineage(
        "ENCERRAMENTO_CONTAGEM_PAGINAS", ALL_FOUR,
        "o próprio documento renderizado", "TRACED", Confidence.CONFIRMED,
        "Declarado e real conferem nos quatro meses: 38, 43, 43 e 43. O valor 43 repetido em "
        "junho, julho e agosto não é copy-forward.",
        transformation="contagem de páginas do PDF final, por extenso entre parênteses",
        report_position="parágrafo final do ENCERRAMENTO",
    ),
    lineage(
        "P2.4_RO_RANGE", ALL_FOUR,
        "Lista Mestra, documentos do tipo Relatório Semanal", "TRACED", Confidence.CONFIRMED,
        "WAVE1 §D (substitui P2.4_FAIXAS_DE_RELATORIOS_SEMANAIS e "
        "P2.4_FAIXA_RO_DESVIO_SISTEMATICO). Um relatório semanal por rodovia, semana "
        "sábado→sexta na coluna Período; RO-NNN.V sequencial e independente por rodovia, .V = "
        "revisão (ambas anexadas). Regra CODE: faixa por rodovia = 1º e último código de "
        "N° Relatório == N ∧ Manifestação == Relatório Semanal, na ordem física, com a revisão "
        "real; período = menor início e maior fim do Período; 'até o dia 25/MM/AAAA' é texto "
        "fixo. Reproduz 76/76 da Lista Mestra e dos anexos. A divergência do texto vem de uma "
        "única semana (25/07–31/07) nas 4 rodovias: o nº 13 a omite e o nº 14 a repete "
        "(anomalias). Nunca inferir faixa por data nem por continuidade com o mês anterior. "
        "Os RO são anexo + citação; nada de dentro deles entra no texto.",
        source_ref=MASTER_LIST, sheet="Controle Geral",
        filter="N° Relatório == N e Manifestação == 'Relatório Semanal de Acompanhamento de Obras'",
        sort="ordem física da linha",
        transformation="agrupar por Empreendimento; primeiro e último código; min/max do Período",
        report_position="Produto 2.4, lista de relatórios semanais por rodovia",
    ),
    lineage(
        "CONTROLE_DE_PRODUTOS_FILTRO_POR_PRODUTO", "Relatório G2 nº 14 — Agosto/2026",
        "Lista Mestra, aba Controle Geral", "TRACED", Confidence.CONFIRMED,
        "Cada bloco dentro de um produto é a Lista Mestra filtrada por N° Relatório E por "
        "Produto. Em agosto: P2.1 tem 3 códigos no PDF e 3 na planilha (exato); P2.4 tem 98 e "
        "98 (exato); P2.2 tem 48 no PDF contra 53 na planilha de hoje, diferença que são as 5 "
        "notas digitadas depois. O índice de ANEXOS não filtra por produto: são os 149, e o "
        "multiconjunto é idêntico à união dos três blocos.",
        source_ref=MASTER_LIST, sheet="Controle Geral",
        filter="N° Relatório == N AND Produto começa com '2.X'",
    ),
    lineage(
        "CONTROLE_DE_PRODUTOS_ORDENACAO", ALL_FOUR,
        "Lista Mestra, ordem física das linhas", "TRACED", Confidence.CONFIRMED,
        "A ordem é a da varredura da planilha de cima para baixo, sem ordenação nenhuma. "
        "REVISTO (WAVE1 §H): os '~17 mil pares' saem de 4 sequências de um único mês (o índice "
        "é a união das outras três), e o acerto estrito por data é 89,5%, não 94%. Agosto "
        "sustenta: as 4 sequências do PDF são idênticas às do snapshot. Maio CONTRADIZ: o "
        "índice do nº 11 está ordenado por código (HISTORICAL_PATTERN). Regra CONFIRMED só "
        "para o padrão vigente (julho/agosto). O XML da planilha não tem sortState. O builder "
        "não aplica ORDER BY no Controle de Produtos (os blocos de texto do 2.4 têm ordens "
        "próprias do modelo, WAVE1 §O).",
        source_ref=MASTER_LIST, sheet="Controle Geral",
        sort="ordem física da linha na planilha",
    ),
    lineage(
        "INDICE_ANEXOS_LAYOUT", "Relatório G2 nº 14 — Agosto/2026",
        "Lista Mestra, aba Controle Geral", "TRACED", Confidence.CONFIRMED,
        "Mesmas seis colunas dos blocos por produto, mas com larguras diferentes: no índice de "
        "anexos as colunas começam em x = 58/113/201/364/423/482, e nos blocos por produto em "
        "58/115/208/378/439/501. São dois layouts distintos e o builder precisa dos dois.",
        source_ref=MASTER_LIST, sheet="Controle Geral",
        filter="N° Relatório == N (sem filtro de produto)",
        report_position="páginas 39 a 43 de agosto",
    ),
    # ------------------------------------------------------------ cadeia de dados do P2.2
    lineage(
        "P2.2_CADEIA_DE_DADOS", ALL_FOUR,
        "03 - Acompanhamento de Projetos Executivo.xlsx", "TRACED", Confidence.CONFIRMED,
        "Cadeia interna provada por fórmula, toda dentro do mesmo arquivo: a aba GED é o log "
        "bruto, uma linha por entrega; a aba Projetos casa (Obra, GRUPO, Disciplina) com a "
        "linha vigente do GED por INDEX de matriz; a aba 'Painel de Controle' lê Projetos com "
        "a rodovia embutida na fórmula de cada grupo de colunas. A direção é inequívoca: o "
        "Excel está a montante e o Power BI a jusante.",
        sheet="GED -> Projetos -> Painel de Controle",
        range="GED!A1:T1030 -> Projetos!A1:X102 -> Painel de Controle!B4:Q27",
        sort="Projetos coluna A, 'Ordem Disciplina', define a ordem de apresentação",
    ),
    lineage(
        "P2.2_QUADRO_PROJETOS_DASHBOARD", ALL_FOUR,
        "painel Power BI construído sobre a aba Projetos", "TRACED", Confidence.CONFIRMED,
        "É captura de tela, não recorte de planilha. Provas: o texto não é extraível do PDF "
        "em nenhum dos 16 casos; a pasta de trabalho não tem nenhuma parte de gráfico, nem "
        "cache de tabela dinâmica, nem segmentação, logo não poderia desenhar a rosca; a "
        "largura em pixels nunca se repete entre rodovias do mesmo mês; e o recorte de maio "
        "capturou o cabeçalho de visual do Power BI e o ícone de limpar seleção, que só "
        "aparecem ao passar o mouse na interface. Casamento de valores com o arquivo vivo: "
        "14 de 22 linhas idênticas em RD-103, e todas as divergências são linhas que avançaram "
        "depois da data impressa no próprio quadro.",
        sheet="Projetos", range="A1:X102",
        filter="Obra == rodovia (filtro de página do painel)",
        sort="Disciplina, pela coluna 'Ordem Disciplina'",
        transformation="painel renderizado -> print de tela a 120 dpi -> PNG inline no Word",
        report_position="P2.2, quatro blocos na ordem RD-103, RD-102A, RD-101, RD-104",
        width_cm=17.5, alignment="inline, largura do texto",
    ),
    lineage(
        "P2.2_QUADRO_PAINEL_DE_CONTROLE", "Relatórios G2 nº 11 e nº 12",
        "03 - Acompanhamento de Projetos Executivo.xlsx, aba 'Painel de Controle'",
        "TRACED", Confidence.CONFIRMED,
        "Intervalo provado por geometria, não por nome: as sete posições de coluna medidas no "
        "PDF batem com as calculadas a partir das larguras da planilha, com erro menor que um "
        "ponto. A rodovia está embutida na fórmula de cada grupo de colunas, o que fixa o "
        "mapeamento sem depender do rótulo. A formatação condicional da aba cobre exatamente "
        "F6:Q27, confirmando o bloco de forma independente. Prova de que é render de célula: "
        "um texto longo aparece truncado no limite da coluna. COMPONENTE DESCONTINUADO a "
        "partir do relatório nº 13; o motivo é UNKNOWN.",
        sheet="Painel de Controle",
        range="RD-103 = B4:H27; RD-102A = B4:E27 + I4:K27; RD-101 = B4:E27 + L4:N27; "
              "RD-104 = B4:E27 + O4:Q27",
        filter="nenhum: a aba não tem autofiltro, print area nem colunas ocultas",
        sort="nenhuma; ordem física das linhas 6 a 27",
        transformation="copiar como imagem -> EMF -> redimensionado a 70,1%, aspecto preservado",
        width_cm=17.5,
    ),
    # ------------------------------------------------------------ segunda fonte estruturada
    lineage(
        "P2.2_STATUS_DISCIPLINAS_POR_RODOVIA", "Relatório G2 nº 14 — Agosto/2026",
        PROJECTS_WORKBOOK, "TRACED", Confidence.HIGH,
        "Os blocos de status por rodovia NÃO vêm da Lista Mestra, que não tem status de "
        "disciplina. Vêm da aba 'Projetos', colunas Obra, GRUPO, Disciplina, "
        "'Disciplina ACEITA?', 'Status (SITUAÇÃO)' e 'Status (AVALIAÇÃO)'. Mapeamento: "
        "Aceitação = ACEITA? é Sim; Aprovação = AVALIAÇÃO começa com 'Aprovad'; Em análise = "
        "SITUAÇÃO é 'Em análise'; Pendentes de aprovação = ACEITA Sim e AVALIAÇÃO Reprovado; "
        "Não entregues = SITUAÇÃO Atrasado sem data de recebimento. Validado: RD-101 Fase de "
        "Estudos bate 8 de 8; RD-103 Viário Secundário bate 5 de 5. "
        "ATENÇÃO: há lista de exclusão obrigatória (Equipe Fixa de Projeto, Projeto Executivo, "
        "Memoriais Descritivos da Obra nunca aparecem no texto) e a grafia 'RD-102 A' na "
        "planilha difere de 'RD-102A' no relatório. Snapshot (WAVE1 §E, DEC-012): v328 (nº 13) "
        "e v438 (nº 14) reproduzem 100% das linhas e células dos 8 quadros; blocos de status "
        "sem contradição no nº 13 e com uma no nº 14 (texto redigido com v429–v436). "
        "'Pendentes de aprovação' = ACEITA Sim, AVALIAÇÃO Reprovado e 'Entrega da Revisão' "
        "aguardando ou vencida no corte: hipótese MEDIUM.",
        sheet="Projetos",
        transformation="filtro por obra e grupo, depois verbalização em lista",
        report_position="Produto 2.2, um bloco por rodovia",
    ),
    lineage(
        "P2.4_BLOCOS_QUE_CITAM_DOCUMENTOS", "Relatório G2 nº 14 — Agosto/2026",
        "Lista Mestra, aba Controle Geral", "TRACED", Confidence.CONFIRMED,
        "Os oito blocos que citam códigos derivam da Lista Mestra filtrada por N° Relatório e "
        "agrupada por Manifestação e Empreendimento: relatórios mensais de obra, boletins de "
        "medição (mês da Descrição; 'realizadas' exige Status Entrega == 'Entregue'), "
        "inspeções de alojamento, relatórios ambientais consolidados, análises de controle "
        "ambiental, não conformidades, lista de produtos por rodovia e faixas de relatório "
        "semanal (P2.4_RO_RANGE, fechado pela WAVE1 §D). Renderizador da WAVE1 §O: fatos 100% "
        "nos nº 13 e 14; resíduo de texto = anomalias registradas.",
        source_ref=MASTER_LIST, sheet="Controle Geral",
        filter="N° Relatório == N, agrupado por Manifestação e Empreendimento",
        transformation="colapsar códigos em faixa ou lista, por rodovia",
    ),
    lineage(
        "P2.4_NC_ENUMERACAO", "Relatórios G2 nº 12 e nº 13 (Junho e Julho/2026)",
        "Lista Mestra, aba Controle Geral", "TRACED", Confidence.HIGH,
        "WAVE1 §C: não existe painel de NC em nenhum relatório (nº 01 a nº 14). NC é texto: "
        "frase fixa (nº 05–14) + enumeração opcional dos códigos por rodovia + complemento de "
        "RNC (só nº 14, MEDIUM). A enumeração vem da Lista Mestra, 100% nos nº 12 e 13. Quando "
        "enumerar é editorial (enumera com 2 e 4 NC, não com 8 a 25: LOW) → GAP-013, default "
        "enumerar sempre. Grafia dupla da Manifestação exige normalização.",
        source_ref=MASTER_LIST, sheet="Controle Geral",
        filter="N° Relatório == N ∧ Manifestação normalizada == 'notificação de não conformidade'",
        transformation="agrupar por Empreendimento; natureza pela Descrição; ordem alfabética "
        "de rodovia (WAVE1 §O)",
        report_position="Produto 2.4, parágrafo de não conformidades",
    ),
    lineage(
        "NC_WORKBOOK_02_NAO_E_FONTE", ALL_FOUR,
        "02_Acompanhamento de NC automatizada.xlsm", "NOT_A_SOURCE", Confidence.CONFIRMED,
        "WAVE1 §C: a planilha NÃO alimenta o Relatório G2. O preenchimento parou em jan/2026 e "
        "nomenclatura e status divergem dos relatórios; a enumeração de NC sai da Lista "
        "Mestra. Não usar como fonte, nem para painel (que nunca existiu) nem para texto.",
    ),
    lineage(
        "RESUMO_EXECUTIVO", ALL_FOUR,
        "molde com slots; parte derivável da Lista Mestra", "TRACED", Confidence.HIGH,
        "NÃO é síntese livre: 5 dos 9 parágrafos são byte a byte idênticos aos dos relatórios "
        "nº 12 e nº 13. É uma sequência de slots fixos em que poucos variam, e a variação é "
        "enumerativa. Gatilho validado nos quatro meses: o slot de documentos de padronização "
        "só existe se houver documento com prefixo IT, CT ou POP na Lista Mestra do relatório; "
        "agosto não tem nenhum e o slot some. Só o parágrafo de temas dos pareceres exige "
        "síntese real. WAVE1 §K: das 19 afirmações de agosto, 47% fixas e 42% deriváveis da "
        "Lista Mestra (≈90%), 5% interpretativas, 5% anomalia; cláusula das Atas ⇔ existe AT "
        "(4/4); a agenda de reuniões tem hora EXTERNAL (entrada).",
        source_ref=MASTER_LIST, sheet="Controle Geral",
        report_position="Produto 2.1, parágrafos finais",
    ),
    lineage(
        "P2.2_DESAPROPRIACAO_E_INTERFERENCIAS", "Relatório G2 nº 14 — Agosto/2026",
        "entrada humana estruturada (input p22_external_status)", "TRACED", Confidence.CONFIRMED,
        "Busca por 'GDP', 'Casa Civil', 'GFD' e 'EnergiaX' em todas as células das três "
        "planilhas baixadas e na Lista Mestra: ZERO ocorrências. WAVE1 §H achou menções "
        "laterais (linhas 'Projeto de Desapropriação/Interferência' na aba Projetos; GED!T990 "
        "cita GFD/RD-104), e a varredura da WAVE1 §E (12 termos em 4.294 itens, 196 "
        "planilhas) confirmou: não existe planilha de acompanhamento de DUP, GDP, Casa Civil "
        "ou interferências. É entrada humana, estruturada por rodovia (GDP, Casa Civil, "
        "interferências com a concessionária); a Análise Programa é derivada da aba Projetos "
        "(QA2-E, schema.derived.prog). Além disso, o conteúdo de DUP já existia nos relatórios nº 11 e "
        "nº 12 embutido como observação dentro de cada rodovia: agosto promoveu a seção "
        "própria, é reestruturação, não informação nova. Só o bloco de interferências com a "
        "concessionária é estreia absoluta, com um único mês de evidência.",
        report_position="Produto 2.2",
    ),
    # ------------------------------------------------------------ assets
    lineage(
        "BLOCO_PAISAGEM_INSTITUCIONAL", ALL_FOUR,
        "assets institucionais fixos (sha1 estável)", "TRACED", Confidence.CONFIRMED,
        "Oito páginas paisagem, uma imagem por página, sem texto além do cabeçalho. Seis "
        "imagens têm sha1 idêntico nos quatro meses e quatro são idênticas de junho em diante. "
        "São arquivos prontos, reutilizados, não gerados.",
        transformation="imagem de página inteira, 26,20 × 14,74 cm",
        report_position="seção 2, páginas 7 a 14",
        width_cm=26.2, alignment="center",
    ),
    lineage(
        "CAPA", ALL_FOUR,
        "objeto OLE PowerPoint embutido no DOCX", "TRACED", Confidence.HIGH,
        "WAVE1 §I: body[0] com w:object + v:shape absoluto (na frente) + o:OLEObject "
        "PowerPoint.Show.12; prévia image1.emf de 11 MB (EMF+ com JPEG + fallback DIB). Sem "
        "seção própria: a seção 0 tem titlePg. Slide 19,05 × 27,517 cm; campos variáveis sp "
        "id=41 ('Relatório Mensal N° {n}') e sp id=42 ('DD de Mês de AAAA'); mídias e layout "
        "byte-idênticos nos 4 meses. O Word exporta a prévia guardada (defeitos de julho e "
        "agosto). Geração: DEC-011, fundo estático + textos do Word em posição absoluta.",
        transformation="DEC-011 (b'): asset de fundo com sha1 + report_number e issue_date",
        report_position="página 1",
    ),
    # ------------------------------------------------------------ lacunas
    lineage(
        "CRONOGRAMAS_POR_RODOVIA_P2.2", ALL_FOUR,
        "UNKNOWN", "UNKNOWN", Confidence.UNKNOWN,
        "Uma imagem PNG por rodovia, regerada todo mês. A planilha de origem é provavelmente "
        "'03 - Acompanhamento de Projetos Executivo.xlsx', mas a correspondência entre "
        "intervalo da planilha e recorte da imagem ainda não foi provada.",
        report_position="P2.2, um por rodovia",
    ),
    # ------------------------------------------------------------ fonte ambiental (WAVE1 §B)
    lineage(
        "P2.4_LICENSE_PANEL", ALL_FOUR,
        ENVIRONMENTAL, "TRACED", Confidence.CONFIRMED,
        "Painel 'Índices de Acompanhamento Ambiental' (1/mês) reconstruído do dado (DEC-009). "
        "Aba 'Licenças', cabeçalho na linha 2, B:P, TODAS as linhas: total = linhas; emitidas "
        "= 'Nº Licença' preenchido; pendentes = Status == 'Aguardando a liberação'; pizza "
        "vigente/pendente; barras por rodovia (decrescente, empate alfabético: HIGH); fases "
        "por 'Fase da licença'; tabela Rodovia/Empresa/Processo/Licença/Fase/Validade/Status/"
        "Link (ordem e nomes de empresa MEDIUM: o mapa vem do modelo Power BI). Contagens "
        "CONFIRMED nos nº 11–14. A aba 'Dashboard' é legada e NÃO é o painel. 346 versões desde "
        "2025-12-08, lidas só em memória. Snapshot = última versão <= 'Atualizado em' do "
        "painel (nº 13 v289, nº 14 v310); DEC-008 refutado para esta fonte (v311 diverge em "
        "RD-103 por edição de 08/09).",
        sheet="Licenças", range="B:P (cabeçalho linha 2)",
        filter="nenhum (autofiltro salvo descartado)",
        transformation="contagens e agrupamentos → render próprio (DEC-009)",
        report_position="Produto 2.4, bloco de licenças",
    ),
    lineage(
        "P2.4_CONDITIONS_PANELS", ALL_FOUR,
        ENVIRONMENTAL, "TRACED", Confidence.CONFIRMED,
        "Painéis 'Status das Condicionantes' (4/mês, um por rodovia). Aba 'Condicionantes', "
        "cabeçalho linha 2, A:L, contagem Responsável → rodovia × Status; 0 aparece como '--'. "
        "Só batem INCLUINDO as linhas ocultas pelo autofiltro (confirma DEC-009 §3). Rodovia "
        "pela aba 'Empresas' (CSG=RD-101, CLX=RD-102a, Delta=RD-103, Tetra=RD-104). O Status "
        "é fórmula com TODAY(): recalculado com a data 'Atualizado em' dá 0 divergências (nº 13 "
        "v289, nº 14 v310). Regra: Observações 'Finalizada' → Finalizada; 'Atendida' → usa "
        "Próxima entrega (K); senão Data da entrega (F); dias <= 0 → Pendente, <= 30 → Próximo "
        "do vencimento, senão No prazo. O gerador recalcula com data de referência explícita "
        "(GAP-012, default = instante da geração) e nunca usa o valor em cache. Texto do 2.4 "
        "sobre licenças e condicionantes bate 100% (0 / 1 / >1 próximas).",
        sheet="Condicionantes + Empresas", range="Condicionantes!A:L (cabeçalho linha 2)",
        filter="nenhum: inclui linhas ocultas",
        transformation="status recalculado na data de referência → contagem rodovia × status",
        report_position="Produto 2.4, um painel e um item de texto por rodovia",
    ),
]


def main() -> int:
    target = assert_write_allowed(CATALOG)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for item in LINEAGE:
            fh.write(item.model_dump_json(exclude_none=True) + "\n")

    by_status: dict[str, int] = {}
    for item in LINEAGE:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    print(f"{len(LINEAGE)} entradas de linhagem em {target.relative_to(REPO_ROOT)}")
    for name, count in sorted(by_status.items()):
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
