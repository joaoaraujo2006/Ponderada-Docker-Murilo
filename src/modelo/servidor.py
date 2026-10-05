"""
Servidor interno do Modelo: expoe apenas a previsao de main.py por HTTP para o
Backend, que roda em outro container na mesma network do compose. Nao e
exposto ao Cliente.

Rotas:
  POST /prever  {"moeda", "dias"}  -> previsao do fechamento dos proximos dias
  GET  /metricas/<moeda>           -> metricas de treino e teste do modelo da moeda
"""
import os

from flask import Flask, jsonify, request

import main as modelo

PORTA = int(os.getenv("PORTA", "5001"))

app = Flask(__name__)


def erro(mensagem, status):
    return jsonify(erro=mensagem), status


@app.post("/prever")
def prever():
    corpo = request.get_json(silent=True) or {}
    try:
        return jsonify(modelo.prever(corpo.get("moeda"), corpo.get("dias", 1)))
    except FileNotFoundError:
        return erro(f"Nao ha dados para a moeda {str(corpo.get('moeda')).upper()}", 404)
    except ValueError as e:
        return erro(str(e), 400)


@app.get("/metricas/<moeda>")
def metricas(moeda):
    try:
        return jsonify(modelo.metricas(moeda))
    except FileNotFoundError:
        return erro(f"Nao ha dados para a moeda {moeda.strip().upper()}", 404)
    except ValueError as e:
        return erro(str(e), 400)


@app.errorhandler(404)
def rota_inexistente(_):
    return erro("Rota inexistente", 404)


@app.errorhandler(405)
def metodo_nao_permitido(_):
    return erro("Metodo nao permitido", 405)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORTA)
