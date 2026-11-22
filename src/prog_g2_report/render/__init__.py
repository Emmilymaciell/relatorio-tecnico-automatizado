"""Renderizadores do Relatório G2.

Puros (dados → estrutura textual, sem python-docx): `p22_text`, `p22_dashboard_data`,
`p24_text`. Devolvem parágrafos, segmentos e níveis de lista para o motor de blocos do builder
emitir. CONTEÚDO aqui; REPRESENTAÇÃO e POSICIONAMENTO no builder.

Representação: `docx_emf`, `paginate`, `product_control` (Controle de Produtos, DEC-010) e
`visuals` (painéis PNG reconstruídos do dado, DEC-009).
"""
