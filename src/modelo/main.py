"""
Modelo: le o CSV de cada moeda gerado pelo Gerar Dados, treina um modelo de
regressao linear (scikit-learn) sobre o preco de fechamento e mantem o modelo
treinado em memoria para fazer as previsoes.

Uso (pelo servidor.py, que expoe a logica por HTTP):
    from main import prever, metricas
    prever("USD", dias=3)
    metricas("USD")

Se o CSV da moeda for atualizado em disco, o modelo e retreinado
automaticamente na proxima previsao (e as metricas sao recalculadas).
"""
import os
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
MAX_DIAS = int(os.getenv("MAX_DIAS", "7"))
MIN_TREINO = int(os.getenv("MIN_TREINO", "5"))  # pontos minimos antes da 1a previsao na avaliacao

modelos = {}  # moeda -> modelo treinado


def normalizar_moeda(moeda):
    moeda = str(moeda or "").strip().upper()
    if not moeda:
        raise ValueError("Informe a moeda, ex: USD")
    return moeda


def caminho_csv(moeda):
    return DATA_DIR / f"historico_{moeda}.csv"


def treinar(moeda):
    moeda = normalizar_moeda(moeda)
    csv = caminho_csv(moeda)
    if not csv.exists():
        raise FileNotFoundError(f"CSV da moeda {moeda} nao encontrado em {csv}")

    df = pd.read_csv(csv, parse_dates=["data"]).sort_values("data").reset_index(drop=True)
    if len(df) < 2:
        raise ValueError(f"Dados insuficientes para treinar {moeda} ({len(df)} linhas)")

    inicio = df["data"].iloc[0]
    y = df["fechamento"]
    regressor = ajustar(df)

    modelos[moeda] = {
        "regressor": regressor,
        "versao_csv": csv.stat().st_mtime,
        "inicio": inicio,
        "ultima_data": df["data"].iloc[-1],
        "ultimo_valor": float(y.iloc[-1]),
        "amostras": len(df),
        "metricas": avaliar(df, regressor),
    }
    return modelos[moeda]


def ajustar(df):
    # X = dias desde a primeira cotacao do df, y = fechamento
    X = (df["data"] - df["data"].iloc[0]).dt.days.to_frame("dia")
    return LinearRegression().fit(X, df["fechamento"])


def calcular(real, previsto):
    real, previsto = np.asarray(real), np.asarray(previsto)
    return {
        "mae": round(float(mean_absolute_error(real, previsto)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(real, previsto))), 4),
        "mape_pct": round(float(mean_absolute_percentage_error(real, previsto) * 100), 2),
        "r2": round(float(r2_score(real, previsto)), 3) if len(real) > 1 else None,
    }


def avaliar(df, regressor):
    """
    - treino: quao bem a reta se ajusta aos proprios dados (in-sample)
    - teste: walk-forward, treina so com o passado e preve o proximo pregao,
      comparado ao baseline "amanha = hoje" (repetir o ultimo fechamento)
    """
    y = df["fechamento"].to_numpy()
    X = (df["data"] - df["data"].iloc[0]).dt.days.to_frame("dia")
    resultado = {"treino": calcular(y, regressor.predict(X))}

    if len(df) <= MIN_TREINO:
        resultado["teste"] = None
        resultado["aviso"] = f"Sao necessarias mais de {MIN_TREINO} cotacoes para o teste walk-forward"
        return resultado

    reais, previstos, anteriores = [], [], []
    for t in range(MIN_TREINO, len(df)):
        passado = df.iloc[:t]
        dia = (df["data"].iloc[t] - passado["data"].iloc[0]).days
        previstos.append(float(ajustar(passado).predict(pd.DataFrame({"dia": [dia]}))[0]))
        reais.append(y[t])
        anteriores.append(y[t - 1])

    reais, previstos, anteriores = map(np.asarray, (reais, previstos, anteriores))
    modelo = calcular(reais, previstos)
    modelo["acerto_direcao_pct"] = round(float(np.mean(np.sign(previstos - anteriores) == np.sign(reais - anteriores)) * 100), 1)
    baseline = calcular(reais, anteriores)

    resultado["teste"] = {
        "previsoes_avaliadas": len(reais),
        "horizonte_dias": 1,
        "modelo": modelo,
        "baseline_ultimo_valor": baseline,
        "modelo_supera_baseline": modelo["mae"] < baseline["mae"],
    }
    return resultado


def obter_modelo(moeda):
    moeda = normalizar_moeda(moeda)
    csv = caminho_csv(moeda)
    m = modelos.get(moeda)
    # Retreina se ainda nao existe ou se o Gerar Dados salvou um CSV mais novo
    if m is None or (csv.exists() and csv.stat().st_mtime != m["versao_csv"]):
        m = treinar(moeda)
    return m


def prever(moeda, dias=1):
    moeda = normalizar_moeda(moeda)
    try:
        dias = int(dias)
    except (TypeError, ValueError):
        raise ValueError("dias deve ser um numero inteiro")
    if not 1 <= dias <= MAX_DIAS:
        raise ValueError(f"dias deve estar entre 1 e {MAX_DIAS}")

    m = obter_modelo(moeda)
    datas = [m["ultima_data"] + timedelta(days=i) for i in range(1, dias + 1)]
    X_futuro = pd.DataFrame({"dia": [(d - m["inicio"]).days for d in datas]})
    valores = m["regressor"].predict(X_futuro)

    previsoes = [
        {"data": d.strftime("%Y-%m-%d"), "valor": round(float(v), 4)}
        for d, v in zip(datas, valores)
    ]

    return {
        "moeda": moeda,
        "ultimo_valor": m["ultimo_valor"],
        "ultima_data": m["ultima_data"].strftime("%Y-%m-%d"),
        "previsoes": previsoes,
    }


def metricas(moeda):
    m = obter_modelo(moeda)
    return {
        "moeda": normalizar_moeda(moeda),
        "amostras": m["amostras"],
        "periodo": {
            "inicio": m["inicio"].strftime("%Y-%m-%d"),
            "fim": m["ultima_data"].strftime("%Y-%m-%d"),
        },
        "coeficiente_por_dia": round(float(m["regressor"].coef_[0]), 6),
        "intercepto": round(float(m["regressor"].intercept_), 4),
        **m["metricas"],
    }
