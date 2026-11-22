"""QA do golden test: extração factual e comparador, independentes do builder.

Regra (WAVE1_FINDINGS §H): o comparador e a lista de desvios permitidos são CONGELADOS antes
de qualquer comparação, e a extração de fatos lê só o PDF — nunca importa
`prog_g2_report.builder` nem o render. Assim o mesmo código mede o PDF histórico e o gerado.
"""
