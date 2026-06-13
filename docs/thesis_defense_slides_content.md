# Nội dung 20 slide phản biện đề cương luận văn

> **Đề tài:** Tối ưu hóa danh mục đầu tư cho thị trường Việt Nam: Black-Litterman tăng cường XGBoost Ensemble và LLM
> **Học viên:** Nguyễn Phúc Khang — MSHV 2470499 · **GVHD:** TS. Trương Thị Thái Minh & TS. Phạm An Vinh
> **Canva design:** `DAHMFdeMr-o` — https://www.canva.com/design/DAHMFdeMr-o/edit
> **Ký hiệu:** 📷 = ảnh có sẵn trong `reports/BC2_De_Cuong_Luan_Van/figures/` · 🎨 = gợi ý ảnh nên thiết kế / chèn thêm · ⚪ = giữ placeholder template

---

## Slide 1 — Cover (30s)

**Title:** PHẢN BIỆN ĐỀ CƯƠNG LUẬN VĂN THẠC SĨ
**Subtitle:** Tối ưu hóa danh mục đầu tư cho thị trường Việt Nam: Black-Litterman tăng cường bằng XGBoost Ensemble và LLM
**University/Date:** Đại học Bách Khoa TP.HCM — Tháng 06/2026
**Presenter:** Học viên: Nguyễn Phúc Khang — 2470499
**Advisors:** GVHD: TS. Trương Thị Thái Minh & TS. Phạm An Vinh

**Hình ảnh:**
- 🎨 Logo ĐHBK TP.HCM (hoặc logo Khoa KH&KTMT) ở góc trên/dưới
- ⚪ Giữ ảnh nền template

---

## Slide 2 — Mục lục (30s)

**Heading:** Nội dung trình bày
**Body:**
1. **Bối cảnh & Động lực** — toàn cầu và thực trạng tại Việt Nam.
2. **Mục tiêu & Khoảng trống nghiên cứu** — vì sao chọn hướng đi này.
3. **Phương pháp đề xuất** — kiến trúc, Black-Litterman, XGBoost Ensemble, hai cải tiến mới (Stock Selection + Risk Management).
4. **Thực nghiệm & Kết quả** — 4 vòng cải tiến, BL+ML vs MVO IS/OOS.
5. **Đánh giá & Kế hoạch giai đoạn 2** — tính mới, tính khả thi, roadmap luận văn tốt nghiệp.

**Hình ảnh:**
- ⚪ Không cần (text-only); có thể thêm icon nhỏ cạnh mỗi mục (📊 🔍 ⚙️ 🧪 🚀)

---

## Slide 3 — Bối cảnh & Động lực toàn cầu (60s)

**Heading:** Bối cảnh quốc tế
**Body:** Robo-advisor toàn cầu (Betterment, Wealthfront, Vanguard Digital Advisor) đã quản lý hàng trăm tỷ USD bằng các mô hình toán học và thuật toán. Sự nổi lên của Large Language Models (GPT-4, Llama, các mô hình hỗ trợ tiếng Việt) mở ra khả năng kết hợp tối ưu hóa định lượng với giao tiếp tự nhiên. Black-Litterman (BL) — kết hợp cân bằng thị trường + views nhà đầu tư qua khuôn khổ Bayesian — đang được nghiên cứu sôi nổi như nền tảng cho thế hệ robo-advisor mới, đặc biệt khi tích hợp Machine Learning để sinh views tự động.

**Hình ảnh:**
- 🎨 Logo các robo-advisor (Betterment, Wealthfront, Vanguard) hoặc biểu đồ AUM toàn cầu
- 🎨 Hình minh họa AI/LLM (mạng neural cách điệu)

---

## Slide 4 — Thực trạng tại Việt Nam (60s)

**Heading:** Thực trạng tại Việt Nam
**Body:** Theo UBCKNN (10/2025), Việt Nam có hơn **12 triệu** tài khoản chứng khoán cá nhân, song phần lớn nhà đầu tư cá nhân thiếu kiến thức chuyên sâu về phân bổ tài sản và quản lý rủi ro — quyết định đầu tư chủ yếu dựa cảm tính, theo đám đông. Lĩnh vực robo-advisor tại VN còn rất sơ khai do (1) thiếu dữ liệu lịch sử dài hạn, (2) số loại tài sản đầu tư hạn chế, (3) hành vi nhà đầu tư có nhiều thiên lệch tâm lý. Đây là cơ hội nghiên cứu một hệ tư vấn vừa **định lượng** (BL + ML) vừa **giao tiếp tự nhiên tiếng Việt** (LLM + RAG + behavioral nudges).

**Hình ảnh:**
- 🎨 Biểu đồ tăng trưởng số tài khoản chứng khoán VN 2018→2025 (12tr+)
- 🎨 Skyline TP.HCM / cờ Việt Nam / hình ảnh sàn HOSE

---

## Slide 5 — Mục tiêu & Câu hỏi nghiên cứu (60s)

**Heading:** Mục tiêu nghiên cứu
**Body 1 (col 1):**
(i) **Xây dựng mô hình tối ưu DMĐT phù hợp thị trường VN**: so sánh MVO, Risk Parity, Black-Litterman → chọn BL làm core nhờ khả năng tích hợp dynamic views với độ tin cậy hiệu chỉnh.
(ii) **Ứng dụng AI tăng cường BL**: XGBoost Ensemble + Walk-forward sinh ML views thay cho view chủ quan; LLM/RAG cho view định tính từ tin tức & giải thích quyết định bằng tiếng Việt.

**Body 2 (col 2):**
(iii) **Triển khai & đánh giá**: walk-forward backtest IS + OOS trên dữ liệu VN, so sánh với EW, MVO, BL-Rule.
**Câu hỏi NC chính:** Mô hình BL+ML có thể vượt MVO trên thị trường VN cả về NAV, Sharpe và MDD trong điều kiện walk-forward thực tế không, đồng thời đảm bảo khả năng giải thích cho nhà đầu tư cá nhân?

**Hình ảnh:**
- ⚪ Không cần (text-heavy); hoặc 🎨 sơ đồ 3-mục-tiêu dạng arrow flow

---

## Slide 6 — Khoảng trống NC (1): Hạn chế phương pháp (60s)

**Heading:** Khoảng trống nghiên cứu (1) — Phương pháp
**Body 1 (col 1):** **MVO** (Markowitz, 1952) là nền tảng MPT nhưng nhạy cảm cực mạnh với sai số ước lượng μ — *Markowitz curse*. Một thay đổi nhỏ trong vector lợi nhuận kỳ vọng dẫn đến danh mục biến động hoàn toàn, thường tạo phân bổ tập trung cực đoan. **Maximum Drawdown** trong các thử nghiệm có thể lên đến −26% đến −65%, không phù hợp triển khai thực tế.

**Body 2 (col 2):** **BL gốc** (Black & Litterman, 1992) khắc phục được *Markowitz curse* nhưng truyền thống chỉ dùng **view chủ quan** từ analyst — không tận dụng dữ liệu lớn. Các mở rộng BL+ML chủ yếu áp dụng trên thị trường phát triển (Mỹ, EU). **Khoảng trống**: chưa có nghiên cứu hệ thống về dynamic ML views + risk-aware BL cho thị trường mới nổi như VN.

**Hình ảnh:**
- 🎨 Biểu đồ minh họa Markowitz curse (efficient frontier biến dạng khi μ thay đổi nhỏ)
- 🎨 Equity curve MVO với MDD lớn

---

## Slide 7 — Khoảng trống NC (2): Thiếu nghiên cứu trên TT VN (60s)

**Heading:** Khoảng trống nghiên cứu (2) — Thị trường Việt Nam
**Body 1 (col 1):** Tại VN, equilibrium từ market-cap khó ước lượng do quy mô vốn hóa nhỏ, biến động cao và chưa có chuỗi dữ liệu dài hạn ổn định. Vai trò của **views** trong khuôn khổ BL trở nên quan trọng hơn bao giờ hết — song hầu như không có nghiên cứu nào triển khai BL với dynamic views trên VN30 với phân tích đầy đủ in-sample + out-of-sample.

**Body 2 (col 2):** Các phương pháp BL/MVO truyền thống thiếu **cơ chế kiểm soát rủi ro thích ứng theo regime** thị trường — đặc biệt quan trọng tại thị trường mới nổi với nhiều giai đoạn biến động mạnh (crash 2022, bull-run vàng 2024). Đề tài lấp 3 khoảng trống: (a) BL+ML cho VN, (b) Combinatorial Stock Selection thay heuristic, (c) Risk Management Layer thích ứng.

**Hình ảnh:**
- 🎨 Biểu đồ VN-Index 2020–2026 highlight các giai đoạn crash/bull (2022 crash, 2024 gold rally)
- 🎨 Sơ đồ 3 khoảng trống → 3 đóng góp

---

## Slide 8 — 4 Trụ cột Phương pháp Đề xuất (60s)

**Heading:** 4 Trụ cột Phương pháp Đề xuất
**Card 1:** **BL Dynamic Views** — thay views tĩnh bằng views động, hợp nhất nhiều nguồn (rule, ML, LLM) trong một khuôn khổ Bayesian thống nhất.
**Card 2:** **XGBoost Ensemble + Walk-forward** — 5 model per asset, retrain mỗi 20 phiên trên expanding window, embargo gap chống leak, confidence từ ensemble disagreement.
**Card 3:** **Combinatorial Stock Selection** *(mới)* — chọn K=5 đại diện VN30 bằng vét cạn tổ hợp, đảm bảo **global optimum**, deterministic.
**Card 4:** **Risk Management Layer** *(mới)* — regime detection + defensive views + volatility dampener + constrained MVO; mục tiêu giảm MDD và làm mượt equity curve trong walk-forward.

**Hình ảnh:**
- 🎨 4 icon đại diện 4 trụ cột (Bayesian / Tree / Combinatorial / Shield) đặt trong 4 card
- ⚪ Hoặc giữ layout 4-card placeholder của template

---

## Slide 9 — Tổng quan kiến trúc đa tác tử (75s)

**Heading:** Kiến trúc tổng quan
**Body 1:** Hệ multi-agent. **Data Agent** thu thập + tiền xử lý lịch sử giá (vnstock, TCBS, HOSE). **View Generation Agent** sinh views song song từ 4 nguồn. **BL Engine** hợp nhất views thành posterior μ_BL. **Optimizer Agent** giải MVO ràng buộc → trọng số tối ưu w*.

**Body 2:** **Explanation Agent** dùng LLM diễn giải quyết định bằng tiếng Việt. Toàn pipeline được walk-forward backtest: rebalance mỗi 5 phiên, retrain ML mỗi 20 phiên, reselect VN30 mỗi 60 phiên.

**Hình ảnh:**
- 📷 **`system_architecture.png`** — sơ đồ multi-agent (BẮT BUỘC chèn — đây là slide kiến trúc)
- Đường dẫn: `reports/BC2_De_Cuong_Luan_Van/figures/system_architecture.png`

---

## Slide 10 — Pipeline sinh views từ 4 nguồn (60s)

**Heading:** Pipeline sinh views động
**Body 1:** **(a) Rule-based** — EMA crossover + RSI + momentum → absolute views. **(b) Relative momentum** — so sánh momentum giữa cặp tài sản, sinh relative views (A outperform B).

**Body 2:** **(c) ML XGBoost** — features kỹ thuật + forward return label → predict đến walk-forward. **(d) LLM-RAG** — Dense Passage Retrieval truy xuất tin tức → LLM sinh view có cấu trúc JSON. Combined views = 0.4 rule + 0.3 relative + 0.3 ML, có cơ chế hợp nhất theo confidence và giới hạn tối đa k_max=10 views.

**Hình ảnh:**
- 🎨 Sơ đồ 4 nguồn views → BL Engine (flow diagram, 4 box màu khác nhau hợp lưu vào 1 box)
- Có thể tạo bằng Mermaid/Excalidraw rồi export PNG

---

## Slide 11 — Black-Litterman: cơ sở & vai trò views (60s)

**Heading:** Mô hình Black-Litterman (cơ sở)
**Body 1:** Equilibrium return ngầm định: π = δ·Σ·w_mkt. Posterior Bayesian: μ_BL = [(τΣ)⁻¹ + Pᵀ·Ω⁻¹·P]⁻¹ · [(τΣ)⁻¹·π + Pᵀ·Ω⁻¹·Q]. Trong đó P chọn tài sản trong view, Q là kỳ vọng view, Ω là độ bất định view (tỷ lệ nghịch confidence).

**Body 2:** **Vai trò views**: confidence cao → Ω nhỏ → BL tin view nhiều → posterior dịch xa equilibrium. Confidence thấp → Ω lớn → BL coi view như nhiễu, posterior gần equilibrium. Đây chính là điểm BL ưu việt hơn MVO khi nguồn views có chất lượng không đồng đều — phù hợp với pipeline 4 nguồn của đề tài.

**Hình ảnh:**
- 🎨 Công thức μ_BL viết LaTeX rendered đẹp (có thể dùng MathJax/CodeCogs export PNG)
- 🎨 Sơ đồ Bayesian update: π (prior) + Views → μ_BL (posterior) — minh họa direction shift

---

## Slide 12 — XGBoost Ensemble + Walk-forward (75s)

**Heading:** Sinh ML views: XGBoost Ensemble + Walk-forward
**Body 1:** **Ensemble 5 mô hình** XGBoost per asset, đa dạng nhờ random seed (42–46), `subsample=0.8`, `colsample_bytree=0.7–0.9`. Walk-forward expanding window, **retrain mỗi 20 phiên** (~1 tháng), **embargo gap = 5 phiên** chống label leakage. Early stopping rounds=10, max_depth=4.

**Body 2:** **Confidence động** = clip(CONF_BASE + margin·k₁ − disagreement·k₂, 0.25, 0.70). Kết hợp với cải tiến **BL Deviation Alpha = 0.25** giới hạn lệch khỏi MVO 25%, balance alpha vs risk. Hit Rate XGBoost đạt 49% so với 39% rule-based — bắt được pattern phi tuyến mà indicators truyền thống bỏ lỡ.

**Hình ảnh:**
- 📷 **`xgboost_ensemble.png`** — sơ đồ 5 model parallel + ensemble averaging
- 📷 **`walk_forward_backtesting.png`** — minh họa expanding window + embargo gap
- Đường dẫn: `reports/BC2_De_Cuong_Luan_Van/figures/{xgboost_ensemble,walk_forward_backtesting}.png`
- Lưu ý: nếu cả 2 quá đầy, ưu tiên `walk_forward_backtesting.png`

---

## Slide 13 — ★ Tính mới #1: Combinatorial Stock Selection (75s)

**Heading:** Tính mới #1: Combinatorial Stock Selection
**Body 1:** **Bài toán:** chọn K=5 cổ phiếu VN30 đại diện → tối thiểu hóa Σᵢ minⱼ∈M d(i,j) với d = 1 − ρ. **Cách tiếp cận:** vét cạn toàn bộ C(30,5) = **142,506** tổ hợp + early-stopping pruning. Đảm bảo **global optimum tuyệt đối**, deterministic, không phụ thuộc seed, chạy ~1–3 giây.

**Body 2:** So với **PAM/K-Medoids** (heuristic local search, có thể kẹt local optimum, phụ thuộc khởi tạo) hay **K-Means** (chọn centroid ảo, không phải cổ phiếu thực). Reselect mỗi 60 phiên (~3 tháng) trong walk-forward. Chi phí tính toán không đáng kể so với chu kỳ rebalance → khả thi triển khai trên dữ liệu VN30 thật. Đây là điểm mới chưa có trong BC2.

**Hình ảnh:**
- 🎨 Sơ đồ minh họa: VN30 (30 chấm) → tổ hợp 5 chấm được chọn (highlight) — kiểu scatter 2D cluster
- 🎨 So sánh side-by-side: K-Medoids (local) vs Combinatorial (global) — 2 mini scatter plot
- Có thể tạo bằng matplotlib từ dữ liệu correlation VN30 thực rồi export

---

## Slide 14 — ★ Tính mới #2: Risk Management Layer (90s)

**Heading:** Tính mới #2: Risk Management Layer
**Body 1:** **(a) Regime Detection** dựa trên `vol_ratio = vol(20d)/vol(120d)` và `drawdown(60d)` → 3 chế độ: **Normal** / **Stress** (vol_ratio≥1.3 hoặc DD≤-10%) / **Crisis** (≥1.8 hoặc DD≤-20%). **(b) Defensive Views**: khi stress/crisis, chèn view "GOLD outperform stocks" và "MBBOND outperform stocks" với spread 5–10%, kéo posterior về tài sản trú ẩn.

**Body 2:** **(c) Volatility Dampener**: vol_ratio cao → giảm confidence ranking views → BL trở về gần equilibrium. **(d) Constrained MVO**: sàn defensive 25% (GOLD+MBBOND), trần equity 70%, risk aversion δ động (2.5 normal → 5.0 stress/crisis). **Tác động:** MDD ổn định mà không hi sinh alpha — equity curve mượt hơn rõ rệt. Cơ chế thích ứng theo regime — chưa thấy trong các nghiên cứu BL+ML trước cho thị trường mới nổi.

**Hình ảnh:**
- 🎨 Sơ đồ 4 cơ chế (a)→(d) dạng decision flow / 4-quadrant
- 🎨 Biểu đồ regime timeline 2020–2026: tô màu vùng Normal (xanh) / Stress (vàng) / Crisis (đỏ)
- 🎨 Hoặc equity curve có/không Risk Mgmt overlay (BEFORE vs AFTER)

---

## Slide 15 — Thiết kế thực nghiệm (75s)

**Heading:** Thiết kế thực nghiệm
**Body 1:** **Dữ liệu & Universe:** VN30 (30 cổ phiếu) làm universe chọn lọc. Mỗi chu kỳ reselect (60 phiên ≈ 3 tháng), Combinatorial Selection (Slide 13) chọn K=5 cổ phiếu đại diện — tập active thay đổi theo thời gian. Kết hợp 2 tài sản phòng thủ cố định: **GOLD** (vàng) + **MBBOND** (trái phiếu MB) — thành phần được Risk Management Layer (Slide 14) bảo vệ bằng weight floor.
→ Danh mục active mỗi kỳ: **K=5 stocks (động) + GOLD + MBBOND = 7 tài sản**.

**Body 2:** **Walk-forward backtest:**
• **IS** 01/2020 → 10/2023 (~950 phiên) · **OOS** 10/2023 → 03/2026 (~600 phiên)
• Rebalance mỗi 5 phiên (≈1 tuần) · Retrain XGBoost Ranker mỗi 20 phiên (~1 tháng) · Reselect K=5 mỗi 60 phiên (~3 tháng)
• **Baselines so sánh:** EW (1/N), MVO, BL+Rule-based, BL+ML(xgboost)
• **Metrics:** NAV, Ann. Return, Sharpe, Sortino, MDD, Calmar

**Hình ảnh:**
- 🎨 Timeline IS/OOS: thanh ngang 2020 → 2026 chia 2 vùng + markers reselect/retrain/rebalance
- 🎨 Sơ đồ: VN30(30) → Select K=5 → + GOLD + MBBOND → BL Optimizer → portfolio weights
- 🎨 Hoặc bảng "Active portfolio" thay đổi qua các reselect cycles

---

## ~~Slide 16~~ — ĐÃ BỎ

> **Lý do:** Nội dung 4 vòng cải tiến thuộc pipeline cũ (4 tài sản cố định). Pipeline mới (ranking mode) đã tích hợp tất cả cải tiến từ đầu → không cần trình bày quá trình iterative. Slide này nên **xóa trong Canva** (right-click → Delete page) để giữ 19 slides tổng.

---

## Slide 16 (mới, thay thế S17 cũ) — Kết quả Ranking Pipeline (90s)

**Heading:** Kết quả: BL+Ranking vs Baselines
**Body 1 (bảng metrics):**
| Strategy | NAV | Sharpe | MDD | Calmar |
|---|---|---|---|---|
| EW (1/N) | ___ | ___ | ___ | ___ |
| MVO | ___ | ___ | ___ | ___ |
| BL + Rule-based | ___ | ___ | ___ | ___ |
| BL + ML (xgboost) | ___ | ___ | ___ | ___ |
| **BL + Ranking (đề xuất)** | **___** | **___** | **___** | **___** |

*(Điền số liệu sau khi chạy lệnh bên dưới)*

**Body 2 (nhận xét):** *(Điền sau khi có kết quả)* Ranking pipeline kỳ vọng:
• Tận dụng dynamic stock selection → diversification tốt hơn
• Risk Mgmt Layer → MDD thấp hơn trong giai đoạn stress
• Relative views từ XGBoost Ranker → Sharpe cải thiện

**Hình ảnh:**
- 📷 **`reports/backtest_compare_views.png`** — NAV comparison chart (3 panels: rule_based / ml_xgboost / ranking)
- 🎨 Hoặc bảng metrics highlight BL+Ranking thắng trên 3 metrics chính
- **BẮT BUỘC chèn chart** để hội đồng thấy equity curve rõ ràng

---

### ⚡ Lệnh cần chạy để sinh kết quả mới nhất

```bash
# ── TRAIN phase (In-Sample: 2020-01 → 2023-10) ──
python run_compare_backtests.py \
  --phase train \
  --plot-path reports/BC2_De_Cuong_Luan_Van/figures/nav_comparison_train.png \
  --output-csv reports/BC2_De_Cuong_Luan_Van/figures/metrics_train.csv \
  --no-plot

# ── TEST phase (Out-of-Sample: 2023-10 → 2026-03) ──
python run_compare_backtests.py \
  --phase test \
  --plot-path reports/BC2_De_Cuong_Luan_Van/figures/nav_comparison_test.png \
  --output-csv reports/BC2_De_Cuong_Luan_Van/figures/metrics_test.csv \
  --no-plot
```

**Output sinh ra:**
- `nav_comparison_train.png` — equity curve IS (3 panels: rule_based / ml / ranking)
- `nav_comparison_test.png` — equity curve OOS
- `metrics_train.csv` — bảng đầy đủ {NAV, Ann.Return, Sharpe, Sortino, MDD, Calmar} × {EW, MVO, BL} × 3 scenarios
- `metrics_test.csv` — tương tự cho OOS
- Console output có bảng BASELINE vs RANKING side-by-side

**Lưu ý:** Đảm bảo đã train XGBoost model trước (cho ML scenario):
```bash
python gen_view/xgboost/model_train.py --method xgboost --train-phase train --validate
```

---

## Slide 18 — Đánh giá: Tính mới & Tính khả thi (60s)

**Heading:** Đánh giá đề tài
**Body 1 (col 1 — Tính mới):**
1. Triển khai BL với dynamic ML views *lần đầu* trên thị trường VN với phân tích đầy đủ IS+OOS.
2. Đề xuất Combinatorial Stock Selection thay vì heuristic K-Medoids — đảm bảo global optimum.
3. Risk Management Layer thích ứng theo regime — chưa thấy trong các nghiên cứu BL+ML cho thị trường mới nổi.
4. Cơ chế *BL Deviation Alpha* mới — kiểm soát lệch khỏi MVO.

**Body 2 (col 2 — Tính khả thi):** Đã có codebase open-source 100% Python, modular (`gen_view/`, `backtest.py`, `config.py`). Backtest hoàn chỉnh trên dữ liệu VN thật (vnstock + TCBS). 4 vòng cải tiến lặp ghi nhận cả thành công lẫn thất bại — minh chứng phương pháp nghiên cứu khoa học. Framework tái sử dụng được cho asset class khác (cryptocurrency, bất động sản, hàng hóa).

**Hình ảnh:**
- ⚪ Không cần ảnh chính (text-heavy 2-column); có thể thêm 2 icon đầu mỗi cột (💡 Tính mới / ✅ Tính khả thi)
- 🎨 Hoặc screenshot cấu trúc thư mục codebase (gen_view/ backtest.py config.py) ở góc col 2

---

## Slide 19 — Kế hoạch giai đoạn 2 (06/2026 – 12/2026) (60s)

**Heading:** Kế hoạch tiếp theo
**Card 1:** **LLM/RAG Integration** (06–08/2026) — User Interaction Agent + Explanation Agent với mô hình hỗ trợ tiếng Việt; RAG pipeline truy xuất tin tức tài chính; nudge hành vi theo Thaler & Sunstein (2008).
**Card 2:** **Mở rộng tài sản & Ranking mode** (08–09/2026) — kích hoạt full pipeline VN30 + Combinatorial Stock Selection + Risk Management Layer trong production-grade backtest. Cross-asset features.
**Card 3:** **UI/UX + Viết & bảo vệ luận văn** (09–12/2026) — web app React/Streamlit với chat tiếng Việt; user testing; viết và bảo vệ luận văn 12/2026. Chi tiết Gantt trong BC2.

**Hình ảnh:**
- 📷 **`gantt_chart.png`** — Gantt timeline 06/2026–12/2026 (đặt phía dưới 3 card hoặc làm full-width)
- Đường dẫn: `reports/BC2_De_Cuong_Luan_Van/figures/gantt_chart.png`
- 🎨 Hoặc 3 icon đầu mỗi card (🤖 LLM / 📈 Pipeline / 🖥️ UI)

---

## Slide 20 — Cảm ơn / Q&A (30s)

**Heading:** Cảm ơn Hội đồng
**Big1:** Cảm ơn
**Big2:** Q & A
**Body:** Trân trọng cảm ơn TS. Trương Thị Thái Minh, TS. Phạm An Vinh và quý thầy cô trong hội đồng đã dành thời gian phản biện. Sẵn sàng thảo luận.

**Hình ảnh:**
- 🎨 Logo ĐHBK + thông tin liên hệ (email/GitHub) ở góc dưới
- ⚪ Hoặc giữ ảnh placeholder template

---

## Tổng kết hình ảnh cần chuẩn bị

### Ảnh có sẵn — chỉ cần chèn (📷)
| Slide | File | Đường dẫn |
|---|---|---|
| S9 | `system_architecture.png` | `reports/BC2_De_Cuong_Luan_Van/figures/` |
| S12 | `xgboost_ensemble.png` + `walk_forward_backtesting.png` | `reports/BC2_De_Cuong_Luan_Van/figures/` |
| S13 | `combinatorial_selection.png` | `reports/BC2_De_Cuong_Luan_Van/figures/` |
| S16 (mới) | `nav_comparison_train.png` + `nav_comparison_test.png` | `reports/BC2_De_Cuong_Luan_Van/figures/` |
| S18 | `gantt_chart.png` | `reports/BC2_De_Cuong_Luan_Van/figures/` |

### Ảnh nên thiết kế thêm (🎨) — ưu tiên
1. **S14** — Regime timeline / equity curve before-after Risk Mgmt (★ ảnh quan trọng cho điểm mới #2)
2. **S10** — Pipeline 4 nguồn views → BL Engine
3. **S15** — Sơ đồ VN30 → K=5 → + GOLD + MBBOND → BL Optimizer
4. **S7** — VN-Index 2020–2026 highlight crash/bull periods

### Slide có thể giữ placeholder (⚪)
- S1 (cover), S2 (mục lục), S8 (4-card), S17 (đánh giá), S19 (cảm ơn)

### Slide đã bỏ
- ~~S16 cũ~~ (4 vòng cải tiến) → xóa trong Canva, tổng còn **19 slides**

---

## Workflow chèn ảnh trong Canva

1. Mở design: https://www.canva.com/design/DAHMFdeMr-o/edit
2. Với mỗi slide cần chèn ảnh: **Uploads** (sidebar trái) → **Upload files** → kéo file PNG/JPG
3. Drag ảnh đã upload vào vị trí placeholder (Canva tự fit). Hoặc **double-click** placeholder và chọn ảnh.
4. Resize/crop bằng các handle góc; căn giữa bằng smart guides.
5. Nếu placeholder cứng (ảnh giả lập đẹp của template) cản trở → **right-click → Delete**, sau đó kéo ảnh mới vào đúng vùng.
6. **Note**: Sau khi commit transaction qua MCP, tất cả text đã lưu permanent — chỉnh ảnh trực tiếp trên web UI **KHÔNG ảnh hưởng** đến text.

---

*File này được sinh từ `.qoder/specs/canva_thesis_defense_plan.md` — chỉnh sửa nội dung text trong Canva editor hoặc mở MCP transaction mới với `find_and_replace_text` để cập nhật từng câu.*
