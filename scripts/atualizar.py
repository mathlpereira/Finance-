"""
Robô de atualização do Globo Financeiro.
Roda no GitHub Actions, busca os dados nas fontes públicas e grava data/mercado.json.
Cada fonte é independente: se uma falhar, as outras continuam e o relatório registra o erro.
"""
import json, math, os, sys, time, datetime as dt
from pathlib import Path

import requests

SAIDA = Path(__file__).resolve().parent.parent / "data" / "mercado.json"
AGORA = dt.datetime.now(dt.timezone.utc)
relatorio = []          # (fonte, item, ok, detalhe)

def log(fonte, item, ok, detalhe=""):
    relatorio.append({"fonte": fonte, "item": item, "ok": ok, "detalhe": str(detalhe)[:200]})
    print(("OK   " if ok else "FALHA"), fonte, item, detalhe)

# ---------------- Yahoo Finance (bolsas, ações, moedas, commodities) ----------------
BOLSAS = [
    # id, nome do índice, ticker, cidade, lat, lon, fuso, abertura, fechamento, moeda
    ("b3", "Ibovespa", "^BVSP", "São Paulo", -23.55, -46.63, "America/Sao_Paulo", "10:00", "17:00", "BRL"),
    ("nyse", "S&P 500", "^GSPC", "Nova York", 40.71, -74.01, "America/New_York", "09:30", "16:00", "USD"),
    ("nasdaq", "Nasdaq", "^IXIC", "Nova York", 40.76, -73.98, "America/New_York", "09:30", "16:00", "USD"),
    ("tsx", "S&P/TSX", "^GSPTSE", "Toronto", 43.65, -79.38, "America/Toronto", "09:30", "16:00", "CAD"),
    ("merval", "Merval", "^MERV", "Buenos Aires", -34.60, -58.38, "America/Argentina/Buenos_Aires", "11:00", "17:00", "ARS"),
    ("lse", "FTSE 100", "^FTSE", "Londres", 51.51, -0.09, "Europe/London", "08:00", "16:30", "GBP"),
    ("xetra", "DAX", "^GDAXI", "Frankfurt", 50.11, 8.68, "Europe/Berlin", "09:00", "17:30", "EUR"),
    ("euronext", "CAC 40", "^FCHI", "Paris", 48.87, 2.34, "Europe/Paris", "09:00", "17:30", "EUR"),
    ("tse", "Nikkei 225", "^N225", "Tóquio", 35.68, 139.77, "Asia/Tokyo", "09:00", "15:30", "JPY"),
    ("sse", "Shanghai Composite", "000001.SS", "Xangai", 31.23, 121.47, "Asia/Shanghai", "09:30", "15:00", "CNY"),
    ("hkex", "Hang Seng", "^HSI", "Hong Kong", 22.28, 114.16, "Asia/Hong_Kong", "09:30", "16:00", "HKD"),
    ("bse", "Sensex", "^BSESN", "Mumbai", 18.93, 72.83, "Asia/Kolkata", "09:15", "15:30", "INR"),
    ("asx", "S&P/ASX 200", "^AXJO", "Sydney", -33.87, 151.21, "Australia/Sydney", "10:00", "16:00", "AUD"),
]
ACOES = [
    ("PETR4.SA", "Petrobras", "Petróleo", "BZ=F"), ("VALE3.SA", "Vale", "Mineração", None),
    ("ITUB4.SA", "Itaú Unibanco", "Bancos", None), ("BBDC4.SA", "Bradesco", "Bancos", None),
    ("BBAS3.SA", "Banco do Brasil", "Bancos", None), ("ABEV3.SA", "Ambev", "Bebidas", None),
    ("WEGE3.SA", "WEG", "Indústria", None), ("B3SA3.SA", "B3", "Serviços financeiros", None),
    ("SUZB3.SA", "Suzano", "Papel e celulose", None), ("PRIO3.SA", "PRIO", "Petróleo", "BZ=F"),
    ("RENT3.SA", "Localiza", "Locação de veículos", None), ("MGLU3.SA", "Magazine Luiza", "Varejo", None),
]
MOEDAS = [("USDBRL=X", "Dólar", "USD"), ("EURBRL=X", "Euro", "EUR"), ("GBPBRL=X", "Libra", "GBP"), ("CNYBRL=X", "Yuan", "CNY")]
COMMODITIES = [("BZ=F", "Petróleo Brent", "US$/barril"), ("GC=F", "Ouro", "US$/onça"), ("ZS=F", "Soja (Chicago)", "US¢/bushel"),
               ("KC=F", "Café arábica", "US¢/libra-peso"), ("BTC-USD", "Bitcoin", "US$")]

def serie_yf(yf, ticker, periodo="1y"):
    h = yf.Ticker(ticker).history(period=periodo, interval="1d", auto_adjust=False)
    h = h.dropna(subset=["Close"])
    if h.empty:
        raise ValueError("sem dados")
    datas = [d.strftime("%Y-%m-%d") for d in h.index]
    fech = [round(float(v), 4) for v in h["Close"]]
    return datas, fech

def resumo(datas, fech):
    ult, ant = fech[-1], (fech[-2] if len(fech) > 1 else fech[-1])
    def var_desde(dias):
        if len(fech) <= dias: return None
        base = fech[-1 - dias]
        return round((ult / base - 1) * 100, 2) if base else None
    ano = datas[-1][:4]
    idx_ano = next((i for i, d in enumerate(datas) if d[:4] == ano), None)
    no_ano = None
    if idx_ano and idx_ano > 0 and fech[idx_ano - 1]:
        no_ano = round((ult / fech[idx_ano - 1] - 1) * 100, 2)
    return {"ultimo": ult, "anterior": ant, "var_dia": round((ult / ant - 1) * 100, 2) if ant else None,
            "var_mes": var_desde(21), "var_ano": no_ano, "var_12m": var_desde(len(fech) - 1) if len(fech) > 200 else None,
            "data": datas[-1], "historico": {"datas": datas, "fech": fech}}

def buscar_yahoo():
    try:
        import yfinance as yf
    except Exception as e:
        log("Yahoo Finance", "biblioteca yfinance", False, e)
        return {}, [], [], []
    bolsas, acoes, moedas, comm = {}, [], [], []
    for (bid, nome, tk, cidade, lat, lon, tz, ab, fe, moeda) in BOLSAS:
        try:
            d, f = serie_yf(yf, tk)
            bolsas[bid] = {"id": bid, "indice": nome, "ticker": tk, "cidade": cidade, "lat": lat, "lon": lon, "fuso": tz,
                           "abre": ab, "fecha": fe, "moeda": moeda, **resumo(d, f)}
            log("Yahoo Finance", nome, True, f[-1])
        except Exception as e:
            log("Yahoo Finance", nome, False, e)
        time.sleep(0.4)
    for (tk, nome, setor, liga) in ACOES:
        try:
            d, f = serie_yf(yf, tk)
            acoes.append({"ticker": tk.replace(".SA", ""), "nome": nome, "setor": setor, "liga": liga, **resumo(d, f)})
            log("Yahoo Finance", tk, True, f[-1])
        except Exception as e:
            log("Yahoo Finance", tk, False, e)
        time.sleep(0.4)
    for (tk, nome, cod) in MOEDAS:
        try:
            d, f = serie_yf(yf, tk)
            moedas.append({"ticker": tk, "nome": nome, "codigo": cod, **resumo(d, f)})
            log("Yahoo Finance", tk, True, f[-1])
        except Exception as e:
            log("Yahoo Finance", tk, False, e)
    for (tk, nome, un) in COMMODITIES:
        try:
            d, f = serie_yf(yf, tk)
            comm.append({"ticker": tk, "nome": nome, "unidade": un, **resumo(d, f)})
            log("Yahoo Finance", tk, True, f[-1])
        except Exception as e:
            log("Yahoo Finance", tk, False, e)
    return bolsas, acoes, moedas, comm

def historico_mensal_yf():
    """Fechamentos mensais longos, usados no simulador (Ibovespa, dólar, S&P 500)."""
    out = {}
    try:
        import yfinance as yf
    except Exception:
        return out
    for tk, chave in [("^BVSP", "ibovespa"), ("USDBRL=X", "dolar"), ("^GSPC", "sp500")]:
        try:
            h = yf.Ticker(tk).history(period="max", interval="1mo", auto_adjust=False).dropna(subset=["Close"])
            h = h[h.index >= "2010-01-01"]
            out[chave] = {d.strftime("%Y-%m"): round(float(v), 4) for d, v in zip(h.index, h["Close"])}
            log("Yahoo Finance", "mensal " + chave, True, len(out[chave]))
        except Exception as e:
            log("Yahoo Finance", "mensal " + chave, False, e)
    return out

# ---------------- Banco Central (SGS) ----------------
SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados?formato=json&dataInicial={ini}&dataFinal={fim}"
def sgs(cod, inicio):
    """Busca uma série do SGS. Séries diárias só aceitam janelas de até 10 anos,
    então o período é dividido em blocos de até 9 anos."""
    ini = dt.datetime.strptime(inicio, "%d/%m/%Y")
    fim_total = AGORA.replace(tzinfo=None)
    dados = []
    while ini <= fim_total:
        fim = min(fim_total, ini + dt.timedelta(days=9 * 365))
        url = SGS.format(cod=cod, ini=ini.strftime("%d/%m/%Y"), fim=fim.strftime("%d/%m/%Y"))
        r = requests.get(url, timeout=40, headers={"Accept": "application/json"})
        if r.status_code == 404:          # bloco sem dados
            pass
        else:
            r.raise_for_status()
            bloco = r.json()
            if isinstance(bloco, list):
                dados.extend(bloco)
        ini = fim + dt.timedelta(days=1)
    if not dados:
        raise ValueError("resposta vazia")
    vistos, saida = set(), []
    for x in dados:
        if x["data"] in vistos:
            continue
        vistos.add(x["data"])
        saida.append((x["data"], float(str(x["valor"]).replace(",", "."))))
    saida.sort(key=lambda t: dt.datetime.strptime(t[0], "%d/%m/%Y"))
    return saida

def buscar_bcb():
    bc = {}
    pedidos = [
        ("selic_meta", 432, "01/01/2024"),       # meta Selic (% a.a.)
        ("cdi_anual", 4389, (AGORA - dt.timedelta(days=45)).strftime("%d/%m/%Y")),       # CDI anualizado base 252 (% a.a.), diário
        ("cdi_mensal", 4391, "01/01/2010"),      # CDI acumulado no mês (% a.m.)
        ("ipca_mensal", 433, "01/01/2010"),      # IPCA (% a.m.)
        ("poupanca_mensal", 25, "01/01/2010"),   # rentabilidade da poupança (% no período)
        ("ptax", 1, "01/01/2025"),               # dólar oficial (PTAX)
    ]
    for chave, cod, ini in pedidos:
        try:
            s = sgs(cod, ini)
            bc[chave] = s
            log("Banco Central", f"{chave} (SGS {cod})", True, s[-1])
        except Exception as e:
            log("Banco Central", f"{chave} (SGS {cod})", False, e)
        time.sleep(0.5)
    out = {}
    if "cdi_anual" in bc:
        out["cdi_anual"] = {"valor": bc["cdi_anual"][-1][1], "data": bc["cdi_anual"][-1][0]}
    if "selic_meta" in bc:
        out["selic"] = {"valor": bc["selic_meta"][-1][1], "data": bc["selic_meta"][-1][0]}
    def mensal(lista):
        m = {}
        for data, v in lista:
            d, mm, a = data.split("/")
            m[f"{a}-{mm}"] = v   # para séries com mais de um ponto no mês, fica o último
        return m
    if "cdi_mensal" in bc:
        m = mensal(bc["cdi_mensal"]); out["cdi_mensal"] = m
        ult = list(m.values())[-12:]
        out["cdi_12m"] = round((math.prod(1 + v / 100 for v in ult) - 1) * 100, 2)
    if "ipca_mensal" in bc:
        m = mensal(bc["ipca_mensal"]); out["ipca_mensal"] = m
        ult = list(m.values())[-12:]
        out["ipca_12m"] = round((math.prod(1 + v / 100 for v in ult) - 1) * 100, 2)
        out["ipca_ultimo"] = {"mes": list(m.keys())[-1], "valor": list(m.values())[-1]}
    if "poupanca_mensal" in bc:
        out["poupanca_mensal"] = mensal(bc["poupanca_mensal"])
    if "ptax" in bc:
        out["ptax"] = {"valor": bc["ptax"][-1][1], "data": bc["ptax"][-1][0]}
    return out

def main():
    dados = {"gerado_em": AGORA.isoformat(timespec="seconds"), "status": "ok"}
    bolsas, acoes, moedas, comm = buscar_yahoo()
    dados.update({"bolsas": bolsas, "acoes": acoes, "moedas": moedas, "commodities": comm})
    dados["mensal"] = historico_mensal_yf()
    dados["bcb"] = buscar_bcb()
    dados["relatorio"] = relatorio
    ok = sum(1 for r in relatorio if r["ok"]); tot = len(relatorio)
    dados["relatorio_resumo"] = f"{ok} de {tot} itens atualizados"
    if ok == 0:
        # nenhuma fonte respondeu: mantém o arquivo anterior para o site não ficar vazio
        print("Nenhuma fonte respondeu; arquivo anterior mantido.")
        sys.exit(1)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(dados["relatorio_resumo"])

if __name__ == "__main__":
    main()
