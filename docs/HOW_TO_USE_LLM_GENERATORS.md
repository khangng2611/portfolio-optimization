# Hướng Dẫn Sử Dụng LLM/ML View Generators

## Tổng quan

File `llm_view_generators.py` cung cấp 3 phương pháp nâng cao để tạo views động cho Black-Litterman:

1. **Traditional ML** (XGBoost) - Học có giám sát
2. **Deep Learning** (LSTM) - Mô hình hóa chuỗi thời gian
3. **LLM-based** (GPT-4, Claude) - Kết hợp dữ liệu định lượng + định tính

## Cài đặt Dependencies

```bash
# Cài đặt tất cả dependencies
pip install -r requirements.txt

# Hoặc cài đặt từng phần:
# Traditional ML
pip install scikit-learn xgboost

# Deep Learning
pip install torch

# LLM
pip install openai anthropic
```

## Option 1: Traditional ML (XGBoost)

### Ưu điểm
- Huấn luyện nhanh (vài giây)
- Dễ hiểu, có thể xem feature importance
- Hoạt động tốt với dữ liệu ít
- Không cần GPU

### Cách sử dụng

```python
from llm_view_generators import TraditionalMLViewGenerator
import pandas as pd

# 1. Khởi tạo generator
ml_gen = TraditionalMLViewGenerator(
    model_type="xgboost",
    feature_window=20,           # 20 ngày để tính features
    prediction_horizon=5,        # dự đoán 5 ngày tới
)

# 2. Load dữ liệu train (2020-2023)
train_prices = pd.read_csv("datasets/stocks/train/E1VFVN30_train.csv")
# ... load các assets khác và merge vào DataFrame

# 3. Huấn luyện model
ml_gen.train(train_prices, verbose=True)

# 4. Lưu model
ml_gen.save(".cache/xgboost_models.pkl")

# 5. Tạo views cho dữ liệu mới
test_prices = pd.read_csv("datasets/stocks/test/E1VFVN30_test.csv")
views = ml_gen.generate_views(test_prices)

# 6. Kết quả
for view in views:
    print(f"{view['name']}: {view['view_return_annual']:.2%}")
```

### Tùy chỉnh tham số

```python
# XGBoost với tham số tùy chỉnh
ml_gen = TraditionalMLViewGenerator(
    model_type="xgboost",
    model_params={
        "n_estimators": 100,
        "max_depth": 6,
        "learning_rate": 0.05,    # learning rate thấp hơn
        "subsample": 0.8,         # sample 80% data mỗi tree
    }
)
```

## Option 2: Deep Learning (LSTM)

### Ưu điểm
- Bắt được mô hình phức tạp trong chuỗi thời gian
- Không cần feature engineering thủ công
- State-of-the-art cho time series
- Có thể học các pattern dài hạn

### Nhược điểm
- Cần nhiều dữ liệu hơn (1000+ samples)
- Huấn luyện chậm hơn (vài phút)
- Khó giải thích (black-box)
- Dễ overfit nếu không cẩn thận

### Cách sử dụng

```python
from llm_view_generators import LSTMViewGenerator

# 1. Khởi tạo LSTM generator
lstm_gen = LSTMViewGenerator(
    sequence_length=60,       # nhìn lại 60 ngày
    prediction_horizon=5,     # dự đoán 5 ngày tới
    hidden_size=64,          # kích thước hidden layer
    num_layers=2,            # 2 lớp LSTM
    dropout=0.2,             # dropout để tránh overfit
    epochs=50,               # số epochs huấn luyện
    batch_size=32,
    device="cpu",            # hoặc "cuda" nếu có GPU
)

# 2. Huấn luyện (mất vài phút)
lstm_gen.train(train_prices, verbose=True)

# 3. Lưu model
lstm_gen.save(".cache/lstm_models.pt")

# 4. Load model đã train
lstm_gen.load(".cache/lstm_models.pt")

# 5. Tạo views
views = lstm_gen.generate_views(test_prices)
```

### Tips để cải thiện LSTM

1. **Tăng dữ liệu**: LSTM cần nhiều data, nên train trên toàn bộ 2020-2023
2. **Điều chỉnh sequence_length**: Thử 30, 60, 90 ngày
3. **Early stopping**: Model tự động dừng khi validation loss không giảm
4. **GPU**: Nếu có GPU, set `device="cuda"` để train nhanh hơn 10x

```python
# Kiểm tra GPU
import torch
if torch.cuda.is_available():
    print(f"GPU available: {torch.cuda.get_device_name(0)}")
    lstm_gen = LSTMViewGenerator(device="cuda")
```

## Option 3: LLM-based (GPT-4 / Claude)

### Ưu điểm
- Kết hợp định lượng (giá, indicators) + định tính (tin tức)
- Có thể hiểu ngữ cảnh, sự kiện, sentiment
- Không cần huấn luyện (zero-shot)
- Giải thích được lý do (reasoning)

### Nhược điểm
- Chi phí API cao (~$0.03-0.10 mỗi view)
- Latency cao (2-5 giây mỗi call)
- Non-deterministic (kết quả không cố định)
- Cần internet connection

### Cách sử dụng

```python
from llm_view_generators import LLMViewGenerator
import os

# 1. Set API key (chọn 1 trong 2)
os.environ["OPENAI_API_KEY"] = "sk-..."
# hoặc
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..."

# 2. Khởi tạo LLM generator
llm_gen = LLMViewGenerator(
    llm_provider="openai",           # hoặc "anthropic"
    model_name="gpt-4",              # hoặc "gpt-3.5-turbo", "claude-3-sonnet"
    temperature=0.3,                 # thấp = ổn định, cao = sáng tạo
    enable_caching=True,             # cache để giảm cost
    cache_ttl_hours=24,              # cache 24h
    enable_news=True,                # bật crawl tin tức
    news_lookback_days=7,            # tin tức 7 ngày gần nhất
)

# 3. Tạo views (không cần train!)
views = llm_gen.generate_views(test_prices, verbose=True)

# 4. Xem chi phí
cost_summary = llm_gen.get_cost_summary()
print(f"Total cost: ${cost_summary['total_cost_usd']:.4f}")
print(f"Avg per call: ${cost_summary['avg_cost_per_call']:.4f}")
```

### So sánh GPT-4 vs Claude vs GPT-3.5-turbo

| Model | Chi phí/call | Chất lượng | Tốc độ |
|-------|-------------|-----------|--------|
| GPT-4 | $0.03-0.05 | Cao nhất | Chậm (3-5s) |
| GPT-3.5-turbo | $0.002-0.005 | Tốt | Nhanh (1-2s) |
| Claude-3-Sonnet | $0.01-0.02 | Cao | Trung bình (2-3s) |

**Khuyến nghị**:
- **Experimentation**: Dùng GPT-3.5-turbo (rẻ nhất)
- **Production**: Dùng GPT-4 hoặc Claude-3-Sonnet
- **Budget-constrained**: Chỉ dùng LLM cho quan trọng assets (VD: chỉ E1VFVN30)

### Giảm chi phí API

```python
# 1. Enable caching (quan trọng!)
llm_gen = LLMViewGenerator(
    enable_caching=True,
    cache_ttl_hours=24,  # cache 1 ngày
)

# 2. Tắt news nếu không cần
llm_gen = LLMViewGenerator(
    enable_news=False,  # giảm tokens -> giảm cost
)

# 3. Dùng mô hình rẻ hơn
llm_gen = LLMViewGenerator(
    model_name="gpt-3.5-turbo",  # rẻ hơn GPT-4 gấp 10x
)

# 4. Giảm max_tokens
llm_gen = LLMViewGenerator(
    max_tokens=300,  # giảm từ 500 xuống 300
)
```

### Ước tính chi phí

Giả sử:
- 4 assets
- Rebalance 5 lần/ngày
- 252 ngày trading/năm
- Chi phí $0.035/view

**Tổng chi phí hàng năm**: 4 × 5 × 252 × 0.035 = **$176.4**

Với caching (giảm 75%): **$44.1**

## Kết hợp 3 phương pháp (Ensemble)

Kết hợp views từ cả 3 phương pháp để tận dụng ưu điểm của từng cái:

```python
from llm_view_generators import (
    TraditionalMLViewGenerator,
    LSTMViewGenerator,
    LLMViewGenerator,
    combine_multi_source_views,
)

# 1. Train/load các models
ml_gen = TraditionalMLViewGenerator()
ml_gen.load(".cache/xgboost_models.pkl")

lstm_gen = LSTMViewGenerator()
lstm_gen.load(".cache/lstm_models.pt")

llm_gen = LLMViewGenerator()

# 2. Tạo views từ mỗi source
ml_views = ml_gen.generate_views(prices)
lstm_views = lstm_gen.generate_views(prices)
llm_views = llm_gen.generate_views(prices)

# 3. Kết hợp với trọng số
combined_views = combine_multi_source_views(
    traditional_ml_views=ml_views,
    lstm_views=lstm_views,
    llm_views=llm_views,
    weights=(0.3, 0.3, 0.4),  # 30% ML, 30% LSTM, 40% LLM
)

# 4. Sử dụng combined_views trong Black-Litterman
```

### Chiến lược kết hợp

**Strategy 1: Equal weight**
```python
weights=(0.33, 0.33, 0.34)  # Công bằng
```

**Strategy 2: Favor LLM** (nếu có budget)
```python
weights=(0.2, 0.2, 0.6)  # LLM chiếm 60%
```

**Strategy 3: Favor Traditional ML** (nếu data nhiều)
```python
weights=(0.5, 0.3, 0.2)  # ML chiếm 50%
```

**Strategy 4: Only ML+LSTM** (không dùng LLM)
```python
weights=(0.5, 0.5, 0.0)  # Không LLM
```

## Tích hợp vào Backtest

### Bước 1: Update backtest.py

```python
# Thêm vào đầu file backtest.py
from llm_view_generators import (
    TraditionalMLViewGenerator,
    LSTMViewGenerator,
    LLMViewGenerator,
)

# Thêm VIEW_MODE mới
VIEW_MODE = "ml_ensemble"  # hoặc "ml_only", "lstm_only", "llm_only"

# Khởi tạo generators (1 lần)
ml_generator = TraditionalMLViewGenerator()
ml_generator.load(".cache/xgboost_models.pkl")  # load trained model

lstm_generator = LSTMViewGenerator()
lstm_generator.load(".cache/lstm_models.pt")

llm_generator = LLMViewGenerator(enable_caching=True)
```

### Bước 2: Thêm logic tạo views

```python
# Trong hàm main(), tại phần tạo views:

if VIEW_MODE == "ml_only":
    views = ml_generator.generate_views(recent_prices)
elif VIEW_MODE == "lstm_only":
    views = lstm_generator.generate_views(recent_prices)
elif VIEW_MODE == "llm_only":
    views = llm_generator.generate_views(recent_prices)
elif VIEW_MODE == "ml_ensemble":
    ml_views = ml_generator.generate_views(recent_prices)
    lstm_views = lstm_generator.generate_views(recent_prices)
    llm_views = llm_generator.generate_views(recent_prices)
    
    views = combine_multi_source_views(
        ml_views, lstm_views, llm_views,
        weights=(0.3, 0.3, 0.4)
    )
```

### Bước 3: Train models trước khi backtest

```python
# train_models.py - Script riêng để train
import pandas as pd
from llm_view_generators import TraditionalMLViewGenerator, LSTMViewGenerator

# Load train data (2020-2023)
train_prices = pd.read_csv(...)  # Load your training data

# Train XGBoost
print("Training XGBoost...")
xgb_gen = TraditionalMLViewGenerator(model_type="xgboost")
xgb_gen.train(train_prices, verbose=True)
xgb_gen.save(".cache/xgb_models.pkl")

# Train LSTM
print("Training LSTM...")
lstm_gen = LSTMViewGenerator(epochs=50)
lstm_gen.train(train_prices, verbose=True)
lstm_gen.save(".cache/lstm_models.pt")

print("All models trained and saved!")
```

## Debugging & Troubleshooting

### Issue 1: PyTorch not found
```bash
pip install torch
# Hoặc với CUDA:
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

### Issue 2: XGBoost not found
```bash
pip install xgboost
```

### Issue 3: OpenAI API error
```python
# Check API key
import openai
print(openai.api_key)  # Should not be None

# Test connection
from openai import OpenAI
client = OpenAI(api_key="sk-...")
response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)
```

### Issue 4: LSTM training too slow
```python
# Giảm epochs
lstm_gen = LSTMViewGenerator(epochs=20)  # thay vì 50

# Giảm batch size
lstm_gen = LSTMViewGenerator(batch_size=16)  # thay vì 32

# Hoặc dùng GPU
lstm_gen = LSTMViewGenerator(device="cuda")
```

### Issue 5: Not enough data for LSTM
```python
# LSTM cần ít nhất sequence_length + prediction_horizon + 100 samples
# Nếu data ít, giảm sequence_length:
lstm_gen = LSTMViewGenerator(sequence_length=30)  # thay vì 60
```

## Best Practices

### 1. Train/Test Split đúng cách
```python
# ĐÚNG: Split theo thời gian
train = prices.loc["2020-01-01":"2023-10-01"]
test = prices.loc["2023-10-01":]

# SAI: Random split (tạo look-ahead bias)
from sklearn.model_selection import train_test_split
train, test = train_test_split(prices)  # ❌ KHÔNG LÀM NHƯ VẦY
```

### 2. Tránh Overfitting
```python
# XGBoost: Tăng min_samples_split, min_samples_leaf
ml_gen = TraditionalMLViewGenerator(
    model_params={
        "min_samples_split": 20,
        "min_samples_leaf": 10,
    }
)

# LSTM: Tăng dropout, giảm hidden_size
lstm_gen = LSTMViewGenerator(
    dropout=0.3,
    hidden_size=32,  # nhỏ hơn = ít overfit hơn
)
```

### 3. Kiểm tra performance
```python
# So sánh predictions vs actual returns
predictions = ml_gen.predict(test_prices)
actual_returns = test_prices.pct_change().mean()

for asset, (pred, conf) in predictions.items():
    actual = actual_returns[asset]
    print(f"{asset}: Predicted={pred:.2%}, Actual={actual:.2%}")
```

### 4. Monitoring chi phí LLM
```python
# Track cost sau mỗi backtest
cost_summary = llm_gen.get_cost_summary()
print(f"LLM cost this session: ${cost_summary['total_cost_usd']:.2f}")

# Warning nếu cost quá cao
if cost_summary['total_cost_usd'] > 10.0:
    print("WARNING: LLM cost exceeds $10!")
```

## Kết quả mong đợi

Dựa trên literature và thực nghiệm:

| Method | Expected Sharpe | Training Time | Inference Time |
|--------|----------------|---------------|----------------|
| Rule-based | 1.70 | 0s (no training) | <1ms |
| XGBoost | 1.55-1.85 | 10-20s | <1ms |
| LSTM | 1.60-1.90 | 2-5 min | 10-50ms |
| LLM (GPT-4) | 1.65-2.00 | 0s | 2-5s |
| Ensemble | **1.80-2.10** | - | - |

**Note**: Kết quả phụ thuộc vào:
- Chất lượng data
- Hyperparameters
- Market regime (trending vs mean-reverting)

## Câu hỏi cho luận văn

Khi viết luận văn, trả lời các câu hỏi sau:

1. **So sánh performance**: Method nào cho Sharpe ratio cao nhất? Tại sao?
2. **Stability**: Method nào ổn định nhất qua thời gian?
3. **Interpretability**: Làm sao giải thích được ML predictions?
4. **Cost-benefit**: LLM có đáng với chi phí API không?
5. **Ensemble vs Single**: Kết hợp có tốt hơn dùng 1 method không?
6. **Feature importance**: Features nào quan trọng nhất cho ML?
7. **Error analysis**: Khi nào models dự đoán sai? Tại sao?

## Tài liệu tham khảo

- [Scikit-learn User Guide](https://scikit-learn.org/stable/user_guide.html)
- [XGBoost Documentation](https://xgboost.readthedocs.io/)
- [PyTorch Tutorials](https://pytorch.org/tutorials/)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [Anthropic Claude Docs](https://docs.anthropic.com/)

## Liên hệ & Hỗ trợ

Nếu gặp vấn đề, check:
1. File `llm_view_generators.py` có chạy được không: `python llm_view_generators.py`
2. Dependencies đã cài đủ chưa: `pip list | grep -E "sklearn|xgboost|torch|openai"`
3. API keys đã set đúng chưa: `echo $OPENAI_API_KEY`

Chúc bạn thành công với luận văn! 🚀
