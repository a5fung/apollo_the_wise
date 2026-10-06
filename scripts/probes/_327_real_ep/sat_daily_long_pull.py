"""#327 G8 (H9 supply-ladder encoder) - READ-ONLY capture of prod mi_daily_closes 2024-01-01 .. today for the
alerts.tsv tickers. Runs INSIDE apollo-market; writes /tmp/sat_daily_long.tsv (same columns as daily.tsv)."""
import asyncio, sys
sys.path.insert(0, "/app")
from agents.market_intelligence.db import get_pool

TICKERS = ['ABCL', 'ABSI', 'ABVX', 'ACAD', 'ACHR', 'ACMR', 'AEHR', 'AEIS', 'AEVA', 'AGX', 'AGYS', 'AIP', 'AKTS', 'ALAB', 'ALOY', 'AMBQ', 'AMLX', 'AMRC', 'ANF', 'APPS', 'ARGX', 'ARM', 'ARWR', 'ARX', 'ASAN', 'ASPI', 'ASTI', 'ATRO', 'AUGO', 'AVAV', 'AVEX', 'BBWI', 'BE', 'BHVN', 'BLSH', 'BLZE', 'BRUN', 'BTDR', 'BTGO', 'BULL', 'BW', 'BZH', 'CAI', 'CAMT', 'CAT', 'CBRL', 'CBRS', 'CGEM', 'CHA', 'CHRN', 'CHTR', 'CLF', 'CLSK', 'COHU', 'CORT', 'CORZ', 'CPA', 'CRCL', 'CRMD', 'CRSR', 'CRWD', 'CRWV', 'CSCO', 'DCTH', 'DELL', 'DFTX', 'DG', 'DOCN', 'DOCS', 'DRTS', 'DY', 'DYN', 'ECG', 'EFOR', 'ELVN', 'EME', 'EOSE', 'ERO', 'EROC', 'ETON', 'EVTC', 'FCEL', 'FET', 'FIG', 'FIGS', 'FLNC', 'FPS', 'FRMI', 'FROG', 'FTK', 'FTNT', 'FUTU', 'GEMI', 'GH', 'GLBE', 'GLOB', 'GO', 'GRND', 'GRRR', 'HAS', 'HGTY', 'HLIT', 'HOOD', 'HPE', 'HQ', 'HRB', 'HTFL', 'HUT', 'HYMC', 'IBRX', 'IDCC', 'IDR', 'IMVT', 'INFQ', 'INOD', 'INSM', 'INSP', 'IONQ', 'IREN', 'JBIO', 'JBL', 'KC', 'KLAR', 'KMT', 'KODK', 'KSS', 'KTOS', 'KURA', 'KYMR', 'LAC', 'LFST', 'LIFE', 'LIND', 'LPTH', 'LRCX', 'LZB', 'MANE', 'MLTX', 'MMYT', 'MNDY', 'MPWR', 'MRAM', 'MRLN', 'MRNA', 'MRVL', 'MRX', 'MTW', 'MU', 'NAVN', 'NBIS', 'NESR', 'NET', 'NMAX', 'NNE', 'NOW', 'NRIX', 'NVCR', 'NVTS', 'NWL', 'OKLO', 'OKTA', 'OMER', 'ONTO', 'OUST', 'PACS', 'PD', 'PENG', 'PGY', 'PHR', 'PHVS', 'PLTR', 'PONY', 'POWI', 'PPTA', 'PRAA', 'PRG', 'PRGO', 'PSIX', 'PUBM', 'PWR', 'QBTS', 'QCOM', 'QDEL', 'QFIN', 'QNST', 'QUBT', 'QURE', 'RARE', 'RCAT', 'RDDT', 'RDW', 'RIOT', 'RLAY', 'ROCK', 'ROIV', 'RPD', 'RUM', 'RXT', 'SAIC', 'SCSC', 'SE', 'SEDG', 'SEI', 'SG', 'SHAZ', 'SIBN', 'SIMO', 'SITM', 'SKM', 'SLN', 'SLS', 'SMCI', 'SNOW', 'SNX', 'SOLS', 'SOUN', 'STAA', 'STC', 'STDN', 'STUB', 'SWBI', 'SYRE', 'TASK', 'TATT', 'TE', 'TEAM', 'TEM', 'TER', 'TEVA', 'TH', 'THC', 'TNDM', 'TRUP', 'TSAT', 'TSEM', 'TTAN', 'TWLO', 'TWST', 'U', 'UUUU', 'VEEV', 'VERA', 'VG', 'VIK', 'VOYG', 'VPG', 'VSNT', 'VSTS', 'WDFC', 'WEN', 'WKC', 'WLDN', 'WULF', 'WYFI', 'XE', 'ZBRA']

async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(
                "SELECT ticker, trade_date::text AS d, open_price::text AS o, high_price::text AS h, "
                "low_price::text AS l, close::text AS c, volume::text AS v FROM mi_daily_closes "
                "WHERE ticker = ANY($1::text[]) AND trade_date >= DATE '2024-01-01' ORDER BY ticker, trade_date",
                TICKERS)
    with open("/tmp/sat_daily_long.tsv", "w") as f:
        f.write("ticker|trade_date|open_price|high_price|low_price|close|volume\n")
        for r in rows:
            f.write("|".join("" if x is None else x for x in (r["ticker"], r["d"], r["o"], r["h"], r["l"], r["c"], r["v"])) + "\n")
    print("ROWS", len(rows))

asyncio.run(main())
