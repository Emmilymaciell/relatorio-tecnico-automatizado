"""Lista Mestra: cabeçalho por conteúdo, seleção por N° Relatório e ordem física (DEC-006)."""

from datetime import datetime

import pytest

from prog_g2_report.sources import master_list as ml

HEADER = (None, "Produto", "Empresa ", "Documento", "Manifestação", "Descrição", "Empreendimento",
          "Data Entrega", "Status Entrega", "Versão", "N° Relatório", "Período",
          "Contém Anexos? (A partir do Relatório 11)")


def _row(product, doc, number, day=1):
    return (None, product, "Dynatest", doc, "Parecer", "desc", "RD-010",
            datetime(2026, 8, day), "Entregue", 1, number, None, None)


def _sheet(*body):
    return [(None, "Programa | Controle de Produtos"), (), HEADER, *body]


def test_header_found_by_content_and_physical_rows_preserved():
    rows = ml.parse_rows(_sheet(_row("2.2 PROJETOS", "PA-002", 14), _row("2.1 COORD", "AT-001", 14)))
    assert [r.physical_row for r in rows] == [4, 5]
    assert rows[0].product_code == "2.2"
    assert rows[0].delivery_date.isoformat() == "2026-08-01"


def test_header_tolerates_mojibake():
    garbled = tuple(h.replace("ç", "�").replace("ã", "�").replace("ó", "�").replace("°", "�")
                    if isinstance(h, str) else h for h in HEADER)
    rows = ml.parse_rows([garbled, _row("2.1 COORD", "AT-001", "14")])
    assert rows[0].report_number == 14
    assert rows[0].manifestation == "Parecer"


def test_selection_is_by_report_number_not_by_date():
    # documento entregue em agosto mas registrado no relatório 15 não entra no 14
    rows = ml.parse_rows(_sheet(_row("2.4 MEIO", "RS-1", 14, day=30), _row("2.4 MEIO", "RS-2", 15, day=2),
                                _row("2.4 MEIO", "RS-3", 14, day=5)))
    chosen = ml.select(rows, 14)
    assert [r.document for r in chosen] == ["RS-1", "RS-3"]


def test_order_is_physical_never_by_date():
    rows = ml.parse_rows(_sheet(_row("2.2 P", "B", 14, day=20), _row("2.2 P", "A", 14, day=1)))
    assert [r.document for r in ml.select(rows, 14, "2.2")] == ["B", "A"]


def test_product_filter_uses_code_prefix():
    rows = ml.parse_rows(_sheet(_row("2.1 COORD", "X", 14), _row("2.2 PROJ", "Y", 14)))
    assert [r.document for r in ml.select(rows, 14, "2.1")] == ["X"]


def test_blank_document_rows_are_ignored():
    rows = ml.parse_rows(_sheet(_row("2.1 COORD", "X", 14), (None, None, None, None)))
    assert len(rows) == 1


def test_missing_header_fails_loudly():
    with pytest.raises(ValueError):
        ml.parse_rows([(None, "foo"), (None, "bar")])


def test_old_header_parecer_maps_to_manifestation():
    # na v134.0 (julho) a coluna se chama "Parecer"; sem isso, manifestation viraria None
    old = tuple("Parecer" if h == "Manifestação" else h for h in HEADER)
    rows = ml.parse_rows([old, _row("2.1 COORD", "AT-001", 13)])
    assert rows[0].manifestation == "Parecer"


def test_index_keeps_only_delivered_rows_but_body_keeps_all():
    # julho/2026: BM "Em elaboração" aparece no corpo do 2.4 e fica fora do índice de anexos
    pending = (None, "2.4 MEIO", "Dynatest", "BM-007.1", "Boletim", "d", "RD-104",
               None, "Em elaboração", 1, 13, None, None)
    rows = ml.parse_rows(_sheet(_row("2.4 MEIO", "RS-1", 13), pending))
    assert [r.document for r in ml.select(rows, 13)] == ["RS-1", "BM-007.1"]
    assert [r.document for r in ml.select_index(rows, 13)] == ["RS-1"]


# ------------------------------------------------------------------ versão em memória (graph_ro)
def _xlsx_bytes(*body) -> bytes:
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ml.SHEET
    for row in _sheet(*body):
        ws.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class _FakeGraph:
    """Só as duas leituras do graph_ro que o leitor usa; nada de escrita."""

    def __init__(self, data: bytes):
        self.data = data
        self.reads = 0

    def versions(self, drive_id, item_id):
        return [{"id": "162.0", "lastModifiedDateTime": "2026-08-14T17:24:37Z"},
                {"id": "163.0", "lastModifiedDateTime": "2026-08-14T18:00:00Z"}]

    def read_version_bytes(self, drive_id, item_id, version_id):
        self.reads += 1
        return self.data


def test_remote_version_is_read_in_memory_cached_and_never_written(tmp_path, monkeypatch):
    from prog_g2_report.builder.context import SourceRef
    from prog_g2_report.sources import master_list_remote as remote

    remote.clear_cache()
    monkeypatch.chdir(tmp_path)
    fake = _FakeGraph(_xlsx_bytes(_row("2.4 GER", "BM-007.1", 13), _row("2.1 COORD", "AT-1", 12)))
    version = remote.read_version("d", "i", "v162", client=fake)
    assert version.version_id == "162.0" and version.last_modified == "2026-08-14T17:24:37Z"
    assert len(version.sha1) == 40
    assert [r.document for r in ml.select(version.rows, 13)] == ["BM-007.1"]
    remote.read_version("d", "i", "162", client=fake)
    assert fake.reads == 1                                   # uma leitura por processo
    ref = SourceRef("master_list", "Lista Mestra", None, drive_id="d", item_id="i",
                    version_id="162.0")
    assert [r.document for r in ml.load_source(ref)] == ["BM-007.1", "AT-1"]
    assert list(tmp_path.iterdir()) == []                    # nada gravado em disco
    with pytest.raises(LookupError, match="GAP-015"):
        remote.read_version("d", "i", "99", client=fake)
    with pytest.raises(ValueError, match="local_path"):
        ml.load_source(SourceRef("master_list", "Lista Mestra"))
    remote.clear_cache()


def test_remote_identity_comes_from_the_work_sources_catalog(tmp_path):
    from prog_g2_report.sources import master_list_remote as remote

    catalog = tmp_path / "work_sources.jsonl"
    catalog.write_text('{"name": "outra.xlsx", "drive_id": "x", "item_id": "y"}\n'
                       '{"name": "00_ Lista mestre.xlsx", "drive_id": "d1", "item_id": "i1"}\n',
                       encoding="utf-8")
    assert remote.catalog_identity("00_ Lista mestre.xlsx", catalog) == ("d1", "i1")
    with pytest.raises(LookupError):
        remote.catalog_identity("nenhuma.xlsx", catalog)
