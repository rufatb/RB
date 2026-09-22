"""Registered research coverage limits; never the production selection universe."""

# Explicit roster, not a claim of current TSX60 membership or ADV rank.
# The historic expansion of production density selection remains rejected.
# PRUNED 2026-09-22: thirteen symbols Yahoo no longer recognises — acquired,
# taken private or renamed (Enerplus, Veren, MEG, NuVista, Crew, CI Financial,
# MAG Silver, SilverCrest, New Gold, Boralex, InterRent, Badger; PBA is Pembina's
# NYSE ticker, PPL.TO is already here). The quote endpoint returned no price for
# any of them and the news feed returned an EMPTY channel, which the identity
# check correctly refused as RSS_CHANNEL_IDENTITY_MISMATCH — eleven "headline
# failures" a day that were really a stale roster.
DELISTED = ('PBA.TO', 'BLX.TO', 'CIX.TO', 'BCI.TO', 'IIP-UN.TO', 'MEG.TO', 'CR.TO', 'VRN.TO', 'ERF.TO', 'NVA.TO', 'NGD.TO', 'MAG.TO', 'SIL.TO')

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
    # Day-107 widening, on request. Liquid TSX names outside the first roster;
    # still a fixed explicit list, still NOT a claim of index membership or ADV
    # rank, and still never the production selection universe. Coverage is
    # gated by prepared technicals, not by the length of this tuple: a name
    # that cannot produce 35 contiguous complete sessions is excluded whether
    # or not it is listed here.
    'BIP-UN.TO', 'BEP-UN.TO', 'KEY.TO', 'ALA.TO', 'GEI.TO',
    'CPX.TO', 'NPI.TO', 'ACO-X.TO', 'AQN.TO',
    'WN.TO', 'EMP-A.TO', 'ATZ.TO', 'GIL.TO', 'BYD.TO',
    'CIGI.TO', 'FSV.TO', 'TIH.TO', 'FTT.TO', 'RBA.TO',
    'LNR.TO', 'MRE.TO', 'CAE.TO', 'BBD-B.TO', 'ONEX.TO', 'X.TO',
    'IGM.TO', 'ELF.TO', 'DFY.TO', 'TSU.TO',
    'CCA.TO', 'TC.TO', 'DIR-UN.TO', 'GRT-UN.TO',
    'REI-UN.TO', 'CAR-UN.TO', 'SRU-UN.TO', 'FCR-UN.TO', 'BTE.TO', 'WCP.TO', 'BIR.TO', 'PEY.TO', 'TVE.TO',
    'LUN.TO', 'HBM.TO', 'CS.TO', 'ERO.TO', 'IVN.TO',
    'ELD.TO', 'IMG.TO', 'BTO.TO', 'OGC.TO', 'EQX.TO', 'SSRM.TO',
    'PAAS.TO', 'CG.TO', 'AGI.TO', 'LUG.TO',
)
# Day-107: the roster more than doubled and staging moved to 09:05, so the
# pre-open window is ~25 minutes rather than minutes. 60 names took ~26s; this
# leaves room for 131 without the budget becoming the thing that caps coverage.
# It is still a bound, not an SLA, and it never runs into the 09:30 cut-off.
BUDGET_SECONDS = 420
REQUEST_SECONDS = 18
WORKERS = 8
REGISTRATION = 'PREREGISTER_day100_deepseek_reliability.md'
EXPANDED_TARGET = 150
EXPANDED_BUDGET_SECONDS = 240
EXPANSION_REGISTRATION = 'PREREGISTER_day101_tsx_expansion.md'
