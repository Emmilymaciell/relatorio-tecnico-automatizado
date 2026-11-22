"""prog_g2_report — engenharia reversa e geracao do zero do Relatorio Mensal G2 (Programa).

Pacotes:
    security    guarda de caminhos e excecoes de bloqueio de escrita
    sharepoint  autenticacao por client secret e cliente Graph SOMENTE LEITURA
    catalog     esquemas dos catalogos JSONL (componentes, linhagem, anomalias, paginas)
"""

from pathlib import Path

__version__ = "0.0.1"

REPO_ROOT = Path(__file__).resolve().parents[2]
