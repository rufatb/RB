"""Day100 research coverage target; never the production selection universe."""

# Explicit roster, not a claim of current TSX60 membership or ADV rank.
# The historic expansion of production density selection remains rejected.
TICKERS = (
    'AC.TO', 'RY.TO', 'TD.TO', 'BNS.TO', 'BMO.TO', 'CM.TO', 'ENB.TO',
    'TRP.TO', 'CNQ.TO', 'SU.TO', 'CVE.TO', 'CP.TO', 'CNR.TO', 'SHOP.TO',
    'ABX.TO', 'AEM.TO', 'NTR.TO', 'MFC.TO', 'SLF.TO', 'BCE.TO', 'T.TO',
    'NA.TO', 'GWO.TO', 'IFC.TO', 'POW.TO', 'BN.TO', 'BAM.TO', 'FFH.TO',
    'IMO.TO', 'TOU.TO', 'PPL.TO', 'ARX.TO', 'CCO.TO', 'TECK-B.TO', 'FM.TO',
    'K.TO', 'WPM.TO', 'FNV.TO', 'ATD.TO', 'DOL.TO', 'L.TO', 'MRU.TO',
    'QSR.TO', 'SAP.TO', 'MG.TO', 'WCN.TO', 'TFII.TO', 'WSP.TO', 'STN.TO',
    'EMA.TO', 'FTS.TO', 'H.TO', 'CU.TO', 'CSU.TO', 'GIB-A.TO', 'OTEX.TO',
    'RCI-B.TO', 'TRI.TO', 'QBR-B.TO', 'CTC-A.TO',
)
BUDGET_SECONDS = 120
REQUEST_SECONDS = 18
WORKERS = 8
REGISTRATION = 'PREREGISTER_day100_deepseek_reliability.md'
