"""
Backend: expoe as rotas HTTP para o Cliente. As previsoes e metricas sao repassadas ao
Modelo, que roda em outro container na mesma network do compose e e acessado
por HTTP (MODELO_URL, ex: http://modelo:5001). Moedas e historico sao lidos
direto do volume compartilhado (DATA_DIR), ja que o Modelo so expoe /prever e /metricas.

Rotas:
  GET  /health                       -> status da API
  GET  /moedas                       -> moedas com dados disponiveis
  GET  /historico/<moeda>            -> cotacoes salvas pelo Gerar Dados
  POST /prever  {"moeda", "dias"}    -> previsao do fechamento dos proximos dias
  GET  /prever/<moeda>?dias=3        -> mesma previsao, via GET
  GET  /metricas/<moeda>             -> metricas de treino e teste do modelo da moeda
  GET  /teste                        -> testa volume, conexao com o Modelo e previsao por moeda
"""
import csv
import os
from pathlib import Path

import requests
from flask import Flask, jsonify, request

PORTA = int(os.getenv("PORTA", "5000"))
MODELO_URL = os.getenv("MODELO_URL", "http://modelo:5001").rstrip("/")
TIMEOUT = float(os.getenv("MODELO_TIMEOUT", "10"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))

app = Flask(__name__)


def prever_no_modelo(moeda, dias):
    """Pede a previsao ao Modelo e devolve a resposta dele (corpo e status) ao Cliente."""
    return repassar_ao_modelo("post", "/prever", json={"moeda": moeda, "dias": dias})


def repassar_ao_modelo(metodo, rota, **kwargs):
    """Chama uma rota do Modelo e devolve a resposta dele (corpo e status) ao Cliente."""
    try:
        resp = requests.request(metodo, f"{MODELO_URL}{rota}", timeout=TIMEOUT, **kwargs)
    except requests.RequestException:
        return jsonify(erro="Modelo indisponivel no momento"), 503

    try:
        corpo = resp.json()
    except ValueError:
        return jsonify(erro="Resposta invalida do Modelo"), 502
    return jsonify(corpo), resp.status_code


@app.get("/health")
def health():
    return jsonify(status="ok")


def moedas_disponiveis():
    return sorted(p.stem[len("historico_"):] for p in DATA_DIR.glob("historico_*.csv"))


@app.get("/moedas")
def listar_moedas():
    return jsonify(moedas=moedas_disponiveis())


@app.get("/metricas/<moeda>")
def metricas(moeda):
    return repassar_ao_modelo("get", f"/metricas/{moeda}")


@app.get("/teste")
def teste():
    """Testa cada etapa do fluxo: volume com CSVs, Modelo acessivel e previsao de 1 dia por moeda."""
    moedas = moedas_disponiveis()
    testes = {
        "volume": {"ok": bool(moedas), "detalhe": f"{len(moedas)} moeda(s) em {DATA_DIR}: {moedas}"},
    }

    for moeda in moedas or ["USD"]:
        try:
            resp = requests.post(f"{MODELO_URL}/prever", json={"moeda": moeda, "dias": 1}, timeout=TIMEOUT)
            corpo = resp.json()
        except requests.RequestException as e:
            testes["modelo"] = {"ok": False, "detalhe": f"Modelo inacessivel em {MODELO_URL}: {e.__class__.__name__}"}
            break
        except ValueError:
            testes["modelo"] = {"ok": False, "detalhe": "Resposta invalida do Modelo"}
            break

        testes["modelo"] = {"ok": True, "detalhe": f"Modelo respondeu em {MODELO_URL}"}
        previsoes = corpo.get("previsoes") or []
        testes[f"previsao_{moeda}"] = {
            "ok": resp.status_code == 200 and len(previsoes) == 1,
            "detalhe": previsoes[0] if previsoes else corpo.get("erro"),
        }

    tudo_ok = all(t["ok"] for t in testes.values())
    return jsonify(status="ok" if tudo_ok else "falha", testes=testes), 200 if tudo_ok else 503


@app.get("/historico/<moeda>")
def historico(moeda):
    moeda = moeda.strip().upper()
    caminho = DATA_DIR / f"historico_{moeda}.csv"
    if not caminho.exists():
        return jsonify(erro=f"Nao ha dados para a moeda {moeda}"), 404

    with caminho.open(newline="", encoding="utf-8") as f:
        cotacoes = list(csv.DictReader(f))
    return jsonify(moeda=moeda, cotacoes=cotacoes)


@app.post("/prever")
def prever_post():
    corpo = request.get_json(silent=True) or {}
    return prever_no_modelo(corpo.get("moeda"), corpo.get("dias", 1))


@app.get("/prever/<moeda>")
def prever_get(moeda):
    return prever_no_modelo(moeda, request.args.get("dias", 1))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORTA)
