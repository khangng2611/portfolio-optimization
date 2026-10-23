# Context đề tài — bàn giao từ giai đoạn 1 sang giai đoạn 2

Ngày khảo sát: 25/09/2026. Commit khi bắt đầu: `5350e2a`.

Tài liệu này là bản đồ để tiếp tục làm việc, không phải báo cáo xác nhận tính đúng đắn của toàn bộ mô hình. Nó phân biệt code đang có, kết quả lịch sử và kế hoạch nghiên cứu. Chưa chạy lại toàn bộ thí nghiệm IS/OOS, chưa sửa thuật toán hoặc dữ liệu. Các đường dẫn bên dưới tính từ root repository.

## 1. Đề tài và phạm vi

- Tên trong báo cáo: **Nghiên cứu và phát triển hệ thống tư vấn phân bổ danh mục đầu tư**.
- Học viên: Nguyễn Phúc Khang, MSHV 2470499; HCMUT / VNU-HCM.
- GVHD: TS. Trương Thị Thái Minh và TS. Phạm An Vinh.
- Mục tiêu dài hạn: hỗ trợ nhà đầu tư cá nhân Việt Nam phân bổ tài sản theo hồ sơ rủi ro; dùng mô hình định lượng để tính trọng số, AI để sinh quan điểm và giao tiếp/giải thích.
- Nền tảng giai đoạn 1: dữ liệu, EW/MVO/BL, sinh views tự động, XGBoost ensemble, walk-forward, chọn cổ phiếu đại diện, kiểm soát rủi ro và đánh giá lịch sử.
- Code hiện tại là Python research/CLI pipeline. Chưa thấy triển khai ứng dụng web, API phục vụ tư vấn, database hồ sơ người dùng, chatbot/RAG hoặc hệ thống agent tương ứng với thiết kế trong đề cương. Dependencies có tên framework/LLM không đồng nghĩa tính năng đã tồn tại.
- Risk Parity, LSTM/Transformer, sentiment/macro và behavioral nudges xuất hiện trong lý thuyết/roadmap, không phải các chiến lược đang chạy trong backtest.

Nguồn định hướng: `reference/topic-description.txt`, `reference/user-flow.txt`, `reports/latex/BC2_De_Cuong_Luan_Van/main.tex`, `reports/slides/thesis_defense_slides_content.md`.

## 2. Các lớp tài liệu và thứ tự đối chiếu

| Nguồn | Nội dung / vai trò |
|---|---|
| `config.py`, `assets_1.json`, source Python | Hành vi và mặc định triển khai hiện tại |
| `README.md`, `QUICKSTART.md` | Entry points; một số mô tả/mặc định đã cũ |
| `docs/DYNAMIC_VIEWS_REPORT.md`, `GEN_VIEW_LLM_GUIDE.md`, `HOW_TO_USE_LLM_GENERATORS.md` | Giai đoạn rule/relative/ML/combined; nhiều lệnh còn gọi `backtest.py` cũ |
| `docs/enhancement_process.md` | Lịch sử 4 vòng cải tiến trên universe 4 tài sản, gồm cả thử nghiệm thất bại |
| `docs/ENHANCEMENT_RANKING_REPORT.md` | Stock selection, ranker, relative views, risk layer |
| `docs/OPTION_B_VOLATILITY_TANH_SCALING.md` | Phép biến đổi dự báo theo volatility; đang dùng cho ranking_absolute |
| `docs/INDICATORS.md` | Công thức và quy ước chỉ báo kỹ thuật |
| `reports/latex/BC1_Chuyen_De_Nghien_Cuu/main.tex` | Báo cáo nghiên cứu, lý thuyết và kết quả phiên bản đầu |
| `reports/latex/BC2_De_Cuong_Luan_Van/main.tex` | Đề cương: mục tiêu, FR/NFR, UML/ERD, kiến trúc, thực nghiệm, kế hoạch |
| `reports/pdf-reports/` | Bản PDF TT1 36 trang, TT2 49 trang tại thời điểm khảo sát |
| `reports/slides/` | Nội dung, script bảo vệ và PDF 19 trang; bản nội dung Markdown đề xuất 20 slide |
| `csonet-paper/final-paper/` | Bản thảo LNCS, nguồn LaTeX, bibliography, figures, PDF hiện có 13 trang |
| `csonet-paper/paper_backtest.py` | Runner tính metric/hit rate và sinh hình bài báo |
| `csonet-paper/review.md`, `paper_writing_spec.txt` | Review/spec lịch sử; không mặc nhiên phản ánh draft hiện tại |
| `.qoder/specs/` | Lịch sử yêu cầu/thay đổi: ensemble, ranking, HYBRID, slide |
| `.qoder/repowiki/en/content/` | Wiki sinh từ code; đã lập bản đồ các chủ đề, dùng làm nguồn phụ |
| `logs/*.json` | 28 log lịch sử: metrics, views, trọng số từng lần rebalance |

`reference/`, `reports/`, `csonet-paper/`, `.qoder/`, phần lớn `logs/` bị `.gitignore` loại trừ. Chỉ đọc Git-tracked files sẽ bỏ sót phần lớn tài liệu học thuật. Các folder này không chắc sẽ có trong một clone/worktree khác.

Tài liệu tham khảo PDF đã nhận diện và trích xuất nội dung:

- `reference/LLM-Enhanced Black-Litterman Portfolio Optimization.pdf`: hướng chuyển dự báo và uncertainty của LLM thành views/độ tin cậy BL; nguồn tham khảo trực tiếp cho nhánh LLM.
- `reference/Personalized Financial Advisory Services Using AI (ResearchGate, 2024).pdf`: bối cảnh cá nhân hóa tư vấn; tên file ghi 2024 nhưng nội dung đầu tài liệu ghi 25/09/2023.
- `csonet-paper/reference-papers/Trends, Volatility, Correlations and Critical Phenomena in Financial Markets (Sara A. Safari, Christof Schmidhuber).pdf`: quan hệ trend–volatility–correlation; chưa thấy tích hợp vào code.
- `csonet-paper/reference-papers/1-s2.0-S0950705126011639-main.pdf`: bài về multimodal emotion recognition, không phải phương pháp portfolio đang triển khai. Chưa rõ mục đích lưu trong thư mục tham khảo.

Đã ưu tiên đọc sâu code lõi và các phần phương pháp, kết quả, yêu cầu, kế hoạch của tài liệu. Việc lập danh mục wiki, script vẽ hình, template và tài liệu tham khảo không đồng nghĩa audit từng dòng hay kiểm chứng độc lập mọi trích dẫn học thuật.

## 3. Quá trình phát triển cần giữ đúng ngữ cảnh

1. Universe cũ: E1VFVN30, GOLD, DCDS, MBBOND (`assets_0.json`). Rule-based / relative / pretrained XGBoost.
2. Cải tiến ensemble 5 regressors, StandardScaler, temporal validation/early stopping, expanding walk-forward. Khắc phục heuristic confidence theo variance của features khác thang đo.
3. Position cap và BL deviation alpha cố định trong lịch sử nghiên cứu. Tài liệu cũ dùng cap 40%, alpha 0.25; không phải mặc định code hiện tại.
4. Mở rộng VN30, chọn K=5 đại diện, XGBoost ranking → relative views; bổ sung volatility dampener, defensive views, constrained optimization.
5. `ranking_absolute`: dùng cùng stock selection/risk layer nhưng ensemble regression → absolute views.
6. HYBRID là output thứ tư, phối hợp MVO/BL theo regime. Có thêm Option B tanh scaling và warm-up khi đánh giá test.
7. Refactor thành package `backtest/`, thêm universe/market proxy trong JSON, cập nhật crawler.

Không dùng kết quả bước trước để chứng minh trực tiếp cho cấu hình bước sau. Đặc biệt alpha cũ là mức BL deviation, alpha HYBRID hiện tại là tỷ phần MVO.

## 4. Bản đồ code

| Module | Trách nhiệm |
|---|---|
| `crawl/stock.py` | `vnstock.ui.Market/Reference`, OHLCV stock và VNINDEX, nguồn `kbs`, split/save CSV; entry point hiện xử lý một batch stock |
| `crawl/fund.py` | NAV quỹ qua vnstock, chia 1000 và làm tròn 2 chữ số, split CSV, batch/retry |
| `crawl/gold.py` | PNJ API, chỉ location TPHCM, PNJ/SJC buy/sell, ffill và cập nhật merge giữ dữ liệu cũ khi API thiếu |
| `utils/data_loader.py` | Asset JSON, paths, chọn phase, concat train/test khi full+split, business-day alignment/ffill/dropna |
| `utils/indicators.py` | EMA/SMA, momentum, RSI, MACD, ATR, Bollinger; scalar/series có quy ước warm-up khác nhau |
| `gen_view/view_generators.py` | Static, rule-based, momentum relative, ML→view dict, combine, P/Q/confidence |
| `gen_view/xgboost/xgboost_core.py` | Single regressor và ensemble theo từng tài sản; features/labels/train/predict/pickle |
| `gen_view/xgboost/model_train.py` | Offline training CLI; `--ensemble` bổ sung ensemble artifact |
| `gen_view/ranking/stock_selection.py` | Exact combinatorial search, coverage cost theo `1-correlation`, pruning |
| `gen_view/ranking/feature_engineering.py` | Time-series, market, cross-sectional rank features |
| `gen_view/ranking/ranking_model.py` | Ensemble XGBRanker `rank:pairwise`, nhóm theo ngày, integer relevance grades, temporal split |
| `gen_view/ranking/relative_views.py` | Ghép top/bottom stocks thành relative P/Q; confidence theo score margin và disagreement |
| `gen_view/ranking/risk_management.py` | Regime normal/stress/crisis, defensive views |
| `backtest/_cli.py`, `_main.py`, `__main__.py` | CLI orchestration, warm-up, data alignment, chạy và log |
| `backtest/_loop.py` | NAV EW/MVO/BL/HYBRID, rebalance và state walk-forward |
| `backtest/_ranking_helpers.py` | Reselect/retrain/active universe/risk layer/BL sub-optimization |
| `backtest/_black_litterman.py` | Prior, Omega, posterior mean |
| `backtest/_optimizer.py` | PSD covariance repair, CVXPY, solver fallback, constraints, pruning micro-weights, HYBRID blend |
| `backtest/_views.py`, `_data_helpers.py` | View dispatch, universe/proxy/cache loading |
| `backtest/_metrics.py` | NAV, CAGR, volatility, Sharpe, Sortino, MDD, Calmar |
| `backtest/_prediction.py` | Next-period weights; hiện dùng standard view dispatcher |
| `backtest/_compare*.py` | So sánh modes, bảng CSV, plots |
| `utils/view_logger.py` | Timestamped JSON views/weights/metrics và optional NAV plot |
| `utils/plot_*.py`, `reports/**/generate_*.py` | Hình lợi suất, timeline, medoids, UML/ERD/mockup/Gantt và đồ thị báo cáo |
| `backtest/__init__.py` | Re-export facade hỗ trợ callers cũ |

## 5. Pipeline đang active

```text
CSV + assets_1.json
  → lịch thứ Hai–thứ Sáu, forward fill, giao các khoảng có dữ liệu
  → daily returns
  → mỗi 5 dòng: mean/covariance từ 20 dòng quá khứ
      → EW / full-universe MVO
      → mỗi 20 dòng: chọn 5 đại diện từ VN30 trên lịch sử tích lũy
      → mỗi 10 dòng: train ensemble trên lịch sử đã cắt theo horizon
      → dự báo 5 ngày → views + confidence
      → regime + dampener + defensive views
      → BL posterior → constrained allocation trên active universe
      → zero-pad BL ra full universe
      → HYBRID = alpha(regime)*MVO + (1-alpha)*BL
  → NAV, metrics, JSON logs / plots
```

- Active BL universe: 5 stock + GOLD + VFF, nếu các assets đó có trong portfolio input.
- Stock selection hiện là vét cạn có pruning cho mục tiêu medoid coverage, không còn thuật toán PAM dù nhiều tên/comment vẫn ghi K-Medoids. C(30,5)=142506; global optimum chỉ áp dụng cho mục tiêu coverage này.
- Regression: 8 features (momentum 5/10/20, RSI14, EMA10/EMA30 ratio, volatility20, MACD histogram, normalized price std20); target là simple forward return, không phải log-return.
- Ensemble: 5 regressors, 200 trees, depth4, learning rate0.05, seeds42–46, subsample0.8, colsample0.70–0.90. Temporal validation20%, early stopping10, tối thiểu100 valid samples.
- Confidence `clip(0.70 - std(predictions)/0.005, 0.25, 0.70)`; sau đó có thể bị volatility dampener giảm tiếp.
- `ranking_absolute` truyền recent returns để dùng `0.5*tanh(pred_return/(sigma_daily*sqrt(5)))` cho annual view. `ml/combined` standard dispatcher không truyền returns, dùng linear annualization + hard cap.
- View dict giữ annual return; `build_views_matrix` chia252 thành daily Q. Sigma, prior và posterior trong code đều ở daily scale.
- Prior dùng equal-weight benchmark proxy, không phải market-cap weights. Omega diagonal = `diag(P @ (tau*Sigma) @ P.T) / confidence`.
- Không có views thì posterior path fallback về historical mean.
- Regime dựa trên mean asset volatility và drawdown của equal-weight basket toàn portfolio; VNINDEX dùng làm feature cho ranker, không trực tiếp là regime detector.
- Test mode chính tải lịch sử train để warm-up rồi reset NAV cho evaluation. Comparison runners có đường chạy khác, xem mục cần đối chiếu.

## 6. Mặc định triển khai tại thời điểm khảo sát

| Tham số | Giá trị |
|---|---|
| Asset config / view mode / ML training | assets_1.json / ranking_absolute / walk_forward |
| Train / split / test end | 2020-01-01 / 2023-10-01 / 2026-07-01 |
| Window / rebalance / initial NAV | 20 / 5 / 1.0 |
| tau / delta | 0.05 / 2.5 |
| Feature window regression / ranking | 30 / 40 |
| Horizon / retrain / reselect / K | 5 / 10 / 20 / 5 |
| Min signal / annual view cap | 0.001 / 0.50 |
| Position cap / min post-solve weight | 0.50 / 0.01 |
| Defensive assets / defensive floor | [VFF] / 0.15 |
| Non-defensive exposure cap | 0.70 (implementation includes GOLD) |
| Risk aversion base / crisis | 1.5 / 5.0 |
| Vol ratio stress / crisis | 1.3 / 1.8 |
| Drawdown stress / crisis | -10% / -20%, lookback60 |
| HYBRID MVO share normal/stress/crisis | 0.60 / 0.30 / 0.10 |
| Trading days / risk-free annual | 252 / 0.06 |

`gen_view/xgboost/config.py` còn định nghĩa RETRAIN_FREQUENCY=20; backtest đang lấy giá trị10 từ root config.

## 7. Dữ liệu đã kiểm tra

- 288 CSV: 96 stock (32 mã ×3), 186 fund (62 quỹ ×3), 3 index, 3 gold.
- Universe cấu hình: 30 stock + GOLD + VFF; VNINDEX là proxy riêng, không nằm trong default_selection. Danh sách JSON khớp `datasets/vn30_list.txt`.
- Stocks/index thô tới 28/08/2026, funds tới 03/09/2026, gold tới 19/07/2026. Đây là max theo nhóm, không bảo đảm mọi asset cùng ngày cuối.
- Quét CSV không phát hiện trùng date trong từng file hoặc trường rỗng. Đây chưa phải kiểm tra giá điều chỉnh, stale prices, outliers hay chất lượng nguồn.
- Với default config, `build_price_table`: train 974×32 từ07/01/2020 tới29/09/2023; test 718×32 từ02/10/2023 tới01/07/2026; full 1692×32.
- Lịch `freq='B'` không loại ngày nghỉ sàn; sau ngày cuối dữ liệu của từng asset cũng có thể tiếp tục ffill tới end_date.
- Crawler lấy end date theo ngày chạy, khác TEST_END_DATE dùng khi backtest. Stock batch hiện start0/size10; fund batch start60/size10. Không mặc định crawl toàn bộ universe trong một lần gọi.

## 8. Kết quả lịch sử: giữ riêng từng nguồn

### Universe 4 tài sản — docs/enhancement_process.md

OOS được tài liệu mô tả là10/2023–03/2026:

| Strategy | NAV | Sharpe | MDD |
|---|---:|---:|---:|
| EW | 1.79 | 1.76 | -8.11% |
| MVO | 1.59 | 1.12 | -10.31% |
| BL+ML | 1.63 | 1.24 | -9.77% |

### Bản thảo CSoNet — sections/5_results.tex

OOS được bản thảo mô tả là10/2023–04/2026:

| Strategy | NAV | Sharpe | MDD |
|---|---:|---:|---:|
| EW | 1.82 | 1.15 | -17.3% |
| MVO | 3.73 | 1.64 | -15.0% |
| BL+ML | 1.90 | 1.71 | -7.1% |
| HYBRID | 2.86 | 1.83 | -11.4% |

Paper báo hit rate51.9%=174/335. Đây là số liệu được báo cáo, chưa tái lập. Bảng sensitivity của chính draft còn có alpha0.20 đạt Sharpe1.98, nên diễn đạt “highest tested Sharpe1.83” cần giới hạn rõ vào bốn strategy của bảng chính.

### Log test gần nhất — logs/views_ranking_absolute_test_20260719_112030.json

144 rebalance records, từ04/10/2023 tới01/07/2026:

| Strategy | NAV | Sharpe | MDD |
|---|---:|---:|---:|
| EW | 1.7277 | 0.8522 | -17.56% |
| MVO | 2.6537 | 1.0479 | -34.06% |
| BL | 1.8335 | 1.2011 | -15.56% |
| HYBRID | 2.3356 | 1.2194 | -24.23% |

Log train28/06/2026 khớp các NAV IS của paper: EW1.9007, MVO4.7899, BL2.0875, HYBRID3.7952. Điều này giúp truy nguyên một phần, nhưng chưa xác nhận version dữ liệu/config cho mọi bảng.

Thông điệp nghiên cứu phù hợp với các bản mới: đánh giá trade-off lợi nhuận/rủi ro của framework tích hợp; chưa tách được đóng góp nhân quả của ML, confidence, selection và defensive constraints. Không nên kết luận BL thắng mọi metric hoặc mọi baseline.

## 9. Các điểm cần đối chiếu trước khi phát triển/viết kết luận mới

Đây là ghi nhận từ đọc code/tài liệu, không phải yêu cầu tự động sửa ngay:

1. **Document drift:** tên assets.json, lệnh backtest.py, period, cap, window, alpha, retrain và universe khác nhau giữa các tài liệu.
2. **Paper–code scale:** paper mô tả annual covariance/Q; code dùng daily Sigma/Q. Code dùng `mu@w - lambda*w' Sigma w`, paper viết lambda/2. Paper còn mô tả linear clipped views, code ranking_absolute đã dùng tanh.
3. **GOLD classification:** code định nghĩa stock/non-defensive là mọi asset ngoài VFF, bao gồm GOLD. Vì tổng weights=1 và cap non-defensive70%, VFF thực tế có floor ít nhất30% khi solve khả thi, mạnh hơn floor15% được nhấn mạnh trong tài liệu.
4. **Defensive confidence:** code nhân DEFENSIVE_CONFIDENCE0.8 với multiplier0.85/1.0 →0.68/0.80; paper mô tả0.85/1.0. Basket đối ứng trong code bao gồm GOLD.
5. **HYBRID legs:** `_loop.py` dùng full-universe MVO; sub-universe constrained MVO vẫn được tính nhưng không dùng cho blend. Một số docstring/spec cũ nói hai legs cùng active universe. HYBRID không tự động thừa hưởng toàn bộ defensive constraints của BL.
6. **Holding/rebalance semantics:** NAV nhân fixed weights với return mỗi ngày, không cập nhật weight drift theo giá giữa các lần rebalance. Cần làm rõ constant-mix giả định so với thực thi rebalance mỗi5 ngày.
7. **Time alignment:** returns lệch một dòng so với prices; views dùng `prices.iloc[:t]` trong khi mu/sigma dùng returns tới trước t. Cần audit forecast timestamp, label horizon, hit-rate và warm-up boundary trước khi khẳng định no-look-ahead hoàn chỉnh.
8. **Validation gap:** outer training history được cắt theo horizon; temporal80/20 bên trong chưa thấy purge gap riêng cho overlapping forward labels.
9. **Ranker lookback:** config feature window40 nhưng features có momentum/volatility60. Predict nhận40 dòng có thể bị NaN và trả empty; cần kiểm tra thực nghiệm nhánh ranking trước khi dùng làm comparator.
10. **Constraints sau solve:** loại weights<1% rồi redistribute có thể vượt cap ban đầu. Fallback của optimizer ranking không bảo đảm cap tổng non-defensive; cần kiểm tra feasibility và constraint residuals.
11. **Comparison protocol:** `_compare_backtests.py` load pretrained ML; `_compare_ranking.py`/`run_one_mode` chưa truyền warm-up index như CLI chính. Không coi các runner tương đương về protocol test.
12. **Next-period API:** `_prediction.py` gọi standard dispatcher; mặc định ranking_absolute không được dispatcher đó xử lý. Cần thống nhất API live-inference với backtest khi làm ứng dụng.
13. **Asset paths:** GOLD full_path trỏ gold_test.csv ở cả hai JSON; full+split hiện tránh bằng concat train/test, nhưng data_mode full sẽ khác. `assets_0.json` tham chiếu E1VFVN30 không có trong snapshot datasets hiện tại.
14. **Reproducibility:** logs chưa lưu đủ config snapshot, data hashes, code commit, model provenance; chưa thấy test suite hoặc CI trong repo. Requirements chứa nhiều gói ngoài pipeline, ML dependencies chưa pin chặt.
15. **Research limitations:** chưa có chi phí giao dịch/slippage/liquidity/thuế, point-in-time VN30, independent confidence calibration, no-ML/fixed-confidence ablation và kiểm định độ bền đủ để quy đóng góp riêng cho ML.
16. **Historical reviews:** review.md nói PDF17 trang, PDF hiện có13; phải kiểm tra artifact hiện tại trước khi dùng nhận xét cũ làm backlog.

## 10. Giai đoạn 2 theo đề cương — bối cảnh ban đầu

- Hồ sơ rủi ro người dùng, mục tiêu và thời hạn đầu tư.
- User Interaction Agent, Views Generator, Data/Preprocessor, deterministic BL engine, Explanation & Nudge Agent.
- LLM/RAG: giao tiếp tiếng Việt, truy xuất dữ liệu/tin tức, diễn giải allocation; có thể nghiên cứu thêm LLM-generated views.
- Web UI, user testing, behavioral nudges.
- Mở rộng assets/features, macro/cross-asset/sentiment; adaptive risk controls.
- Transaction-cost model, thực nghiệm/ablation và hoàn thiện luận văn.

Một phần mở rộng VN30 và dynamic alpha theo regime đã có trong code sau đề cương. Không đưa lại các mục này thành công việc chưa làm chỉ vì tài liệu cũ ghi future work. Timeline trong đề cương là kế hoạch lịch sử. Phạm vi mới được người dùng xác nhận được ghi tại mục 12 bên dưới.

## 11. Kiểm tra trong lần khởi tạo context

- Git working tree sạch trước khảo sát; không thấy AGENTS.md trong repo hoặc các thư mục cha đã kiểm tra.
- AST parse thành công43 file Python dưới backtest/gen_view/utils/crawl/reports/csonet-paper.
- Đọc và thống kê toàn bộ288 CSV; load default train/test/full thành công.
- Smoke run bằng venv Python3.12:170 dòng giá, 5 stock + GOLD/VFF; modes rule_based, relative, ranking_absolute. Mỗi mode trả150 điểm NAV,30 lần rebalance; NAV hữu hạn/dương và tổng weights≈1. Ranking_absolute sinh32 views trong run ngắn.
- Smoke selection dùng universe5 để chạy nhẹ; **không xác nhận runtime/optimality của toàn bộ30-stock search**, performance IS/OOS, mọi constraints hoặc nhánh relative ranker.
- Có cảnh báo fontconfig cache không ghi được trong sandbox; numerical smoke runs vẫn exit0. Không tạo lại figure/báo cáo lịch sử.
- Chỉ bổ sung tài liệu context này; không crawl, train/save model cache, sửa source/dataset, commit hoặc push.

Các lệnh chính để tra cứu khi có yêu cầu tiếp theo (full runs có thể tốn thời gian và sinh logs):

```bash
venv/bin/python -m backtest --help
venv/bin/python -m backtest --phase train --view-mode ranking_absolute --no-plot
venv/bin/python -m backtest --phase test --view-mode ranking_absolute --no-plot
venv/bin/python -m backtest._compare_ranking --phase test --no-plot
venv/bin/python gen_view/xgboost/model_train.py --method xgboost --train-phase train --ensemble
```

Khi mở task mới, đọc tài liệu này rồi kiểm tra lại Git/config/data liên quan. Context là snapshot có nguồn, không bảo đảm trạng thái repo sẽ giữ nguyên và không thay cho chỉ dẫn mới của người dùng.

## 12. Định hướng giai đoạn 2 đã xác nhận — 25/09/2026

- Người dùng yêu cầu Technical Specification để xây ứng dụng full-stack và tích hợp kết quả nghiên cứu/ứng dụng vào luận văn; dựa BC2 và file /Users/nguyenkhang/Downloads/proposed-architecture.md.
- Người dùng đã chọn: **sản phẩm hướng production ngay, nhiều người dùng và các dịch vụ triển khai độc lập**. Không mặc định quay về pilot/modular monolith.
- Bản thiết kế chi tiết: [TECHNICAL_SPECIFICATION_PHASE_2.md](TECHNICAL_SPECIFICATION_PHASE_2.md). Chọn domain microservices, owned databases, REST/AMQP/SSE, Portfolio saga, Quant/ML/Market/Chat/Knowledge/Research, Identity và Web/BFF.
- Precompute forecasts/selection; final allocation phải tính theo personalized inputs. Core numerical được version hóa và dùng chung Quant/Research, legacy-v1 giữ để tái lập.
- Tất cả sơ đồ xuất source Mermaid trong code blocks, không xuất ảnh static.
- AWS reference deployment, capacity/SLO, retention và các preset là đề xuất thiết kế cần kiểm chứng/chốt khi triển khai, không phải kết quả đã đạt.
- Nhiệm vụ này bổ sung tài liệu thiết kế/context; chưa triển khai ứng dụng, sửa numerical source hoặc tái chạy toàn bộ kết quả giai đoạn 1.
