# Guide: View Generation với ML/LLM (Current State + Roadmap)

Tài liệu này tách rõ 2 phần:
- Phần đang chạy được trong hệ thống hiện tại
- Phần roadmap nghiên cứu (chưa active trong backtest chính)

## 1. Current state (đang active)

### 1.1 Mục tiêu

Sinh views cho Black-Litterman theo cách tự động, có thể lậ lại và dễ so sánh.

### 1.2 Thành phần đang dùng

1. Rule-based views (`gen_view/view_generators.py`)
2. Relative views (`gen_view/view_generators.py`)
3. ML views từ XGBoost (`gen_view/xgboost/xgboost_core.py`)

Cấu hình tập trung tại:
- `config.py`: tham số toàn dự án (BL params, view mode mặc định, combined weights, ML defaults)
- `gen_view/xgboost/config.py`: tham số riêng module XGBoost (hyperparams, feature periods, confidence heuristic)

### 1.3 Luồng ML XGBoost

```text
Historical prices
-> feature engineering
-> forward-return labels
-> train per-asset XGBoost
-> save cache (.pkl)
-> predict at rebalance
-> convert predictions to BL views
```

Train command:

```bash
python gen_view/xgboost/model_train.py --method xgboost --train-phase train --validate
```

Run ML backtest:

```bash
python backtest.py --phase test --view-mode ml --ml-model-type xgboost
```

### 1.4 Vì sao XGBoost là lựa chọn hiện tại

- Huấn luyện nhanh, dễ debug
- Chạy tốt với tabular features
- Phù hợp volume dữ liệu hiện có
- Đã tích hợp sẵn vào backtest CLI

## 2. Roadmap (không active trong backtest production)

### 2.1 Deep Learning (LSTM/Transformer)

Trạng thái:
- Chưa có pipeline production hoàn chỉnh trong `backtest.py`
- Có thể mở rộng trong nghiên cứu sau nếu cần modeling sequence sau hơn

Rui ro chính:
- Cần thêm dữ liệu và tuning
- Khó giải thích hơn tree-based models

### 2.2 LLM-based views

Trạng thái:
- Logic LLM trong repo ở dạng ý tưởng/thử nghiệm, chưa phải luồng chính
- Chưa nên sử dụng để kết luận benchmark chính thức

Rui ro chính:
- Chi phí API
- Latency
- Reproducibility

## 3. Kháy ngị cho luận văn

1. Báo cáo kết quả chính dựa trên 4 modes đang hỗ trợ trong `backtest.py`:
   - `rule_based`, `relative`, `ml`, `combined`

2. Trình bày LSTM/LLM dưới dạng hướng phát triển:
   - Nếu có demo riêng thì tách bàng appendix/prototype
   - Không gộm chung với kết quả production nếu chưa active

3. Đảm bảo reproducibility:
   - Ghi rõ train phase
   - Ghi rõ tập assets
   - Ghi rõ model cache và ngày train
   - Ghi rõ version `config.py` và `gen_view/xgboost/config.py` đang dùng

## 4. Checklist thực thi

1. Cập nhật dữ liệu và assets config
2. Huấn luyện XGBoost
3. Chạy backtest theo từng view mode
4. Chạy script compare
5. Lưu report vào `reports/`

```bash
python gen_view/xgboost/model_train.py --method xgboost --train-phase train --validate
python backtest.py --phase test --view-mode rule_based --no-plot
python backtest.py --phase test --view-mode ml --ml-model-type xgboost --no-plot
python run_compare_backtests.py --phase test --no-plot
```
