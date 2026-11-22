from prog_g2_report.catalog import Anomaly, AnomalyClass, Confidence, Evidence
from prog_g2_report.sharepoint.models import ItemRef

SAMPLE_ITEM = {
    "id": "01ABC",
    "name": "RM 14 - Relatório Mensal.pdf",
    "size": 1234,
    "eTag": '"{X},1"',
    "cTag": '"c:{X},1"',
    "webUrl": "https://contoso.sharepoint.com/sites/exemplo",
    "createdDateTime": "2026-09-01T10:00:00Z",
    "lastModifiedDateTime": "2026-09-02T10:00:00Z",
    "file": {"mimeType": "application/pdf", "hashes": {"quickXorHash": "AAA="}},
    "parentReference": {
        "driveId": "b!drive",
        "id": "01PARENT",
        "path": "/drives/b!drive/root:/4.%20Produtos/07.%20Janeiro%202026/G2",
    },
}


def test_itemref_from_graph_decodes_path_and_identity():
    item = ItemRef.from_graph(SAMPLE_ITEM)
    assert (item.drive_id, item.item_id) == ("b!drive", "01ABC")
    assert item.path == "4. Produtos/07. Janeiro 2026/G2/RM 14 - Relatório Mensal.pdf"
    assert not item.is_folder
    assert item.extension == "pdf"
    assert item.quick_xor_hash == "AAA="
    assert item.parent_item_id == "01PARENT"


def test_itemref_folder():
    raw = {**SAMPLE_ITEM, "file": None, "folder": {"childCount": 7}}
    raw.pop("file")
    item = ItemRef.from_graph(raw, "b!drive")
    assert item.is_folder and item.child_count == 7


def test_anomaly_never_learns_as_rule_by_default():
    anomaly = Anomaly(
        report_id="Relatório G2 nº 03",
        page=2,
        component="APRESENTACAO_NUMERO_RELATORIO",
        observed_value="Nº 02",
        expected_value="Nº 03",
        evidence=[Evidence(report_id="Relatório G2 nº 03", page=2, excerpt="Relatório Mensal Nº 02")],
        classification=AnomalyClass.COPY_FORWARD_ERROR,
        confidence=Confidence.HIGH,
    )
    assert anomaly.should_learn_as_rule is False
    line = anomaly.model_dump_json(exclude_none=True)
    assert '"should_learn_as_rule":false' in line
