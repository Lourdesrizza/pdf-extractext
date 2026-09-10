from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.main import app
from app.infrastructure.database import connection


def test_lifespan_initializes_once_and_closes_client(monkeypatch):
    database = MagicMock()
    database.command = AsyncMock(return_value={"ok": 1})
    database.documents.create_index = AsyncMock()
    database.documents.index_information = AsyncMock(return_value={
        "uq_documents_checksum": {"key": [("checksum", 1)], "unique": True}
    })
    client = MagicMock()
    client.__getitem__.return_value = database
    monkeypatch.setattr(connection, "_client", client)
    with TestClient(app) as http:
        assert http.get("/").status_code == 200
        assert http.get("/").status_code == 200
        database.command.assert_awaited_once_with("ping")
        database.documents.create_index.assert_awaited_once()
        database.documents.index_information.assert_awaited_once()
        client.close.assert_not_called()
    client.close.assert_called_once()
    assert connection._client is None


@pytest.mark.parametrize("stage", ["connection", "index"])
def test_startup_failure_does_not_serve_and_closes_client(monkeypatch, stage):
    database = MagicMock()
    database.command = AsyncMock(return_value={"ok": 1})
    database.documents.create_index = AsyncMock()
    if stage == "connection":
        database.command.side_effect = ServerSelectionTimeoutError("no disponible")
    else:
        database.documents.create_index.side_effect = RuntimeError("indice incorrecto")
    client = MagicMock()
    client.__getitem__.return_value = database
    monkeypatch.setattr(connection, "_client", client)
    with pytest.raises((RuntimeError, ServerSelectionTimeoutError)):
        with TestClient(app):
            pytest.fail("No debe completar el inicio")
    client.close.assert_called_once()
    assert connection._client is None
