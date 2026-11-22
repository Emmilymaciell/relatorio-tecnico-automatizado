"""Acesso ao SharePoint corporativo via Microsoft Graph — SOMENTE LEITURA.

    auth.py       token de aplicativo por client secret (msal); nunca expoe o token
    graph_ro.py   cliente com allowlist explicita de operacoes de leitura
    discovery.py  resolucao de site/drive/pastas e inventario por metadados
    models.py     modelos pydantic dos objetos descobertos (drive_id + item_id)
"""
