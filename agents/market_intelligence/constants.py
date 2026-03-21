"""Shared constants for the Market Intelligence agent."""

# Sectors excluded from RS leaders unless stock price >= SECTOR_FILTER_MIN_PRICE.
# Small-cap biotech/pharma spike on drug trials — noise, not institutional accumulation.
SECTOR_FILTER_SECTORS = frozenset({
    "Healthcare",           # FMP top-level sector for biotech + pharma
})
SECTOR_FILTER_INDUSTRIES = frozenset({
    "Biotechnology",
    "Drug Manufacturers—Specialty & Generic",
    "Drug Manufacturers - Specialty & Generic",
    "Pharmaceutical Retailers",
    "Diagnostics & Research",
})
# Stocks in filtered sectors with price >= this are kept (large-cap pharma/biotech)
SECTOR_FILTER_MIN_PRICE = 50.0

# Leveraged/inverse ETFs, broad index ETFs, sector ETFs — excluded from RS leaders and EP scans
SKIP_TICKERS = frozenset({
    # Leveraged / inverse
    "TQQQ", "SQQQ", "SPXL", "SPXS", "UPRO", "SDS", "SSO", "QLD", "QID",
    "UDOW", "SDOW", "LABU", "LABD", "SOXL", "SOXS", "TNA", "TZA",
    "FNGU", "FNGD", "TECL", "TECS", "FAS", "FAZ", "NUGT", "DUST",
    "JNUG", "JDST", "GDXD", "ERX", "ERY", "GUSH", "DRIP", "UVXY",
    "SVXY", "VXX", "UVIX", "SVIX", "BOIL", "KOLD", "UCO", "SCO",
    "AGQ", "ZSL", "GLL", "DULL", "UGL", "YANG", "YINN", "CWEB",
    "BRZU", "BZQ", "EDC", "EDZ", "DRN", "DRV", "RETL", "BNKU",
    "MSTZ", "MSTU", "CONL", "TSLL", "NVDL", "NVDS",  # Single-stock leveraged
    # Broad index ETFs
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "IVV", "RSP",
    # Sector ETFs (not individual stock EPs)
    "XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLP", "XLU", "XLY",
    "XLRE", "XLC", "SMH", "IBB", "XBI", "GDX", "GDXJ", "KRE",
    # Commodity ETFs — track commodities, not stocks
    "USO", "BNO", "DBO", "UNG", "GLD", "SLV", "IAU", "PPLT", "PALL",
    "WEAT", "CORN", "SOYB", "CPER", "DBA", "DBC", "GSG", "PDBC",
    "NRGU", "NRGD",  # Leveraged energy ETNs
})
