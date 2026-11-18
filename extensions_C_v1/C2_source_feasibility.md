# C2 source feasibility

Research date 2026-11-04. Status: **NOT RUN — DAILY SERIES AND RIGHTS/VINTAGE GATE NOT MET**. This is the stop deliverable specified in experiment_1.md, not a finding that Vietnamese total-return indices do not exist.

VN30TRI is the first candidate fixed in protocol_frozen.md. Official index identity and a historical dividend-method definition were verified. No accepted daily level file was obtained on 2023-09-29–2026-04-29 with the required vendor-record dates, historical methodology/vintage and research-use rights. Consequently there are no C2 NAV/Sharpe/outperformance statistics and no three-path index chart. Numerical result cells remain null with an explicit status.

## Sources examined

1. [HOSE June 2026 factsheet](https://staticfile.hsx.vn/Uploads/UploadDocuments/2468981/Form_Factsheet_MCIndices_VN_T06.2026.pdf): confirms VN30TRI as an end-of-day total-return variant in VND. A factsheet is not the required daily historical observation file. Its post-sample date does not certify a historical data vintage.
2. [HOSE index rules version 1.2, hosted by SSC](https://ssc.gov.vn/webcenter/contentattachfile/idcplg?IdcService=GET_FILE&allowInterrupt=1&dID=87913&dDocName=APPSSCGOVVN162095654&Rendition=Quy%20tac%20chi%20so&filename=Quy%20tac%20bo%20chi%20so%20HOSE%20index_May2015_Ver1.2%20(Them%20chi%20so%20TRI)-final.pdf&IsAttachment=1): section 5A describes gross cash-dividend reinvestment on the ex-date and end-of-day total-return calculation. It establishes a historical definition, not an observation-vintage archive or permission for a vendor export across all evaluation dates.
3. [TradingView VN30TRI](https://www.tradingview.com/symbols/HOSE-VN30TRI/): confirms the HOSE symbol and displays a chart. The retrieved public page supplies neither the accepted daily export nor row-level vintage/rights evidence. No private chart transport, account bypass or unlicensed export was used.
4. [CEIC VN30 total-return series](https://www.ceicdata.com/en/vietnam/ho-chi-minh-stock-exchange-monthly/ho-chi-minh-stock-exchange-index-total-return-vn30): identifies a monthly dataset sourced through Exchange Data International. Monthly observations cannot replace 641 daily returns; no interpolation or zero filling was performed. No inference is made about paid daily datasets outside this retrieved page.
5. [FiinQuant market-breadth documentation](https://docs.fiinquant.vn/ham-va-cong-thuc/4.-thong-ke-thi-truong/4.1.-lay-du-lieu-ve-do-rong-thi-truong-so-ma-san-so-ma-tran-so-ma-tang-giam-tham-chieu): lists VN30TRI among recognized groups, but that endpoint supplies breadth rather than the historical close-level sequence. A recognized ticker alone is insufficient.

Searches also targeted official hsx.vn history and FiinQuant historical-index documentation. Public search results identify vendor capabilities but no authenticated data entitlement was available to this task. No request for payment, new contract, or access credential was made.

## Missing pack and a precise route forward

Obtain a lawfully shared daily VN30TRI level file including the anchor 2023-09-29 and all 641 subsequent portfolio return dates, index_date/index_level/vendor_record_date; canonical identifier/currency; dividend and corporate-action method; publication/methodology changes; vintage/backfill description; retrieval timestamp; and evidence that research use is permitted. Ask separately whether raw redistribution is allowed. A local research license must not be treated as a raw-data upload license.

The supervisor/data owner can choose a licensed HOSE/vendor route. C2_market.py already implements a fail-closed metadata gate and no-gap single-session alignment for a future approved input. If full coverage is unavailable, its pre-fixed fallback is the longest contiguous common daily-return interval with portfolios recomputed on the same dates. The existing VNINDEX price series remains excluded from C2.

C2 data availability and rights require follow-up; C1 is unaffected. Market-relative alpha and same-risk superiority are not established.
