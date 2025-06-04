import pytest
import main

@pytest.fixture
def mock_success(monkeypatch):
    def fake_consultar(num, cpf=None, senha=None):
        return {"numero": num}, None
    def fake_parse(resp):
        return {
            "sucesso": True,
            "processo": {
                "dadosBasicos": {"numero": resp["numero"]},
                "documentos": [],
                "movimentos": [
                    {"descricao": "Senten\xe7a proferida", "dataHora": "2024-01-01"},
                    {"descricao": "Distribu\xeddo", "dataHora": "2023-12-01"}
                ],
                "resumo": {"situacao": "EM_ANDAMENTO"}
            }
        }
    monkeypatch.setattr(main, "consultar_processo_mni", fake_consultar)
    monkeypatch.setattr(main, "parse_processo_response", fake_parse)

@pytest.fixture
def mock_error(monkeypatch):
    monkeypatch.setattr(main, "consultar_processo_mni", lambda num, cpf=None, senha=None: (None, "fail"))


def test_consultar_processo_success(client, mock_success):
    resp = client.get("/api/v1/processo/123")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sucesso"] is True
    assert data["processo"]["dadosBasicos"]["numero"] == "123"


def test_consultar_processo_error(client, mock_error):
    resp = client.get("/api/v1/processo/123")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["erro"] == "MNI_ERROR"


def test_resumo_endpoint(client, mock_success):
    resp = client.get("/api/v1/processo/123/resumo")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sucesso"] is True
    assert data["numeroProcesso"] == "123"
    assert data["totalDocumentos"] == 0


def test_movimentos_filter_and_limit(client, mock_success):
    resp = client.get("/api/v1/processo/123/movimentos?limite=1&tipo=Senten\xe7a")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["movimentos"]) == 1
    assert data["total"] == 2


def test_not_implemented_endpoints(client):
    r1 = client.get("/api/v1/processo/123/copia-integral")
    assert r1.status_code == 501
    r2 = client.get("/api/v1/processo/123/documento/1")
    assert r2.status_code == 501
