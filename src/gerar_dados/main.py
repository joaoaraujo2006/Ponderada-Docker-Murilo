"""
Gerar Dados: busca no Yahoo Finance o historico da moeda informada, salva um
CSV por moeda no volume compartilhado, de onde o Modelo le os dados.
Roda em loop, repetindo a cada INTERVALO_DIAS para cada moeda de MOEDAS.
"""
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import yfinance as yf

MOEDAS = [m.strip().upper() for m in os.getenv("MOEDAS", "USD").split(",") if m.strip()]
MOEDA_BASE = os.getenv("MOEDA_BASE", "BRL")  # moeda em que a cotacao e expressa
PERIODO = os.getenv("PERIODO", "7d")
INTERVALO_DIAS = float(os.getenv("INTERVALO_DIAS", "7"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))


def ticker_da_moeda(moeda):
    # Formato do Yahoo Finance para pares de moedas: USDBRL=X, EURBRL=X, ...
    return f"{moeda.upper()}{MOEDA_BASE}=X"


def caminho_csv(moeda):
    return DATA_DIR / f"historico_{moeda.upper()}.csv"


def buscar_cotacoes(moeda):
    ticker = ticker_da_moeda(moeda)
    df = yf.Ticker(ticker).history(period=PERIODO, interval="1d")
    if df.empty:
        raise ValueError(f"Yahoo Finance nao retornou dados para a moeda {moeda} ({ticker})")

    df = df[["Open", "High", "Low", "Close"]].reset_index()
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df.columns = ["data", "abertura", "maxima", "minima", "fechamento"]
    df.insert(0, "moeda", moeda.upper())
    return df


def salvar_csv(df, moeda):
    destino = caminho_csv(moeda)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Escreve em arquivo temporario e renomeia, para o Modelo nunca ler um CSV pela metade
    tmp = destino.with_suffix(".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, destino)
    return destino


def executar(moeda):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Buscando {moeda} ({PERIODO})")
    df = buscar_cotacoes(moeda)
    destino = salvar_csv(df, moeda)
    print(f"{len(df)} linhas salvas em {destino}")


if __name__ == "__main__":
    # Moedas podem vir pela linha de comando (python main.py USD EUR) ou pela variavel MOEDAS
    moedas = [m.upper() for m in sys.argv[1:]] or MOEDAS
    while True:
        for moeda in moedas:
            try:
                executar(moeda)
            except Exception as e:
                print(f"Erro ao gerar dados de {moeda}: {e}")
        time.sleep(INTERVALO_DIAS * 24 * 60 * 60)
