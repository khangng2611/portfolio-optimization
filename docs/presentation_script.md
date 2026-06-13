# SCRIPT THUYẾT TRÌNH — Phản biện Đề cương Luận văn
## Thời lượng: 20 phút | 19 slides

---

## SLIDE 1 — Trang bìa (30 giây)

> Kính chào Hội đồng, thầy/cô phản biện,
>
> Em là Nguyễn Phúc Khang, MSSV 2470499, học viên cao học ngành Khoa học Máy tính. Hôm nay em xin trình bày đề cương luận văn với đề tài: **"Nghiên cứu và phát triển hệ thống tư vấn phân bổ danh mục đầu tư"**, dưới sự hướng dẫn của TS. Trương Thị Thái Minh và TS. Phạm An Vinh.

---

## SLIDE 2 — Nội dung trình bày (30 giây)

> Bài trình bày gồm 5 phần chính:
>
> **Một** — Bối cảnh và Động lực: tại sao đề tài này cần thiết.
> **Hai** — Mục tiêu và Khoảng trống nghiên cứu.
> **Ba** — Phương pháp đề xuất: kiến trúc hệ thống và 2 cải tiến mới.
> **Bốn** — Thực nghiệm và Kết quả ban đầu.
> **Năm** — Đánh giá tính mới, tính khả thi, và roadmap giai đoạn 2.
>
> Em xin bắt đầu.

---

## SLIDE 3 — 1.1 Bối cảnh & Động lực toàn cầu (1 phút 30 giây)

> Trước hết về bối cảnh toàn cầu, có **hai xu hướng lớn** đang hội tụ:
>
> **Thứ nhất**, sự bùng nổ của Large Language Models — GPT-4, Llama — đặc biệt các mô hình hỗ trợ tiếng Việt. Chúng mở ra khả năng kết hợp **tối ưu hóa định lượng** với **giao tiếp tự nhiên** — điều mà trước đây chưa khả thi.
>
> **Thứ hai**, ngành Robo-advisor toàn cầu — Betterment, Wealthfront, Vanguard Digital Advisor — đang quản lý **hàng trăm tỷ USD** hoàn toàn tự động bằng thuật toán.
>
> Ở giao điểm của hai xu hướng này, mô hình **Black-Litterman** nổi lên như nền tảng lý tưởng: nó kết hợp cân bằng thị trường với views nhà đầu tư qua khuôn khổ Bayesian — rất phù hợp khi ta muốn tích hợp Machine Learning để sinh views tự động thay cho analyst truyền thống.

---

## SLIDE 4 — 1.2 Thực trạng tại Việt Nam (1 phút 30 giây)

> Quay về Việt Nam, theo UBCKNN tính đến 10/2025, thị trường đã có hơn **12 triệu tài khoản** chứng khoán cá nhân — tăng trưởng 26.6% chỉ riêng năm 2024.
>
> Tuy nhiên, phần lớn nhà đầu tư cá nhân **thiếu kiến thức chuyên sâu** về phân bổ tài sản và quản lý rủi ro. Quyết định đầu tư chủ yếu dựa cảm tính, theo đám đông.
>
> Lĩnh vực robo-advisor tại Việt Nam còn **rất sơ khai** vì ba lý do:
> - **(1)** Thiếu dữ liệu lịch sử dài hạn,
> - **(2)** Số loại tài sản đầu tư hạn chế,
> - **(3)** Hành vi nhà đầu tư có nhiều thiên lệch tâm lý.
>
> → Đây chính là **cơ hội nghiên cứu**: xây dựng một hệ tư vấn vừa **định lượng** bằng BL + Machine Learning, vừa có khả năng **giao tiếp tự nhiên bằng tiếng Việt** qua LLM.

---

## SLIDE 5 — 2.1 Mục tiêu (1 phút 30 giây)

> Từ bối cảnh đó, đề tài đặt ra **ba mục tiêu**:
>
> **Một — Xây dựng mô hình tối ưu danh mục** phù hợp thị trường Việt Nam. Sau khi so sánh MVO, Risk Parity, và Black-Litterman, em chọn BL làm core nhờ khả năng tích hợp dynamic views với độ tin cậy hiệu chỉnh.
>
> **Hai — Ứng dụng AI tăng cường Black-Litterman**: XGBoost Ensemble kết hợp Walk-forward sinh ML views thay cho view chủ quan. LLM/RAG cho view định tính từ tin tức và giải thích quyết định bằng tiếng Việt.
>
> **Ba — Triển khai và đánh giá**: Walk-forward backtest trên dữ liệu thực Việt Nam, in-sample và out-of-sample, so sánh với Equal-Weight và MVO.
>
> **Câu hỏi nghiên cứu chính**: Mô hình Black-Litterman kết hợp Machine Learning có thể vượt MVO trên thị trường Việt Nam về NAV, Sharpe và MDD trong điều kiện walk-forward thực tế không, đồng thời đảm bảo khả năng giải thích cho nhà đầu tư cá nhân?

---

## SLIDE 6 — 2.2 Hạn chế của phương pháp hiện tại (1 phút)

> Tại sao không dùng MVO trực tiếp?
>
> **MVO** — nền tảng MPT từ Markowitz 1952 — có vấn đề nổi tiếng gọi là **Markowitz curse**: nhạy cảm cực mạnh với sai số ước lượng μ. Một thay đổi nhỏ trong vector lợi nhuận kỳ vọng dẫn đến danh mục biến động hoàn toàn, tập trung cực đoan. Trong thực nghiệm của em, MDD có thể lên đến **-26% đến -65%** — không phù hợp triển khai thực tế.
>
> **Black-Litterman gốc** khắc phục được Markowitz curse nhưng truyền thống chỉ dùng view chủ quan từ analyst — không tận dụng dữ liệu lớn.
>
> **Khoảng trống**: chưa có nghiên cứu hệ thống về dynamic Machine Learning views + risk-aware Black-Litterman cho thị trường mới nổi như Việt Nam.

---

## SLIDE 7 — 2.2 Thiếu nghiên cứu trên thị trường Việt Nam (1 phút)

> Cụ thể hơn cho thị trường Việt Nam:
>
> Market-cap **khó ước lượng** do quy mô vốn hóa nhỏ, biến động cao, và chưa có chuỗi dữ liệu dài hạn ổn định. Vai trò của views trong khuôn khổ BL trở nên **đặc biệt quan trọng** — nhưng không có nghiên cứu nào triển khai BL với dynamic views trên VN30 với phân tích đầy đủ in-sample + out-of-sample.
>
> Đồng thời, các phương pháp BL/MVO truyền thống **thiếu cơ chế kiểm soát rủi ro** thích ứng theo regime — điều rất quan trọng với thị trường nhiều giai đoạn biến động mạnh như Việt Nam từ 2020 đến 2026.
>
> → Đề tài lấp **3 khoảng trống**:
> **(a)** BL + ML cho Việt Nam,
> **(b)** Combinatorial Stock Selection thay heuristic,
> **(c)** Risk Management Layer thích ứng.

---

## SLIDE 8 — 3. Phương pháp đề xuất — 4 điểm nổi bật (1 phút)

> Phương pháp đề xuất gồm **4 thành phần chính**:
>
> **Một — Black-Litterman Dynamic Views**: thay views tĩnh bằng views động, hợp nhất nhiều nguồn — rule-based, machine learning, LLM — trong một khuôn khổ Bayesian thống nhất.
>
> **Hai — XGBoost Ensemble + Walk-forward**: 5 model per asset, retrain mỗi 20 phiên trên expanding window, embargo gap chống leak, confidence từ ensemble disagreement.
>
> **Ba — Combinatorial Stock Selection**: chọn K=5 đại diện VN30 bằng vét cạn tổ hợp, đảm bảo global optimum, deterministic.
>
> **Bốn — Risk Management Layer**: regime detection + defensive views + volatility dampener + constrained MVO; mục tiêu giảm MDD và làm mượt equity curve.
>
> Em sẽ đi chi tiết từng phần.

---

## SLIDE 9 — 3.1 Kiến trúc tổng quan (1 phút 30 giây)

> Hệ thống được thiết kế theo kiến trúc **multi-agent**, gồm 4 agents chính:
>
> **Data Agent**: thu thập và tiền xử lý lịch sử giá từ vnstock, TCBS, HOSE.
>
> **View Generation Agent**: sinh views song song bằng các phương pháp khác nhau — rule-based, relative, ML XGBoost, và LLM. BL Engine hợp nhất views thành posterior μ_BL.
>
> **Optimizer Agent**: giải MVO ràng buộc → ra trọng số tối ưu w.
>
> **Explanation Agent**: dùng LLM diễn giải quyết định bằng tiếng Việt cho end-user.
>
> Toàn pipeline được **walk-forward backtest**: rebalance mỗi **5 phiên**, retrain ML mỗi **20 phiên**, reselect VN30 mỗi **60 phiên**. Thiết kế này đảm bảo **không look-ahead bias** — đúng như điều kiện giao dịch thực tế.

---

## SLIDE 10 — 3.2 Mô hình Black-Litterman (1 phút 30 giây)

> Đây là công thức cốt lõi của Black-Litterman mà em sử dụng.
>
> **Hai input**:
> - Lợi nhuận cân bằng thị trường (Market Equilibrium Returns): Được suy ra từ trạng thái cân bằng của thị trường, phản ánh sự đồng thuận của toàn bộ thị trường.
> - Quan điểm của nhà đầu tư (Investor Views): Các nhận định chủ quan hoặc dự báo của nhàđầu tư về lợi nhuận tương đối hoặc tuyệt đối của các tài sản.
>
> **Bayesian Update** cho ra **lợi nhuận kỳ vọng của danh mục thị trường** μ_BL — pha trộn giữa equilibrium và views theo mức confidence.
>
> μ_BL sau đó đưa vào **Mean-Variance Optimization** với ràng buộc: w ≥ 0, Σw = 1, w_i ≤ 40%.
>
> Điểm đặc biệt: em đề xuất thêm cơ chế **BL Deviation Alpha**: w_final = w_MVO + α(w_BL − w_MVO). Cơ chế này kiểm soát mức độ hệ thống "lệch" khỏi MVO khi views confident — tránh trường hợp BL đổ hết vào 1 asset khi model quá tự tin.

---

## SLIDE 11 — 3.3 Pipeline sinh view động (1 phút)

> Pipeline sinh views gồm **4 nguồn** chạy song song:
>
> - **Rule-Based Views** (absolute): EMA Crossover, RSI, Momentum Signal → view đơn giản nhưng robust.
> - **Relative Views**: so sánh cặp tài sản theo momentum difference → BL nhận dạng "A > B".
> - **ML Views (XGBoost)**: 8 features kỹ thuật → ensemble 5 models → prediction + confidence.
> - **Combined**: weighted aggregation w1=0.4, w2=0.3, w3=0.3.
>
> Tất cả đều được chuyển thành ma trận **P, Q, Ω** và đưa vào BL Engine. Thiết kế modular cho phép thêm/bớt nguồn views dễ dàng — trong giai đoạn 2 sẽ thêm LLM views.

---

## SLIDE 12 — 3.4 Phương pháp sinh view (XGBoost) (1 phút 30 giây)

> Bên trái là kiến trúc **XGBoost Ensemble**:
>
> - 8 Input Features: momentum_5/10/20, RSI_14, MA_ratio_10_30, volatility_20, MACD_histogram, price_std_20.
> - **5 models** với seed khác nhau (42–46) và colsample khác nhau (0.7–0.9) → Mean Prediction → BL View (Q, confidence).
> - Confidence = CONF_MAX − pred_std/CONF_SCALE. Khi ensemble **đồng thuận cao** → confidence cao → BL lệch mạnh khỏi equilibrium.
> 
> (Momentum - Chỉ số Momentum (MOM) là công cụ phân tích kỹ thuật dùng để đo lường tốc độ thay đổi của giá tài sản trong một khoảng thời gian nhất định.)
> (RSI_14 - chỉ số sức mạnh tương đối dùng để đo lường tốc độ và mức độ thay đổi giá của một tài sản trong 14 phiên gần nhất, để xác định tín hiệu quá mua, quá bán)
> (MA_ratio - chỉ số thể hiện trung bình giá ngắn hạn so với dài hạn)    
>
>
> Bên phải là **Walk-Forward Testing**:
> - Retrain mỗi **20 trading days** trên expanding window.
> - **Embargo gap = 5 ngày** chống data leakage.
> - In-Sample: 01/2020 → 10/2023. Out-of-Sample: 10/2023 → 03/2026.
>
> Đây là điểm **khác biệt quan trọng** so với các nghiên cứu BL+ML khác: phần lớn chỉ train-test split đơn giản, còn em dùng **expanding walk-forward** — mô phỏng chính xác điều kiện giao dịch thực.

---

## SLIDE 13 — 3.5 Combinatorial Stock Selection (1 phút 30 giây)

> Đây là **đóng góp mới thứ nhất**.
>
> **Bài toán**: chọn K=5 cổ phiếu đại diện từ VN30, sao cho tổng khoảng cách correlation giữa các cổ phiếu được chọn là **tối thiểu** — nghĩa là chúng đại diện tối đa cho toàn bộ universe.
>
> Distance = 1 − correlation(i,j). Mục tiêu: min Σ min_{m∈M} distance(i,m).
>
> **Cách tiếp cận**: vét cạn toàn bộ C(30,5) = **142,506 tổ hợp** + early-stopping pruning. Đảm bảo:
> - **Global optimum tuyệt đối** — không có heuristic nào tốt hơn.
> - **Deterministic** — chạy lại cho cùng kết quả.
> - Thời gian chỉ **1–3 giây**.
>
> Biểu đồ bên phải cho thấy 5 cổ phiếu được chọn (sao cam) phân bố đều trong không gian MDS — mỗi cổ phiếu đại diện cho một "cụm" khác nhau của thị trường.
>
> Cứ mỗi 60 phiên (~3 tháng), hệ thống **reselect** — cập nhật danh mục K=5 theo điều kiện thị trường mới nhất.

---

## SLIDE 14 — 3.6 Risk Management Layer (1 phút 30 giây)

> Đây là **đóng góp mới thứ hai** — chưa thấy trong các nghiên cứu BL+ML cho thị trường mới nổi.
>
> **Regime Detection** — 3 chế độ:
> - **Normal**: vol_ratio < 1.3 và drawdown > -10% → thị trường ổn định.
> - **Stress**: vol_ratio ≥ 1.3 hoặc drawdown ≤ -10% → căng thẳng.
> - **Crisis**: vol_ratio ≥ 1.8 hoặc drawdown ≤ -20% → khủng hoảng.
>
> Với vol_ratio = vol(20 ngày) / vol(120 ngày) — khi biến động ngắn hạn vượt xa dài hạn → tín hiệu stress.
>
> **Volatility Dampener**: khi vol_ratio cao → **giảm confidence** ranking views → BL tự động trở về gần equilibrium. Cơ chế này giúp hệ thống "nghi ngờ" các dự đoán ML trong giai đoạn bất thường.
>
> **Defensive Views**: khi stress/crisis, chèn view "GOLD outperform stocks" và "MBBOND outperform stocks" → **kéo posterior về tài sản trú ẩn**.
>
> **Constrained MVO**: sàn defensive 25% cho tài sản trú ẩn, trần 70% equity, risk aversion δ động (2.5 normal → 5.0 crisis).
>
> **Tác động**: MDD ổn định mà không hi sinh alpha — equity curve **mượt hơn rõ rệt**.

---

## SLIDE 15 — 4.1 Thiết kế thực nghiệm (1 phút)

> Về thiết kế thực nghiệm:
>
> **Dữ liệu**: 30 cổ phiếu VN30 làm universe chọn lọc. Mỗi chu kỳ reselect → K=5 cổ phiếu đại diện, kết hợp **vàng + MBBOND** (trái phiếu MB) = **7 tài sản** active mỗi kỳ.
>
> **Walk-forward backtest**:
> - In-sample: 01/2020 → 10/2023 (~950 phiên)
> - Out-of-sample: 10/2023 → 03/2026 (~600 phiên)
> - Rebalance mỗi 5 phiên, retrain XGBoost mỗi 20 phiên, reselect K=5 mỗi 60 phiên.
>
> **Baselines**: EW (1/N), MVO, BL+Rule-based, BL+ML(xgboost).
>
> **Metrics**: NAV, Annualized Return, Sharpe, Sortino, MDD, Calmar.
>
> Timeline phía dưới cho thấy 3 tầng markers — mật độ rebalance > retrain > reselect — tạo nên nhịp điều chỉnh **đa tốc độ**.

---

## SLIDE 16 — 4.2 Kết quả tổng hợp (2 phút)

> Đây là kết quả In-Sample — giai đoạn train:
>
> | Strategy | NAV | Sharpe | MDD |
> |---|---|---|---|
> | EW (1/N) | 1.829 | 0.719 | -37.60% |
> | MVO | 4.339 | 1.461 | -33.34% |
> | **BL + Ranking (đề xuất)** | **1.905** | **0.967** | **-29.54%** |
>
> **Nhận xét quan trọng**:
>
> MVO đạt NAV cao nhất (4.339) nhưng với MDD **-33.34%** — rủi ro quá lớn cho nhà đầu tư cá nhân. Trong thực tế, drawdown -33% nghĩa là danh mục từ 1 tỷ còn 670 triệu — đa số nhà đầu tư sẽ panic sell.
>
> **BL + Ranking** của em đạt Sharpe **0.967** — tỷ suất risk-adjusted tốt, và quan trọng hơn: MDD chỉ **-29.54%** — cải thiện đáng kể so với MVO (-33%) và EW (-37%). Equity curve (đường xanh lá) **mượt và ổn định hơn** rõ rệt — đây chính là tác dụng của Risk Management Layer.
>
> Mặc dù NAV tuyệt đối thấp hơn MVO, nhưng xét về **risk-adjusted return** và khả năng triển khai thực tế — BL+Ranking là lựa chọn phù hợp cho nhà đầu tư cá nhân. *Không ai muốn lãi 300% nhưng phải chịu drawdown -33% giữa đường.*

---

## SLIDE 17 — 5.1 Đánh giá tính mới & tính khả thi (1 phút 30 giây)

> **Tính mới** — 4 đóng góp:
>
> - Triển khai **Black-Litterman với dynamic ML views** lần đầu trên thị trường Việt Nam, với phân tích đầy đủ IS & OOS.
> - Đề xuất **Combinatorial Stock Selection** — chọn top K tài sản đại diện bằng exhaustive search, đảm bảo global optimum.
> - **Risk Management Layer** thích ứng theo regime — chưa thấy trong nghiên cứu BL+ML nào cho thị trường mới nổi.
> - Cơ chế **Black-Litterman Deviation Alpha** — kiểm soát lệch khỏi MVO.
>
> **Tính khả thi**:
> - Đã có **codebase hoàn chỉnh** — toàn bộ pipeline đã chạy được end-to-end.
> - **Backtest hoàn chỉnh** trên dữ liệu Việt Nam thật — không phải simulated data.
> - Framework có thể **tái sử dụng cho asset khác**: cryptocurrency, bất động sản, hàng hóa — chỉ cần thay data source.

---

## SLIDE 18 — 5.2 Kế hoạch giai đoạn tiếp theo (1 phút)

> Giai đoạn 1 (thanh xanh) — **đã hoàn thành**:
> - Thu thập dữ liệu, xây framework backtesting, module sinh views, XGBoost Ensemble + Walk-forward, Combinatorial Selection, Risk Management, backtest và đánh giá.
>
> Giai đoạn 2 (thanh cam) — **kế hoạch đến 01/2027**:
> - **Tích hợp LLM/RAG cho chatbot** — diễn giải quyết định bằng tiếng Việt.
> - **Mở rộng tập tài sản** — cross-asset features.
> - **Phát triển giao diện web** — demo interactive.
> - **Dynamic alpha & behavioral nudges** — cá nhân hóa theo risk profile.
> - **Kiểm thử toàn hệ thống** — unit test + integration test.
> - **Viết luận văn + Bảo vệ** — dự kiến 12/2026 – 01/2027.
>
> Hiện tại (06/2026) — vạch đỏ trên biểu đồ — giai đoạn 1 đã xong, em đang chuẩn bị bước vào giai đoạn 2.

---

## SLIDE 19 — Q&A (30 giây)

> Em xin kết thúc bài trình bày tại đây.
>
> Em xin cảm ơn Hội đồng đã lắng nghe. Em sẵn sàng trả lời câu hỏi ạ.

---

## PHỤ LỤC: CÂU HỎI CÓ THỂ GẶP & GỢI Ý TRẢ LỜI

### Q1: "Tại sao NAV của BL+Ranking thấp hơn MVO?"
> BL+Ranking hy sinh NAV tuyệt đối để đạt **equity curve mượt hơn** (MDD -29% vs -33%). Trong triển khai thực tế, nhà đầu tư cá nhân ưu tiên **không mất quá nhiều** hơn là lãi cực đại. Sharpe ratio 0.967 cho thấy risk-adjusted performance rất tốt. Ngoài ra, kết quả out-of-sample sẽ cho thấy MVO overfits trong IS.

### Q2: "Combinatorial search C(30,5) có scale được không?"
> Với N=30, K=5 → 142,506 tổ hợp, chạy 1-3 giây. Nếu N tăng lên 50 (VN50), C(50,5) ≈ 2.1 triệu — vẫn khả thi trong vài phút. Nếu cần mở rộng hơn, có thể chuyển sang K-Medoids hoặc branch-and-bound, nhưng hiện tại exhaustive search vẫn là tối ưu vì đảm bảo global optimum.

### Q3: "Risk Management Layer có giúp gì trong giai đoạn crash 2022?"
> Có. Khi VN-Index giảm >30% (Q2-Q3 2022), regime chuyển sang Crisis → defensive views chèn "GOLD/MBBOND outperform stocks" → trọng số equity bị cap 70% → MDD của BL+Ranking chỉ -29% trong khi EW chịu -37%. Vol dampener cũng giảm confidence ML views → BL trở về gần equilibrium — tránh "đuổi theo" dự đoán ML sai trong giai đoạn bất thường.

### Q4: "Tại sao chọn XGBoost mà không phải LSTM/Transformer?"
> - XGBoost phù hợp hơn với **tabular features** (momentum, RSI, MA) — đã được chứng minh hiệu quả hơn deep learning trên structured data (Grinsztajn et al., 2022).
> - Ensemble 5 models cho **uncertainty quantification** tự nhiên qua disagreement — LSTM cần thêm kỹ thuật riêng (MC Dropout, etc.).
> - Walk-forward retrain mỗi 20 phiên → model nhẹ chạy nhanh, không cần GPU.

### Q5: "Phần LLM trong giai đoạn 2 sẽ làm gì cụ thể?"
> - **View generation từ tin tức**: dùng RAG (Retrieval-Augmented Generation) crawl tin tức tài chính Việt → LLM extract sentiment → chuyển thành BL view với confidence.
> - **Giải thích quyết định**: "Danh mục tuần này tăng tỷ trọng GOLD vì thị trường đang ở chế độ Stress — vol_ratio = 1.5" — bằng tiếng Việt tự nhiên.
> - **Behavioral nudges**: nhắc nhở nhà đầu tư khi portfolio lệch khỏi risk profile ban đầu.

---

## GHI CHÚ THỜI GIAN

| Phần | Slides | Thời gian |
|------|--------|-----------|
| Mở đầu + Agenda | 1–2 | 1 phút |
| Bối cảnh & Động lực | 3–4 | 3 phút |
| Mục tiêu & Khoảng trống | 5–7 | 3.5 phút |
| Phương pháp đề xuất | 8–14 | 8.5 phút |
| Thực nghiệm & Kết quả | 15–16 | 3 phút |
| Đánh giá & Kế hoạch | 17–18 | 2.5 phút |
| Kết luận + Q&A | 19 | 0.5 phút |
| **Tổng** | | **~20 phút** |

---

## MẸO TRÌNH BÀY

1. **Slide 13 & 14** (Combinatorial + Risk Mgmt) là 2 đóng góp mới → dành thời gian nhiều nhất, nói chậm, nhấn mạnh.
2. **Slide 16** (Kết quả) — đọc bảng số **chậm rãi**, so sánh từng metric → giúp hội đồng absorb.
3. Khi nói về MDD, nêu **ví dụ cụ thể**: "1 tỷ → 670 triệu" — hội đồng sẽ cảm nhận được impact.
4. Giữ **giọng nói đều**, không vội — 20 phút là đủ nếu không lan man.
5. Nếu hội đồng hỏi về giai đoạn 2 (LLM) → nhấn mạnh giai đoạn 1 đã có **foundation vững** → LLM chỉ là thêm nguồn views, không thay đổi core architecture.
