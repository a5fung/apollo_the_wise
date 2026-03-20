"""
Stock universe for RS calculations.

~150 liquid US stocks covering all major sectors and themes.
Polygon free tier supports individual ticker aggregates, so we use
a curated list rather than pulling all 8000+ US stocks.

Expand this list over time. Keep to ~200 max for the nightly run
to complete in <1 hour at Polygon free tier (5 calls/min).
"""

# Each entry: (ticker, one-line business description)
# Description helps Claude cluster stocks into themes by actual business,
# not just sector label.
UNIVERSE_WITH_DESC: list[tuple[str, str]] = [
    # Technology — large cap
    ("AAPL", "Consumer electronics, iPhones, services ecosystem"),
    ("MSFT", "Enterprise software, Azure cloud, AI platform"),
    ("NVDA", "AI/data center GPUs, inference & training chips"),
    ("AVGO", "Networking semis, custom AI accelerators (XPUs)"),
    ("AMD", "CPUs & GPUs for data center, gaming, AI"),
    ("QCOM", "Mobile SoCs, wireless modems, IoT chips"),
    ("INTC", "Legacy CPU maker, foundry pivot"),
    ("MU", "DRAM & NAND memory, HBM for AI GPUs"),
    ("AMAT", "Semiconductor equipment, deposition & etch"),
    ("LRCX", "Semiconductor equipment, etch & deposition"),
    ("KLAC", "Semiconductor equipment, inspection & metrology"),
    ("MRVL", "Custom AI silicon, networking, storage controllers"),
    ("SMCI", "AI server systems, GPU rack infrastructure"),
    ("ARM", "Chip architecture licensing, mobile & data center"),
    ("CRWD", "Endpoint cybersecurity, cloud-native platform"),
    ("PANW", "Enterprise cybersecurity, firewall & SASE"),
    ("FTNT", "Network security appliances, SD-WAN"),
    ("ZS", "Zero-trust cloud security, SASE"),
    ("OKTA", "Identity & access management"),
    ("CYBR", "Privileged access management, identity security"),
    ("NOW", "IT service management, enterprise workflow automation"),
    ("CRM", "CRM software, enterprise AI (Einstein)"),
    ("SNOW", "Cloud data warehouse & analytics"),
    ("DDOG", "Cloud monitoring, observability platform"),
    ("MDB", "NoSQL database, developer data platform"),
    ("TEAM", "Collaboration software (Jira, Confluence)"),
    ("ASAN", "Work management & project collaboration"),
    ("HUBS", "Inbound marketing, CRM for SMBs"),
    # Technology — mid cap / high growth
    ("PLTR", "AI analytics for government & enterprise"),
    ("AI", "Enterprise AI platform (C3.ai)"),
    ("PATH", "Robotic process automation (UiPath)"),
    ("SOUN", "Voice AI, conversational intelligence"),
    ("IONQ", "Quantum computing hardware"),
    ("QUBT", "Quantum computing software"),
    ("RGTI", "Quantum computing (Rigetti)"),
    ("ARQQ", "Quantum encryption & networking"),
    # Semiconductors / AI infrastructure
    ("TSM", "Foundry, manufactures chips for NVDA/AMD/AAPL"),
    ("ASML", "Extreme UV lithography machines, chip manufacturing"),
    ("MCHP", "Microcontrollers, analog, embedded systems"),
    ("ADI", "Analog semiconductors, signal processing"),
    ("TXN", "Analog & embedded chips, industrial/auto"),
    ("ON", "Power semiconductors, auto/industrial"),
    ("WOLF", "Silicon carbide power semis, EV charging"),
    # AI optical / networking
    ("CIEN", "Optical networking equipment, WDM systems"),
    ("FNSR", "Optical transceivers, datacom/telecom"),
    ("COHR", "Optical components, AI datacenter transceivers"),
    ("LITE", "Optical components, 3D sensing, telecom"),
    ("VIAVI", "Optical test & measurement, network monitoring"),
    ("IIVI", "Photonic components, compound semiconductors"),
    # Cloud / hyperscalers
    ("META", "Social media, VR/AR, AI research"),
    ("GOOGL", "Search, cloud, AI (Gemini), advertising"),
    ("AMZN", "E-commerce, AWS cloud, AI infrastructure"),
    # Consumer discretionary
    ("TSLA", "Electric vehicles, energy storage, autonomy"),
    ("NKE", "Athletic footwear & apparel"),
    ("LULU", "Premium athletic apparel"),
    ("DECK", "Performance footwear (Hoka, UGG)"),
    ("CROX", "Casual footwear (Crocs, Heydude)"),
    ("BKNG", "Online travel booking (Booking.com, Priceline)"),
    ("ABNB", "Short-term rental marketplace"),
    ("UBER", "Ride-hailing, food delivery, freight"),
    ("LYFT", "Ride-hailing"),
    ("DPZ", "Pizza delivery chain, tech-driven operations"),
    ("CMG", "Fast-casual restaurants (Chipotle)"),
    # Financials
    ("JPM", "Largest US bank, investment banking, trading"),
    ("GS", "Investment banking, trading, asset management"),
    ("MS", "Investment banking, wealth management"),
    ("BLK", "World's largest asset manager (iShares ETFs)"),
    ("V", "Payment network, credit/debit card processing"),
    ("MA", "Payment network, credit/debit card processing"),
    ("PYPL", "Digital payments, Venmo"),
    ("SQ", "Payment processing, Cash App, Bitcoin"),
    ("COIN", "Cryptocurrency exchange"),
    ("BAC", "Major US bank, consumer & commercial banking"),
    ("WFC", "Major US bank, consumer & commercial banking"),
    ("C", "Global bank, institutional clients"),
    ("AXP", "Premium credit cards, travel rewards"),
    ("SCHW", "Discount brokerage, wealth management"),
    # Healthcare / biotech
    ("LLY", "Pharma, GLP-1 obesity/diabetes drugs"),
    ("NVO", "Pharma, GLP-1 obesity/diabetes drugs (Ozempic)"),
    ("ABBV", "Pharma, immunology (Humira successor), oncology"),
    ("MRK", "Pharma, oncology (Keytruda), vaccines"),
    ("PFE", "Pharma, vaccines, oncology"),
    ("AMGN", "Biotech, biosimilars, oncology, obesity pipeline"),
    ("GILD", "Biotech, HIV/HCV antivirals, oncology"),
    ("REGN", "Biotech, eye disease (Eylea), immunology"),
    ("VRTX", "Biotech, cystic fibrosis, pain pipeline"),
    ("MRNA", "mRNA vaccines & therapeutics"),
    ("BNTX", "mRNA vaccines & cancer immunotherapy"),
    ("SGEN", "Antibody-drug conjugates, oncology"),
    ("INCY", "Biotech, hematology/oncology (Jakafi)"),
    ("IRTC", "Cardiac monitoring devices, digital health"),
    ("ISRG", "Robotic surgery systems (da Vinci)"),
    ("DXCM", "Continuous glucose monitors"),
    ("PODD", "Insulin pump systems (Omnipod)"),
    ("GEHC", "Medical imaging, diagnostics equipment"),
    # Energy
    ("XOM", "Integrated oil & gas major"),
    ("CVX", "Integrated oil & gas major"),
    ("COP", "Exploration & production, US shale"),
    ("EOG", "Exploration & production, shale oil"),
    ("PXD", "Permian Basin shale oil producer"),
    ("SLB", "Oilfield services, drilling technology"),
    ("HAL", "Oilfield services, completions & production"),
    ("FANG", "Permian Basin oil producer (Diamondback)"),
    ("MPC", "Oil refining, fuel distribution"),
    ("VLO", "Oil refining, renewable diesel"),
    # Industrials
    ("CAT", "Construction & mining equipment"),
    ("DE", "Agricultural & construction equipment"),
    ("HON", "Diversified industrial, aerospace, automation"),
    ("RTX", "Aerospace & defense, jet engines, missiles"),
    ("LMT", "Defense prime, F-35, missiles, space"),
    ("GD", "Defense, submarines, Gulfstream jets"),
    ("NOC", "Defense, stealth bombers, space systems"),
    ("GE", "Aviation engines, power, renewable energy"),
    ("ETN", "Power management, electrical systems"),
    ("AXON", "Law enforcement tech, body cameras, tasers"),
    ("TRMB", "GPS, precision agriculture, construction tech"),
    # Materials
    ("FCX", "Copper & gold mining"),
    ("NEM", "Gold mining"),
    ("AA", "Aluminum production"),
    ("X", "Steel production (US Steel)"),
    ("STLD", "Steel production, recycling"),
    ("RS", "Steel & metals distribution"),
    # Utilities
    ("NEE", "Renewable energy utility, wind & solar"),
    ("VST", "Power generation, nuclear fleet"),
    ("NRG", "Power generation & retail electricity"),
    ("CEG", "Nuclear power generation (Constellation)"),
    # Real estate
    ("AMT", "Cell tower REIT"),
    ("EQIX", "Data center REIT"),
    ("PLD", "Industrial/logistics warehouse REIT"),
    # Consumer staples
    ("COST", "Warehouse club retail"),
    ("WMT", "Mass-market retail, grocery, e-commerce"),
    ("MNST", "Energy drinks"),
    ("KO", "Beverages (Coca-Cola)"),
    ("PEP", "Beverages & snacks (Pepsi, Frito-Lay)"),
    # Communications
    ("NFLX", "Streaming video, original content"),
    ("DIS", "Entertainment, streaming (Disney+), parks"),
    ("SPOT", "Music streaming"),
    ("TTD", "Programmatic digital advertising"),
    ("PINS", "Visual discovery & social media (Pinterest)"),
    ("SNAP", "Social media (Snapchat), AR"),
    # ETFs for regime / benchmark
    ("SPY", "S&P 500 ETF"),
    ("QQQ", "Nasdaq 100 ETF"),
    ("IWM", "Russell 2000 small-cap ETF"),
    ("XLK", "Technology sector ETF"),
    ("XLF", "Financial sector ETF"),
    ("XLE", "Energy sector ETF"),
    ("XLV", "Healthcare sector ETF"),
    ("XLI", "Industrial sector ETF"),
]

# Flat ticker list for backward compatibility
UNIVERSE: list[str] = list(dict.fromkeys(t for t, _ in UNIVERSE_WITH_DESC))

# Ticker → description lookup
TICKER_DESC: dict[str, str] = {t: d for t, d in UNIVERSE_WITH_DESC}
