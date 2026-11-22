"""Catálogo das mutações adversariais das TRÊS rodadas de QA-E do Relatório G2 nº 14 (Gate D).

Fonte: tmp/agent_QAE/mutations.py (rodada 1), tmp/agent_QAE2/mutations.py (rodada 2) e
tmp/agent_QAE3/mutations_{old,new,pdf2,x}.py (rodada 3, páginas do 14_final = 14_v5, 43
páginas), com os resultados em res_*.json. Cada mutação é um dict declarativo de
`prog_g2_report.qa.mutate` com:

    name     nome da rodada (r1_/r2_/r3_ e o nome original)
    expect   "text"  — muda o TEXTO: tem de reprovar pelo diff estrito (`text_diff` novo);
             "fail"  — não é texto (imagem, cabeçalho/rodapé, numeração): tem de reprovar;
             "raster_limit" — conteúdo DENTRO de figura raster que passou na rodada 3 e que
                      o diff de texto não vê (sem OCR): limitação documentada (xfail estrito)
    passed_round3  True nas 13 mutações de texto que passaram no comparador 3.0 (QA3-E) e nas
             de raster que passaram

O nome do signatário não aparece aqui: a mutação `signer` o lê do PDF em tempo de execução.
"""

from __future__ import annotations


def _s(name, page, old, new, hits=1, expect="text", **kw):
    return {"name": name, "op": "sub", "page": page, "old": old, "new": new, "hits": hits,
            "expect": expect, **kw}


def _f(name, section, old, new, nth=0, **kw):
    return {"name": name, "op": "f_sub", "section": section, "old": old, "new": new, "nth": nth,
            "expect": "text", **kw}


ROUND_1_AND_2 = [
    # ---- rodada 1 (QA-E), páginas do 14_final
    {"name": "r1_redact_dashboard_p18", "op": "redact_image", "page": 18, "expect": "fail"},
    {"name": "r1_redact_env_panel_p29", "op": "redact_image", "page": 29, "expect": "fail"},
    {"name": "r1_del_page6_raw", "op": "del_page", "page": 6, "fix": False, "expect": "text"},
    {"name": "r1_del_page6_fixdecl", "op": "del_page", "page": 6, "fix": True,
     "expect": "text"},
    {"name": "r1_del_page24_fixdecl", "op": "del_page", "page": 24, "fix": True,
     "expect": "text"},
    _s("r1_code_swap_anexos", 39, "NT-726.1", "NT-926.1"),
    _s("r1_code_swap_p22", 24, "NT-726.1", "NT-926.1"),
    _s("r1_code_swap_text_24", None, "RO-545.1", "RO-546.1"),
    _s("r1_month_presentation", 3, "Agosto/2026", "Julho/2026"),
    _s("r1_month_all", None, "Agosto/2026", "Julho/2026", 10),
    _s("r1_cover_number", 1, "14", "15"),
    _s("r1_cover_date", 1, "08 de Setembro", "08 de Outubro"),
    _s("r1_declared_annexes", None, "149 (cento", "148 (cento"),
    _s("r1_pc_dates_month", 24, "10/08/2026", "10/07/2026", 20),
    _s("r1_pc_status", 24, "Entregue", "Pendente", 5),
    _s("r1_pc_road_cell", 24, "RD-103", "RD-104", 1),
    _s("r1_pc_description", 24, "Topografia", "Drenagem", 1),
    _s("r1_narr_bm_numbers", 15, "07, 08 e 09", "06, 07 e 08"),
    _s("r1_narr_meeting_hour", 5, "às 10h", "às 15h"),
    _s("r1_narr_report_ref", 5, "N° 09", "N° 08"),
    {"name": "r1_drop_dashboard_p18", "op": "drop_image", "page": 18, "expect": "fail"},
    {"name": "r1_blank_dashboard_p18", "op": "blank_image", "page": 18, "expect": "fail"},
    {"name": "r1_blank_env_panel_p29", "op": "blank_image", "page": 29, "expect": "fail"},
    {"name": "r1_wipe_pc_page25", "op": "wipe_body", "page": 25, "expect": "text"},
    {"name": "r1_wipe_text_page22", "op": "wipe_body", "page": 22, "expect": "text"},
    {"name": "r1_swap_dashboards_18_19", "op": "swap_images", "a": 18, "b": 19,
     "expect": "fail"},
    # ---- rodada 2 (QA2-E)
    _s("r2_24_number_dias", 27, "dias 26 e 25", "dias 26 e 24"),
    _s("r2_24_word_count_licencas", 28, "oito licen", "nove licen"),
    _s("r2_24_word_count_cinco", 28, "cinco licen", "três licen"),
    _s("r2_24_rodovias_quatro", 28, "alojamentos das quatro", "alojamentos das três"),
    _s("r2_24_bm_month", 28, "Abril/2026", "Março/2026"),
    _s("r2_24_rm_road", 27, "RM-011.1 referente à RD-104", "RM-011.1 referente à RD-101"),
    _s("r2_24_cond_negation", 30, "não há condicionantes pendentes",
       "há condicionantes pendentes"),
    # "B) RD-102A:" não existe num span só no 14_final (QA3-E: NOT FOUND); r2_22_road_nospace
    # é a mesma mutação no texto que existe
    _s("r2_22_status_road", 22, "RD-102A:", "RD-101:"),
    _s("r2_22_status_value_flip", 22, "Análise Programa: Aprovado;", "Análise Programa: Não aprovado;"),
    _s("r2_22_status_neg_removed", 23, "Análise Programa: Não aprovado;", "Análise Programa: Aprovado;"),
    _s("r2_22_publication_date", 22, "Publicado em 01/09/2026", "Publicado em 02/09/2026"),
    _s("r2_22_aprovacao_aceitacao", 18, "Aprovação: Todas", "Aceitação: Todas"),
    _s("r2_22_nivel_1_2", 19, "aceitos em 1º nível", "aceitos em 2º nível"),
    _s("r2_22_percent", 18, "40% do valor", "45% do valor"),
    _s("r2_21_company_swap", 5, "com a DELTA", "com a CSG"),
    _s("r2_21_weekday", 5, "às quintas, às 11h", "às sextas, às 11h"),
    _s("r2_25_negation", 35, "não houve atividades", "houve atividades"),
    {"name": "r2_closing_signer", "op": "signer", "new": "Tal", "expect": "text"},
    {"name": "r2_anexos_row_removed", "op": "redact_pc_row", "page": 39, "code": "NT-726.1",
     "expect": "text"},
    {"name": "r2_anexos_row_removed_fixdecl", "op": "redact_pc_row", "page": 39,
     "code": "NT-726.1", "fix_annex": 148, "expect": "text"},
    {"name": "r2_24_pc_row_removed", "op": "redact_pc_row", "page": 32, "code": "RO-545.1",
     "expect": "text"},
    _s("r2_anexos_status_cell", 39, "Entregue", "Pendente", 1),
    {"name": "r2_panel_updated_date", "op": "paint", "page": 29,
     "frac": [0.817, 0.008, 0.905, 0.031], "text": "Atualizado em 08/10/2026", "expect": "fail"},
    {"name": "r2_panel_kpi_pendentes", "op": "paint", "page": 29,
     "frac": [0.80, 0.064, 0.86, 0.10], "text": " 3", "expect": "fail"},
    {"name": "r2_panel_kpi_pendentes_b", "op": "paint", "page": 29,
     "frac": [0.835, 0.068, 0.87, 0.097], "text": "3", "expect": "raster_limit",
     "passed_round3": True},
    {"name": "r2_swap_env_panels_30_31", "op": "swap_images", "a": 30, "b": 31,
     "expect": "fail"},
    _s("r2_22_road_nospace", 22, "RD-102A:", "RD-101:", 1),
    {"name": "r2_22_quadro_cell", "op": "paint", "page": 18,
     "frac": [0.55, 0.30, 0.70, 0.36], "text": "Reprovado", "expect": "raster_limit",
     "passed_round3": True},
    # ---- rodada 2, no nível dos fatos (segmentos do extrator)
    {"name": "r2_fx_dup_paragraph_212", "op": "f_dup_seg", "section": "2.1.2",
     "needle": "Adicionalmente, foram emitidos pareceres técnicos no âmbito do Produto P2.4",
     "expect": "text"},
    {"name": "r2_fx_del_paragraph_212", "op": "f_del_seg", "section": "2.1.2",
     "needle": "Adicionalmente, foram emitidos pareceres técnicos no âmbito do Produto P2.4",
     "expect": "text"},
    {"name": "r2_fx_swap_roads_22", "op": "f_swap_segs", "section": "2.2.2",
     "a": "A) RD-103:", "b": "B) RD-102A:", "expect": "text"},
    {"name": "r2_fx_swap_status_same_road_22", "op": "f_swap_segs", "section": "2.2.2",
     "a": "• Análise Programa: Aprovado;", "b": "• Análise Programa: Não aprovado;", "expect": "text"},
    _f("r2_fx_swap_license_counts_24", "2.4.2", "duas licenças", "cinco licenças"),
    {"name": "r2_fx_pc_drop_anexos", "op": "pc_drop", "block": "ANEXOS", "index": 10,
     "expect": "text"},
    {"name": "r2_fx_pc_drop_24", "op": "pc_drop", "block": "2.4", "index": 5, "expect": "text"},
    {"name": "r2_fx_pc_dup_anexos", "op": "pc_dup", "block": "ANEXOS", "index": 10,
     "expect": "text"},
    {"name": "r2_fx2_del_38w_24", "op": "f_del_seg", "section": "2.4.2",
     "needle": "Os documentos contemplam a análise dos ensaios", "expect": "text"},
]

# Página inteira apagada (total coerente) e corpo da página apagado, página a página
# (rodadas 1 e 2: sweep_del_NN e wsweep_NN). A capa (página 1) fica fora, como no QA.
PAGE_SWEEPS = (
    [{"name": f"r2_sweep_del_{n:02d}", "op": "del_page", "page": n, "fix": True,
      "renumber": True, "expect": "text"} for n in range(2, 44)]
    + [{"name": f"r2_wsweep_{n:02d}", "op": "wipe_body", "page": n, "expect": "text"}
       for n in range(2, 44)]
)

ROUND_3 = [
    # ---- PDF
    _s("r3_n01_disc_name_swap_pdf", 20, "Geométrico e Interseções encontra-se",
       "de Drenagem encontra-se"),
    _s("r3_n05_ro_code_in_range", 27, "RO-539.1 a RO-542.1", "RO-540.1 a RO-542.1"),
    _s("r3_n06_weekly_period_end", 27, "01/08/2026 a 28/08/2026", "01/08/2026 a 29/08/2026"),
    _s("r3_n09_contract_number", 3, "Contrato N° 00/0000-PARC", "Contrato N° 01/0000-PARC"),
    _s("r3_n09b_contract_party", 3, "00/0000-PARC", "00/0000-SUP", passed_round3=True),
    _s("r3_n10_signature_month", 37, "09 de Setembro de 2026", "09 de Outubro de 2026"),
    _s("r3_n11_index_doc_type", 39, "Nota Técnica", "Parecer", 1),
    {"name": "r3_n12_del_26_paragraph", "op": "redact_line", "page": 36,
     "needle": "relacionadas ao produto 2.6", "expect": "text"},
    _s("r3_n12b_26_product_number", 36, "relacionadas ao produto 2.6",
       "relacionadas ao produto 2.5"),
    {"name": "r3_n13_toc_page_number", "op": "toc_page", "line": "2.4 Produto 2.4",
     "number": "29", "expect": "text", "passed_round3": True},
    _s("r3_n13b_toc_title", 2, "Recebimento de Obra", "Entrega de Obra", passed_round3=True),
    _s("r3_n14_header_confidencial", 27, "-CONFIDENCIAL-", "-PÚBLICO-", expect="fail"),
    _s("r3_n15_printed_page_number", 27, "27", "72", expect="fail"),
    {"name": "r3_n16_kpi_clean_8_to_6", "op": "paint", "page": 29,
     "frac": [0.811, 0.066, 0.841, 0.094], "text": "6", "clean": True, "expect": "fail"},
    {"name": "r3_n16b_kpi_clean_8_to_9", "op": "paint", "page": 29,
     "frac": [0.811, 0.066, 0.841, 0.094], "text": "9", "clean": True, "expect": "fail"},
    {"name": "r3_n16c_kpi_8_to_83", "op": "paint", "page": 29,
     "frac": [0.835, 0.068, 0.87, 0.097], "text": "3", "expect": "raster_limit",
     "passed_round3": True},
    _s("r3_n17_consortium_member", 3, "Dynatest Engenharia LTDA", "Dynatest Consultoria LTDA",
       passed_round3=True),
    _s("r3_n18_pc_date_day", 32, "10/08/2026", "11/08/2026"),
    # ---- PDF, 2ª leva (pdf2): as que passaram na rodada 3 também no PDF
    _s("r3_p21_todas_nem", 18, "Aprovação: Todas", "Aprovação: Nem todas", passed_round3=True),
    _s("r3_p19_casa_civil", 22, "Aguardando aceite da GDP", "Publicada, aceite da GDP",
       passed_round3=True),
    _s("r3_p22_gdp", 22, "Solicitado", "Dispensado", passed_round3=True),
    _s("r3_p07c_algumas_todas", 30, "algumas", "todas as", passed_round3=True),
    _s("r3_p24_rca", 32, "Encaminhado e analisado", "Encaminhado e devolvido",
       passed_round3=True),
    # ---- fatos
    _f("r3_n01_disc_name_swap", "2.2.2", "o Projeto Geométrico e Interseções encontra-se aprovado",
       "o Projeto de Drenagem encontra-se aprovado"),
    _f("r3_n01b_disc_out_of_vocab", "2.2.2", "Orçamento e Memoriais de Cálculo e o Cronograma",
       "Orçamento e Memoriais de Cálculo e o Plano de Ataque"),
    {"name": "r3_n02_disc_move_group", "op": "chain", "expect": "text", "ops": [
        {"op": "f_sub", "section": "2.2.2",
         "old": "Disciplinas pendentes de aprovação: Projeto de Terraplenagem;",
         "new": "Disciplinas pendentes de aprovação: nenhuma;"},
        {"op": "f_sub", "section": "2.2.2",
         "old": "Disciplinas pendentes de aprovação: Projeto de Sinalização",
         "new": "Disciplinas pendentes de aprovação: Projeto de Terraplenagem, Projeto de "
                "Sinalização"}]},
    {"name": "r3_n02b_disc_swap_between_groups", "op": "f_swap_substr", "section": "2.2.2",
     "a": "Disciplinas pendentes de aprovação: Projeto de Terraplenagem",
     "b": "Disciplinas pendentes de aprovação: Estudos Geotécnicos e Sondagens",
     "expect": "text"},
    _f("r3_n03_add_ressalva_other_block", "2.2.2", "Todas as disciplinas encontram-se aprovadas",
       "Todas as disciplinas encontram-se aprovadas com ressalva"),
    # QA3-E n03b mirava "encontram- se aprovados com ressalva" do 14_final; no 14_v5 (DEC-015)
    # a frase é por disciplina: a mesma mutação ("sem ressalva") na frase que existe
    _f("r3_n03b_sem_ressalva", "2.2.2",
       "O Projeto de Terraplenagem encontra-se aprovado com ressalva",
       "O Projeto de Terraplenagem encontra-se aprovado sem ressalva"),
    # v4 (DEC-015): a ressalva por disciplina não pode voltar a ser generalizada nem trocar de
    # disciplina
    _f("r4_ressalva_removida", "2.2.2",
       "O Projeto de Terraplenagem encontra-se aprovado com ressalva",
       "O Projeto de Terraplenagem encontra-se aprovado"),
    _f("r4_ressalva_trocada", "2.2.2",
       "o Projeto Geométrico e Interseções encontra-se aprovado. O Projeto de Terraplenagem "
       "encontra-se aprovado com ressalva",
       "o Projeto de Terraplenagem encontra-se aprovado. O Projeto Geométrico e Interseções "
       "encontra-se aprovado com ressalva"),
    _f("r4_ressalva_generalizada", "2.2.2",
       "o Projeto Geométrico e Interseções encontra-se aprovado. O Projeto de Terraplenagem "
       "encontra-se aprovado com ressalva",
       "o Projeto Geométrico e Interseções e o Projeto de Terraplenagem encontram-se "
       "aprovados com ressalva"),
    {"name": "r3_n04_pc_swap_same_code", "op": "pc_swap", "block": "2.4", "i": 21, "j": 22,
     "expect": "text"},
    {"name": "r3_n04b_pc_swap_same_code_anexos", "op": "pc_swap", "block": "ANEXOS", "i": 42,
     "j": 43, "expect": "text"},
    _f("r3_n05b_ro_code_in_range_fx", "2.4.2", "RD-101: RO-544.1 a RO-547.1",
       "RD-101: RO-544.1 a RO-546.1"),
    _f("r3_n06b_weekly_period_start", "2.4.2", "01/08/2026 a 28/08/2026",
       "02/08/2026 a 28/08/2026"),
    _f("r3_n07_cond_pendente", "2.4.2", "Não apresenta condicionantes em atraso, contudo",
       "Não apresenta condicionantes pendentes, contudo"),
    {"name": "r3_n07b_cond_algumas_apenas_uma", "op": "f_swap_substr", "section": "2.4.2",
     "a": "contudo, encontram-se algumas condicionantes próximas ao vencimento a serem "
          "apresentadas",
     "b": "e apenas uma condicionante próxima ao vencimento a ser apresentada",
     "expect": "text", "passed_round3": True},
    _f("r3_n07c_cond_algumas_todas", "2.4.2", "encontram-se algumas condicionantes",
       "encontram-se todas as condicionantes", passed_round3=True),
    {"name": "r3_n08_del_list_item_short", "op": "f_del_seg", "section": "2.1.2",
     "needle": "Relatório Mensal de Obras;", "expect": "text", "passed_round3": True},
    {"name": "r3_n08b_del_group_item", "op": "f_del_seg", "section": "2.2.2",
     "needle": "Viário Secundário;", "expect": "text", "passed_round3": True},
    {"name": "r3_n08c_del_casa_civil_item", "op": "f_del_seg", "section": "2.2.2",
     "needle": "Publicação pela Casa Civil: Aguardando aceite da GDP;", "expect": "text"},
    _f("r3_n09c_contract_fx", "1", "Contrato N° 00/0000-PARC", "Contrato N° 00/0001-PARC"),
    {"name": "r3_n12c_del_26_quote", "op": "f_del_seg", "section": "2.6.1",
     "needle": "Este produto compreende", "expect": "text"},
    {"name": "r3_n12d_del_262", "op": "f_del_seg", "section": "2.6.2",
     "needle": "No período de referência", "expect": "text"},
    _f("r3_n19_casa_civil_publicado", "2.2.2",
       "Publicação pela Casa Civil: Aguardando aceite da GDP;",
       "Publicação pela Casa Civil: Publicado após aceite da GDP;", passed_round3=True),
    _f("r3_n20_gfd_favoravel", "2.2.2",
       "Manifestação GFD: Ausência de manifestação até o presente momento",
       "Manifestação GFD: Favorável, com manifestação até o presente momento",
       passed_round3=True),
    _f("r3_n21_todas_nem_todas", "2.2.2", "Aprovação: Todas as disciplinas encontram-se aprovadas",
       "Aprovação: Nem todas as disciplinas encontram-se aprovadas", passed_round3=True),
    _f("r3_n22_gdp_complementacao", "2.2.2",
       "Análise GDP: Solicitado complementação, encontra-se em avaliação pela GDP",
       "Análise GDP: Dispensada complementação, encontra-se concluída pela GDP",
       passed_round3=True),
    _f("r3_n23_semanais_quinzenais", "2.4.2", "Os relatórios semanais contemplam",
       "Os relatórios quinzenais contemplam", passed_round3=True),
    _f("r3_n24_rca_devolvido", "2.4.2", "Encaminhado e analisado no período",
       "Encaminhado e devolvido no período", passed_round3=True),
    {"name": "r3_n25_meeting_swap_roads", "op": "f_swap_substr", "section": "2.1.2",
     "a": "reunião com a DELTA", "b": "reunião com a CSG", "expect": "text"},
    {"name": "r3_n26_gamb_process_swap", "op": "f_swap_substr", "section": "2.4.2",
     "a": "Processo 000000000000002", "b": "Processo 000000000000003", "expect": "text"},
    _f("r3_n27_dup_theme", "2.1.2", "abrangendo temas como complementação da DUP",
       "abrangendo temas como complementação do Projeto de Drenagem", passed_round3=True),
    {"name": "r3_n28_aceitacao_aprovacao_swap", "op": "f_swap_substr", "section": "2.2.2",
     "a": "Aceitação (1º Nível), correspondente", "b": "Aprovação (2º Nível), correspondente",
     "expect": "text"},
    # QA3-E n29 falhou por KeyError ('kind' não é campo; as células são posicionais): a
    # mutação pretendida — Manifestação da linha trocada — na 2ª célula
    {"name": "r3_n29_pc_kind_field", "op": "pc_cell", "block": "2.2", "code": "NT-726.1",
     "cell": 1, "new": "Parecer", "expect": "text"},
    {"name": "r3_n30_swap_road_blocks_conds", "op": "f_swap_segs", "section": "2.4.2",
     "a": "RD-101: Não apresenta condicionantes", "b": "RD-102A: Não apresenta condicionantes",
     "expect": "text"},
    _f("r3_n31_crosswire_casa_civil_gets_gdp", "2.2.2",
       "Publicação pela Casa Civil: Aguardando aceite da GDP;",
       "Publicação pela Casa Civil: Solicitado complementação, encontra-se em avaliação pela "
       "GDP;", passed_round3=True),
    {"name": "r3_n32_group_header_swap", "op": "f_swap_substr", "section": "2.2.2",
     "a": "Disciplinas do Viário Principal:", "b": "Disciplinas do Viário Secundário:",
     "expect": "text"},
    _f("r3_n33_started_vs_gdp_interf", "2.2.2",
       "Iniciado processo de realocação de interferências: Aguardando manifestação da "
       "concessionária",
       "Iniciado processo de realocação de interferências: Realocação concluída pela "
       "concessionária", passed_round3=True),
]

CATALOG = ROUND_1_AND_2 + ROUND_3 + PAGE_SWEEPS
