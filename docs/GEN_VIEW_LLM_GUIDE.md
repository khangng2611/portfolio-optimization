# Sinh Views cho Black-Litterman bằng Large Language Models (LLMs)

**Tài liệu nghiên cứu**: Ứng dụng AI trong Portfolio Optimization  
**Nội dung**: Phương pháp sinh Views động bằng LLMs  
**Mục đích**: Báo cáo với giảng viên, nghiên cứu hướng cải tiến

---

## Mục lục

1. [Giới thiệu](#1-giới-thiệu)
2. [Tại sao dùng LLM cho View Generation?](#2-tại-sao-dùng-llm-cho-view-generation)
3. [Option 1: Traditional ML (XGBoost)](#3-option-1-traditional-ml-xgboost)
4. [Option 2: Deep Learning (LSTM, Transformer)](#4-option-2-deep-learning-lstm-transformer)
5. [Option 3: LLM-based Views (GPT-4, Claude)](#5-option-3-llm-based-views-gpt-4-claude)
6. [So sánh 3 Options](#6-so-sánh-3-options)
7. [Kết hợp với Rule-Based](#7-kết-hợp-với-rule-based)
8. [Challenges & Solutions](#8-challenges--solutions)
9. [Roadmap Implementation](#9-roadmap-implementation)

---

## 1. Giới thiệu

### 1.1. Bối cảnh

Trong nghiên cứu trước, chúng ta đã implement **Rule-based View Generator** sử dụng Technical Analysis (MA, RSI, Momentum). Phương pháp này:

✅ **Ưu điểm**:
- Có cơ sở toán học rõ ràng
- Interpretable, dễ giải thích
- Performance tốt (Sharpe 1.70)

❌ **Hạn chế**:
- Chỉ dựa vào price data (quantitative)
- Không tận dụng thông tin qualitative (news, sentiment)
- Không học được complex patterns từ data

### 1.2. Cơ hội với Machine Learning & LLMs

**Machine Learning** có thể:
- Học patterns phức tạp từ historical data
- Tự động feature engineering
- Dự đoán non-linear relationships

**Large Language Models** (LLMs) có thể:
- Hiểu và phân tích tin tức tài chính
- Đánh giá sentiment từ báo cáo, social media
- Kết hợp quantitative + qualitative data
- Reasoning như một financial analyst

### 1.3. Ba hướng tiếp cận
#### Option 1: Traditional ML (XGBoost, ...)
- Input: Price data
- Features: Manual
- Complexity: Medium
#### Option 2: Deep Learning (LSTM, Transformer)
- Input: Sequences
- Features: Auto
- Complexity: High
#### Option 3: LLM-based (GPT-4, Claude, Gemini, ...)
- Input: Text + Price data 
- Complexity: Very High

---

## 2. Tại sao dùng LLM cho View Generation?

### 2.1. Giới hạn của Rule-Based

**Rule-based chỉ nhìn thấy**:
```
Price Data → Technical Indicators → Views
     ↓
  E1VFVN30: 25,000 → 24,500 → 24,000
     ↓
  MA_ratio = -2.5% → BEARISH view
```

**Nhưng bỏ sót**:
- 📰 Tin tức: "VN-Index tăng điểm mạnh nhờ dòng tiền ngoại"
- 💬 Sentiment: Investor confidence tăng
- 📊 Context: FED giảm lãi suất
- 🌍 Macro: USD giảm giá, vàng tăng

### 2.2. LLM có thể làm gì?

#### Ví dụ 1: Phân tích tin tức

**Input (Text)**:
```
Tin tức ngày 15/03/2026:
1. "NHNN giữ nguyên lãi suất điều hành ở mức 4.5%"
2. "VN30 tăng 15 điểm, thanh khoản đạt 8,000 tỷ đồng"
3. "Vàng thế giới giảm về 2,100 USD/oz do USD mạnh lên"
```

**LLM reasoning**:
```
Phân tích:
- NHNN giữ lãi suất → Chính sách tiền tệ ổn định
- VN30 tăng điểm + thanh khoản cao → Risk appetite tăng
- Vàng giảm do USD mạnh → Vàng trong nước có thể giảm theo

Kết luận:
- E1VFVN30: BULLISH (môi trường tích cực cho cổ phiếu)
- GOLD: BEARISH (áp lực từ vàng thế giới)

View:
{
  "E1VFVN30": +8% annualized (confidence: 0.7),
  "GOLD": -3% annualized (confidence: 0.6)
}
```

#### Ví dụ 2: Kết hợp Quant + Qual

**Input**:
```
Quantitative:
- E1VFVN30: MA_ratio = +3.2% (bullish)
- E1VFVN30: RSI = 72 (overbought)
- E1VFVN30: Momentum_20d = +12%

Qualitative:
- "Cổ phiếu ngân hàng bứt phá, VCB tăng trần"
- "Dòng tiền F0 đổ vào thị trường mạnh mẽ"
- "Chuyên gia dự báo VN-Index có thể lên 1,300 điểm"
```

**LLM reasoning**:
```
Phân tích kết hợp:

Technical:
- MA crossover và momentum mạnh → Xu hướng tăng rõ ràng
- RSI = 72 → Hơi overbought, nhưng trong uptrend có thể kéo dài

Fundamental:
- Sentiment rất tích cực, dòng tiền mạnh
- Ngân hàng (trụ VN30) đang dẫn dắt

Tổng hợp:
- RSI cao nhưng được support bởi strong sentiment
- Xu hướng tăng có thể kéo dài thêm 1-2 tuần

View:
- E1VFVN30: +10% annualized (confidence: 0.75)
- Lý do: Technical bullish + Strong fundamental support
- Risk: Nếu RSI > 80, nên giảm confidence xuống 0.5
```

### 2.3. So sánh Rule-Based vs LLM

| Khía cạnh | Rule-Based | LLM-Based |
|-----------|------------|-----------|
| **Input** | Chỉ price data | Price + News + Sentiment |
| **Reasoning** | Fixed rules (if-then) | Contextual understanding |
| **Adaptability** | Không tự học | Có thể học từ feedback |
| **Interpretability** | 100% transparent | Có thể giải thích (với prompting) |
| **Cost** | Free | API costs (GPT-4: $0.01-0.03/1K tokens) |
| **Speed** | Rất nhanh (< 1ms) | Chậm hơn (1-3 seconds/call) |
| **Accuracy** | Ổn định, consistent | Có thể hallucinate |

---

## 3. Option 1: Traditional ML (XGBoost)

### 3.1. Cơ chế hoạt động

**Pipeline tổng quan**:

```
┌──────────────────────────────────────────────────────────────┐
│                    TRADITIONAL ML PIPELINE                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: Data Collection                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Historical Price Data (2018-2024)                  │     │
│  │ - Open, High, Low, Close                           │     │
│  │ - Volume (if available)                            │     │
│  │ - Corporate actions                                │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  Step 2: Feature Engineering                                │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Technical Indicators:                              │     │
│  │ - Momentum: ROC_5, ROC_10, ROC_20                 │     │
│  │ - Trend: EMA_10/30, MACD, ADX                     │     │
│  │ - Volatility: ATR, Bollinger width                │     │
│  │ - Volume: Volume_SMA_ratio                        │     │
│  │ - Others: RSI, Stochastic, CCI                    │     │
│  │                                                    │     │
│  │ → Total: 20-30 features                           │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  Step 3: Label Creation                                     │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Target Y = Future return (forward 20 days)        │     │
│  │                                                    │     │
│  │ If today = Day t:                                 │     │
│  │   Y[t] = (Price[t+20] - Price[t]) / Price[t]     │     │
│  │                                                    │     │
│  │ Example:                                          │     │
│  │   Day 0: Price = 100                              │     │
│  │   Day 20: Price = 108                             │     │
│  │   Y[0] = (108-100)/100 = 0.08 = 8%              │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  Step 4: Train/Valid/Test Split                            │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Time Series Split (NO shuffling!)                 │     │
│  │                                                    │     │
│  │ [Train: 2018-2021][Valid: 2021-2022][Test: 2022+]│     │
│  │                                                    │     │
│  │ Important: Avoid look-ahead bias                  │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  Step 5: Model Training                                     │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Algorithms:                                        │     │
│  │ • XGBoost: Gradient boosting (fast, accurate)    │     │
│  │ • LightGBM: Memory efficient, large datasets     │     │
│  │                                                    │     │
│  │ Hyperparameters tuning:                           │     │
│  │ - n_estimators: 100-500                          │     │
│  │ - max_depth: 5-15                                │     │
│  │ - learning_rate: 0.01-0.1                        │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  Step 6: Prediction & View Generation                      │
│  ┌────────────────────────────────────────────────────┐     │
│  │ At rebalance time t:                              │     │
│  │ 1. Compute current features                       │     │
│  │ 2. predicted_return = model.predict(features)    │     │
│  │ 3. confidence = get_confidence(model, features)  │     │
│  │ 4. Create view if |predicted_return| > threshold │     │
│  └────────────────────────────────────────────────────┘     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 3.2. Ưu điểm

1. **Well-established**: Được nghiên cứu và sử dụng rộng rãi
2. **Interpretable**: Feature importances, SHAP values
3. **Fast training**: Vài phút trên laptop
4. **Robust**: Ít overfitting hơn deep learning
5. **Easy debugging**: Có thể analyze từng tree/feature

### 3.3. Nhược điểm

1. **Manual feature engineering**: Phải tự tạo features
2. **No sequential modeling**: Không capture time dependencies tốt
3. **Limited to tabular**: Không xử lý được text, images
4. **Plateau performance**: Khó tăng accuracy hơn sau một ngưỡng

### 3.4. Khi nào nên dùng?

✅ **Phù hợp khi**:
- Bạn có feature engineering expertise
- Data không quá lớn (< 1M samples)
- Cần interpretability cao
- Muốn train nhanh, iterate nhanh

❌ **Không phù hợp khi**:
- Data có sequential dependencies phức tạp
- Muốn tự động feature extraction
- Cần xử lý multi-modal data (text + price)

---

## 4. Option 2: Deep Learning (LSTM, Transformer)

### 4.1. Cơ chế hoạt động

#### 4.1.1. LSTM (Long Short-Term Memory)

**Kiến trúc**:

```
┌────────────────────────────────────────────────────────────┐
│                      LSTM ARCHITECTURE                     │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Input: Sequence of price windows                         │
│  ┌──────────────────────────────────────────────┐         │
│  │ [Day -19][Day -18]...[Day -1][Day 0]         │         │
│  │                                               │         │
│  │ Each day: [Open, High, Low, Close, Volume]   │         │
│  │                                               │         │
│  │ Shape: (batch_size, seq_len, features)       │         │
│  │        (32, 20, 5)                            │         │
│  └──────────────────────────────────────────────┘         │
│                         ↓                                  │
│  Layer 1: LSTM (64 hidden units)                          │
│  ┌──────────────────────────────────────────────┐         │
│  │ For each timestep:                            │         │
│  │   h_t = LSTM(x_t, h_{t-1}, c_{t-1})          │         │
│  │                                               │         │
│  │ Memory cells capture:                         │         │
│  │ - Short-term patterns (recent days)           │         │
│  │ - Long-term trends (weeks/months)             │         │
│  │                                               │         │
│  │ Output: Hidden states h_0, h_1, ..., h_19    │         │
│  └──────────────────────────────────────────────┘         │
│                         ↓                                  │
│  Layer 2: Dropout (0.2)                                   │
│  ┌──────────────────────────────────────────────┐         │
│  │ Randomly drop 20% neurons                     │         │
│  │ → Prevent overfitting                         │         │
│  └──────────────────────────────────────────────┘         │
│                         ↓                                  │
│  Layer 3: LSTM (32 hidden units)                          │
│  ┌──────────────────────────────────────────────┐         │
│  │ Stack second LSTM for deeper representations  │         │
│  └──────────────────────────────────────────────┘         │
│                         ↓                                  │
│  Layer 4: Fully Connected (1 output)                      │
│  ┌──────────────────────────────────────────────┐         │
│  │ Take last hidden state h_19                   │         │
│  │ → FC layer → Predicted return                 │         │
│  │                                               │         │
│  │ Output: Single value (forward 20-day return) │         │
│  └──────────────────────────────────────────────┘         │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Tại sao LSTM hiệu quả?**

1. **Memory cells**: Nhớ được thông tin từ xa (long-term dependencies)
2. **Gates mechanism**:
   - **Forget gate**: Quyết định quên thông tin cũ nào
   - **Input gate**: Quyết định cập nhật thông tin mới nào
   - **Output gate**: Quyết định output gì từ memory

3. **Ví dụ**:
   ```
   Sequence: [100, 102, 105, 103, 107, 110, ...]
   
   LSTM học được:
   - Pattern 1: Prices are trending up (+10% over 20 days)
   - Pattern 2: Small pullbacks (103 after 105) are temporary
   - Pattern 3: Momentum is accelerating (slope increasing)
   
   → Prediction: Likely to continue up
   ```

#### 4.1.2. Transformer

**Kiến trúc**:

```
┌────────────────────────────────────────────────────────────┐
│                   TRANSFORMER ARCHITECTURE                 │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Input: Same as LSTM (sequences)                          │
│                         ↓                                  │
│  Positional Encoding                                       │
│  ┌──────────────────────────────────────────────┐         │
│  │ Add position information to sequence          │         │
│  │ (Transformers don't have inherent order)      │         │
│  │                                               │         │
│  │ PE(pos, 2i) = sin(pos / 10000^(2i/d))        │         │
│  │ PE(pos, 2i+1) = cos(pos / 10000^(2i/d))      │         │
│  └──────────────────────────────────────────────┘         │
│                         ↓                                  │
│  Multi-Head Self-Attention                                │
│  ┌──────────────────────────────────────────────┐         │
│  │ Attention(Q, K, V) = softmax(QK^T/√d) × V    │         │
│  │                                               │         │
│  │ Learns relationships between all timesteps:   │         │
│  │ - Which days are most relevant?               │         │
│  │ - How do Day -5 and Day -15 interact?        │         │
│  │                                               │         │
│  │ Multiple heads capture different patterns     │         │
│  └──────────────────────────────────────────────┘         │
│                         ↓                                  │
│  Feed-Forward Network                                      │
│  ┌──────────────────────────────────────────────┐         │
│  │ FFN(x) = max(0, xW1 + b1)W2 + b2              │         │
│  │                                               │         │
│  │ Non-linear transformation                     │         │
│  └──────────────────────────────────────────────┘         │
│                         ↓                                  │
│  Output: Predicted return                                 │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Ưu điểm của Transformer**:
1. **Parallel processing**: Không sequential như LSTM → Nhanh hơn
2. **Long-range dependencies**: Attention mechanism xem toàn bộ sequence
3. **State-of-the-art**: Được dùng trong GPT, BERT

### 4.2. Ưu điểm của Deep Learning

1. **Automatic feature learning**: Không cần manual engineering
2. **Capture complex patterns**: Non-linear, hierarchical features
3. **Scalability**: Performance tăng theo data size
4. **Transfer learning**: Có thể fine-tune pre-trained models

### 4.3. Nhược điểm

1. **Data hungry**: Cần nhiều data (100K+ samples)
2. **Computational cost**: Cần GPU, training lâu (hours/days)
3. **Black box**: Khó interpret hơn các mô hình cây quyết định
4. **Overfitting risk**: Dễ overfit nếu không regularize đúng
5. **Hyperparameter tuning**: Rất nhiều parameters cần tune

### 4.4. Khi nào nên dùng?

✅ **Phù hợp khi**:
- Có nhiều data (years of daily data cho nhiều assets)
- Có GPU/TPU resources
- Muốn capture temporal dependencies
- Không cần interpretability tuyệt đối

❌ **Không phù hợp khi**:
- Data ít (< 1000 samples)
- Không có GPU
- Cần train nhanh, iterate nhanh
- Stakeholders yêu cầu interpretability cao

---

## 5. Option 3: LLM-based Views (GPT-4, Claude)

### 5.1. Cơ chế hoạt động

**Pipeline tổng quan**:

```
┌──────────────────────────────────────────────────────────────┐
│                      LLM-BASED PIPELINE                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: Data Collection                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Quantitative:                                      │     │
│  │ - Price data (recent 30 days)                     │     │
│  │ - Technical indicators (MA, RSI, MACD)            │     │
│  │                                                    │     │
│  │ Qualitative:                                      │     │
│  │ - News: Crawl from CafeF, VnExpress              │     │
│  │ - Social sentiment: Twitter, Reddit               │     │
│  │ - Macro data: Interest rates, USD/VND            │     │
│  │ - Company reports: Earnings, guidance            │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  Step 2: Prompt Engineering                                 │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Craft detailed prompt:                             │     │
│  │                                                    │     │
│  │ System: "You are a financial analyst..."         │     │
│  │                                                    │     │
│  │ User: "Analyze E1VFVN30:                          │     │
│  │                                                    │     │
│  │ Price data:                                       │     │
│  │ [Chart/table of prices]                           │     │
│  │                                                    │     │
│  │ Technical indicators:                             │     │
│  │ - MA_ratio: +3.2% (bullish)                      │     │
│  │ - RSI: 68 (near overbought)                      │     │
│  │ - MACD: Positive histogram                        │     │
│  │                                                    │     │
│  │ Recent news:                                      │     │
│  │ 1. 'VN30 tăng mạnh nhờ cổ phiếu ngân hàng'      │     │
│  │ 2. 'Dòng tiền ngoại tiếp tục mua ròng'           │     │
│  │ 3. 'FED signal giữ lãi suất ổn định'             │     │
│  │                                                    │     │
│  │ Provide view in JSON format..."                   │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  Step 3: LLM Inference                                      │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Call OpenAI API / Anthropic API / Google AI       │     │
│  │                                                    │     │
│  │ response = client.chat.completions.create(        │     │
│  │     model="gpt-4",                                │     │
│  │     messages=[...],                               │     │
│  │     response_format={"type": "json_object"}       │     │
│  │ )                                                 │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  Step 4: Parse Response                                     │
│  ┌────────────────────────────────────────────────────┐     │
│  │ LLM Output (JSON):                                 │     │
│  │ {                                                  │     │
│  │   "asset": "E1VFVN30",                            │     │
│  │   "predicted_return_annual": 0.12,                │     │
│  │   "confidence": 0.75,                             │     │
│  │   "reasoning": "Strong technical + positive       │     │
│  │                 sentiment + foreign inflows",     │     │
│  │   "risks": ["RSI near overbought",                │     │
│  │             "Potential profit-taking"],           │     │
│  │   "time_horizon": "1-2 months"                    │     │
│  │ }                                                  │     │
│  └────────────────────────────────────────────────────┘     │
│                         ↓                                    │
│  Step 5: View Generation                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │ Convert to Black-Litterman format:                 │     │
│  │                                                    │     │
│  │ view = {                                          │     │
│  │     "name": "E1VFVN30_llm_view",                  │     │
│  │     "legs": {"E1VFVN30": 1.0},                    │     │
│  │     "view_return_annual": 0.12,                   │     │
│  │     "confidence": 0.75,                           │     │
│  │     "reasoning": "..."  # For audit trail         │     │
│  │ }                                                  │     │
│  └────────────────────────────────────────────────────┘     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 5.2. Prompt Engineering Chi tiết

**Prompt tốt là chìa khóa thành công**. Ví dụ prompt template:

```python
SYSTEM_PROMPT = """
Bạn là một chuyên gia phân tích tài chính chuyên nghiệp với 10 năm kinh nghiệm 
trong quản lý danh mục đầu tư tại thị trường Việt Nam.

Nhiệm vụ của bạn là phân tích dữ liệu tài chính và đưa ra dự báo về expected 
return của các tài sản cho mô hình Black-Litterman.

Quy tắc:
1. Phân tích kỹ cả technical và fundamental factors
2. Xem xét context thị trường toàn cầu và Việt Nam
3. Đưa ra dự báo realistic (không quá lạc quan hoặc bi quan)
4. Luôn cung cấp reasoning chi tiết
5. Đánh giá confidence dựa trên độ tin cậy của signals

Output format: JSON với các field sau:
- predicted_return_annual: float (-1.0 đến 1.0)
- confidence: float (0.0 đến 1.0)
- reasoning: string (chi tiết lý do)
- key_factors: list[string] (các yếu tố chính ảnh hưởng)
- risks: list[string] (các rủi ro cần lưu ý)
"""

USER_PROMPT_TEMPLATE = """
Hãy phân tích và dự báo return cho tài sản: {asset_name}

═══════════════════════════════════════════════════════════════
1. DỮ LIỆU GIÁ (30 NGÀY GẦN NHẤT)
═══════════════════════════════════════════════════════════════
{price_table}

Giá hiện tại: {current_price:,.0f} VND
Thay đổi 30 ngày: {change_30d:+.2%}
Highest 30d: {high_30d:,.0f} VND
Lowest 30d: {low_30d:,.0f} VND

═══════════════════════════════════════════════════════════════
2. CHỈ BÁO KỸ THUẬT
═══════════════════════════════════════════════════════════════
Moving Averages:
  • EMA 10: {ema_10:.2f}
  • EMA 30: {ema_30:.2f}
  • MA Ratio: {ma_ratio:+.2%} → {ma_signal}

Momentum:
  • ROC 20d: {momentum_20:+.2%}
  • ROC 60d: {momentum_60:+.2%}

Oscillators:
  • RSI (14): {rsi:.1f} → {rsi_zone}
  • MACD Histogram: {macd_hist:.4f}

Volatility:
  • ATR (14): {atr:.2f}
  • Bollinger Position: {bb_position:.2%}

═══════════════════════════════════════════════════════════════
3. TIN TỨC GẦN ĐÂY (10 BÀI MỚI NHẤT)
═══════════════════════════════════════════════════════════════
{news_list}

═══════════════════════════════════════════════════════════════
4. SENTIMENT ANALYSIS
═══════════════════════════════════════════════════════════════
Social Media Sentiment: {social_sentiment}
News Sentiment: {news_sentiment}
Analyst Ratings: {analyst_ratings}

═══════════════════════════════════════════════════════════════
5. BỐI CẢNH THỊ TRƯỜNG
═══════════════════════════════════════════════════════════════
VN-Index: {vnindex_level:,.2f} ({vnindex_change:+.2%})
Thanh khoản: {liquidity:,.0f} tỷ đồng
Dòng tiền ngoại: {foreign_flow} tỷ đồng
Lãi suất NHNN: {interest_rate:.2%}
USD/VND: {usdvnd:,.0f}

═══════════════════════════════════════════════════════════════
YÊU CẦU PHÂN TÍCH
═══════════════════════════════════════════════════════════════
Dựa trên tất cả thông tin trên, hãy:
1. Đánh giá xu hướng (bullish/bearish/neutral)
2. Dự đoán expected return trong 20 ngày giao dịch tới (annualized)
3. Đánh giá confidence level (0-1)
4. Giải thích chi tiết reasoning
5. Liệt kê key factors và risks

Output JSON format:
{{
    "predicted_return_annual": <float>,
    "confidence": <float>,
    "reasoning": "<detailed explanation>",
    "key_factors": ["factor1", "factor2", ...],
    "risks": ["risk1", "risk2", ...]
}}
"""
```

### 5.3. Ưu điểm của LLM

1. **Multi-modal understanding**: 
   - Hiểu cả numbers (price) và text (news)
   - Kết nối information từ nhiều nguồn

2. **Contextual reasoning**:
   ```
   LLM có thể reasoning:
   
   "RSI = 72 (overbought) NHƯNG trong context của:
    - Strong foreign inflows (tin tức)
    - Breaking resistance level (technical)
    - Positive earnings guidance (fundamental)
   
   → RSI cao là healthy, không phải alarm
   → Bullish view vẫn valid với confidence cao"
   ```

3. **Natural language output**:
   - Dễ explain cho stakeholders
   - Có thể audit reasoning process

4. **Zero-shot / Few-shot learning**:
   - Không cần train từ đầu
   - Có thể adapt nhanh cho new assets

5. **Updated knowledge**:
   - GPT-4 Turbo có knowledge cutoff gần đây
   - Hiểu về current events, macro trends

### 5.4. Nhược điểm

1. **Hallucination risk**: 
   - LLM có thể "bịa" facts
   - Solution: Verify với external data sources

2. **Cost**:
   ```
   Ví dụ với GPT-4:
   
   Input: ~2000 tokens (price data + news + prompt)
   Output: ~500 tokens (JSON response)
   
   Cost: $0.01/1K input + $0.03/1K output
        = $0.02 + $0.015 = $0.035 per view
   
   With 4 assets, 5 rebalances/day, 252 days:
   Total: $0.035 × 4 × 5 × 252 = $176.4/year
   ```

3. **Latency**:
   - API call: 1-3 seconds
   - 4 assets × rebalance → 4-12 seconds
   - Có thể bottleneck for high-frequency

4. **Reproducibility**:
   - Same prompt có thể cho different outputs
   - Solution: Set temperature=0, seed parameter

5. **API dependency**:
   - Cần internet connection
   - Rate limits (TPM, RPM)
   - API downtime risk

### 5.5. Khi nào nên dùng?

✅ **Phù hợp khi**:
- Có budget cho API costs
- Cần kết hợp quant + qual data
- Muốn interpretable reasoning
- Portfolio size vừa phải (< 50 assets)
- Rebalance frequency thấp (daily/weekly)

❌ **Không phù hợp khi**:
- High-frequency trading (< 1 hour)
- Cost-sensitive (limited budget)
- No internet access (offline systems)
- Cần deterministic output

---

## 6. So sánh 3 Options

### 6.1. Comparison Table

| Tiêu chí | Traditional ML | Deep Learning | LLM-Based |
|----------|----------------|---------------|-----------|
| **Data Requirements** | Moderate (10K samples) | High (100K+ samples) | Low (can work with small data) |
| **Training Time** | Minutes | Hours/Days | No training (zero-shot) |
| **Inference Speed** | Very Fast (< 1ms) | Fast (< 10ms) | Slow (1-3s) |
| **Hardware** | CPU OK | GPU needed | API call (no local compute) |
| **Interpretability** | High (feature importance) | Low (black box) | High (natural language reasoning) |
| **Accuracy Potential** | Good (70-75%) | Very Good (75-80%) | Good (70-75%, but holistic) |
| **Cost** | Low (electricity) | Medium (GPU costs) | High (API fees) |
| **Multi-modal** | No (only tabular) | Limited (needs engineering) | Yes (text + numbers native) |
| **Maintenance** | Medium (retrain monthly) | High (retrain, tune often) | Low (API updates automatically) |
| **Reproducibility** | 100% | 100% (with fixed seed) | ~90% (temperature=0) |

### 6.2. Kịch bản sử dụng

#### Scenario 1: Research Phase (hiện tại)

```
Mục tiêu: Khám phá, test nhanh, iterate
Budget: Hạn chế
Timeline: 2-3 tháng

→ Gợi ý: Traditional ML (XGBoost)

Lý do:
✓ Train nhanh, iterate nhanh
✓ Dễ debug, analyze features
✓ Cost thấp
✓ Đủ tốt để validate idea
```

#### Scenario 2: Thesis Completion

```
Mục tiêu: Hoàn thiện luận văn, so sánh methods
Budget: Medium (có thể xin funding)
Timeline: 6 tháng

→ Gợi ý: All 3 options (so sánh)

Approach:
1. Implement XGBoost (baseline ML)
2. Implement LSTM (advanced DL)
3. Test LLM với small sample (proof of concept)
4. Compare performance trong thesis

Value:
✓ Comprehensive comparison
✓ Novel contribution (LLM for BL views)
✓ Publication potential
```

#### Scenario 3: Production System (tương lai)

```
Mục tiêu: Deploy real trading system
Budget: High (hedge fund, asset manager)
Timeline: Long-term

→ Gợi ý: Ensemble của cả 3

Architecture:
┌──────────────────────────────────────┐
│         ENSEMBLE SYSTEM              │
├──────────────────────────────────────┤
│                                      │
│  Option 1: XGBoost                   │
│  Weight: 0.3                         │
│  → Fast, reliable baseline           │
│                                      │
│  Option 2: LSTM                      │
│  Weight: 0.4                         │
│  → Capture temporal patterns         │
│                                      │
│  Option 3: LLM (GPT-4)               │
│  Weight: 0.3                         │
│  → Incorporate news/sentiment        │
│                                      │
│  Final View = Weighted Average       │
│                                      │
└──────────────────────────────────────┘

Value:
✓ Diversification (không phụ thuộc single model)
✓ Robustness (1 model fail, còn 2 models khác)
✓ Complementary strengths
```

---

## 7. Kết hợp với Rule-Based

### 7.1. Tại sao cần kết hợp?

**Rule-Based** (đã có):
- ✅ Fast, deterministic
- ✅ Proven track record (Sharpe 1.70)
- ✅ 100% transparent
- ❌ Chỉ dùng price data

**ML/LLM**:
- ✅ Richer information
- ✅ Adaptive learning
- ❌ Rủi ro overfitting, hallucination

**Ensemble approach** = Best of both worlds!

### 7.2. Kiến trúc kết hợp

```
┌──────────────────────────────────────────────────────────────┐
│              HYBRID VIEW GENERATION SYSTEM                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────┐  ┌──────────────────┐  ┌─────────────┐ │
│  │  Rule-Based    │  │  ML (XGBoost)    │  │ LLM (GPT-4) │ │
│  │                │  │                  │  │             │ │
│  │ Input: Price   │  │ Input: Features  │  │ Input: All  │ │
│  │ Output: Views  │  │ Output: Views    │  │ Output:Views│ │
│  └───────┬────────┘  └────────┬─────────┘  └──────┬──────┘ │
│          │                    │                    │        │
│          └────────────────────┼────────────────────┘        │
│                               ↓                             │
│                      ┌─────────────────┐                    │
│                      │  VIEW FUSION    │                    │
│                      │                 │                    │
│                      │  Strategies:    │                    │
│                      │  1. Weighted Avg│                    │
│                      │  2. Voting      │                    │
│                      │  3. Meta-model  │                    │
│                      └────────┬────────┘                    │
│                               ↓                             │
│                      ┌─────────────────┐                    │
│                      │  FINAL VIEWS    │                    │
│                      │  (P, Q, Ω)      │                    │
│                      └────────┬────────┘                    │
│                               ↓                             │
│                      ┌─────────────────┐                    │
│                      │ BLACK-LITTERMAN │                    │
│                      └─────────────────┘                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 7.3. Fusion Strategies

#### Strategy 1: Weighted Average

```python
def weighted_average_fusion(rule_views, ml_views, llm_views):
    """
    Kết hợp bằng trung bình trọng số.
    
    Weights dựa trên historical performance.
    """
    weights = {
        'rule': 0.4,   # Rule-based đã proven (Sharpe 1.70)
        'ml': 0.35,    # ML có potential cao
        'llm': 0.25    # LLM bổ sung qualitative
    }
    
    combined_views = []
    
    # Điều chỉnh confidence theo weights
    for view in rule_views:
        view['confidence'] *= weights['rule']
        view['source'] = 'rule_based'
        combined_views.append(view)
    
    for view in ml_views:
        view['confidence'] *= weights['ml']
        view['source'] = 'ml'
        combined_views.append(view)
    
    for view in llm_views:
        view['confidence'] *= weights['llm']
        view['source'] = 'llm'
        combined_views.append(view)
    
    return combined_views
```

#### Strategy 2: Voting System

```python
def voting_fusion(rule_views, ml_views, llm_views):
    """
    Chỉ giữ views được >=2/3 methods đồng ý.
    
    Tăng confidence nếu cả 3 methods agree.
    """
    assets = set()
    for views in [rule_views, ml_views, llm_views]:
        for view in views:
            for asset in view['legs'].keys():
                assets.add(asset)
    
    consensus_views = []
    
    for asset in assets:
        # Collect predictions từ 3 methods
        predictions = []
        
        for views, name in [(rule_views, 'rule'), 
                            (ml_views, 'ml'), 
                            (llm_views, 'llm')]:
            for view in views:
                if asset in view['legs'] and view['legs'][asset] == 1.0:
                    predictions.append({
                        'source': name,
                        'return': view['view_return_annual'],
                        'confidence': view['confidence']
                    })
        
        # Nếu ít nhất 2/3 agree
        if len(predictions) >= 2:
            # Average return, sum confidence
            avg_return = np.mean([p['return'] for p in predictions])
            total_confidence = sum([p['confidence'] for p in predictions])
            total_confidence = min(0.95, total_confidence)  # Cap
            
            consensus_views.append({
                'name': f'{asset}_consensus',
                'legs': {asset: 1.0},
                'view_return_annual': avg_return,
                'confidence': total_confidence,
                'num_votes': len(predictions),
                'sources': [p['source'] for p in predictions]
            })
    
    return consensus_views
```

#### Strategy 3: Meta-Model

```python
def meta_model_fusion(rule_views, ml_views, llm_views, meta_model):
    """
    Train một meta-model để học cách kết hợp tối ưu.
    
    Meta-model input: [rule_pred, ml_pred, llm_pred, rule_conf, ...]
    Meta-model output: final_view, final_confidence
    """
    # Feature cho meta-model
    features = []
    
    for asset in all_assets:
        rule_pred = get_prediction(rule_views, asset)
        ml_pred = get_prediction(ml_views, asset)
        llm_pred = get_prediction(llm_views, asset)
        
        rule_conf = get_confidence(rule_views, asset)
        ml_conf = get_confidence(ml_views, asset)
        llm_conf = get_confidence(llm_views, asset)
        
        # Agreement metrics
        agreement = compute_agreement(rule_pred, ml_pred, llm_pred)
        
        features.append([
            rule_pred, ml_pred, llm_pred,
            rule_conf, ml_conf, llm_conf,
            agreement
        ])
    
    # Meta-model prediction
    final_views = meta_model.predict(features)
    
    return final_views
```

---

## 8. Challenges & Solutions

### 8.1. Challenge 1: Data Quality

**Vấn đề**:
- News từ crawl có thể duplicate, spam
- Price data có missing values
- Corporate actions (splits, dividends) gây noise

**Solutions**:

```python
# 1. News deduplication
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def deduplicate_news(news_list):
    """Remove duplicate/similar news articles."""
    if len(news_list) <= 1:
        return news_list
    
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(news_list)
    
    similarities = cosine_similarity(tfidf_matrix)
    
    # Keep only unique articles (similarity < 0.8)
    unique_indices = []
    for i in range(len(news_list)):
        is_unique = True
        for j in unique_indices:
            if similarities[i, j] > 0.8:
                is_unique = False
                break
        if is_unique:
            unique_indices.append(i)
    
    return [news_list[i] for i in unique_indices]

# 2. Price data cleaning
def clean_price_data(df):
    """Handle missing values and corporate actions."""
    # Forward fill for missing values
    df = df.ffill()
    
    # Detect and adjust for stock splits
    daily_returns = df['close'].pct_change()
    outliers = daily_returns[abs(daily_returns) > 0.5]  # >50% move
    
    if len(outliers) > 0:
        print(f"Warning: Detected {len(outliers)} potential corporate actions")
        # Manual review or automatic adjustment
    
    return df
```

### 8.2. Challenge 2: LLM Hallucination

**Vấn đề**:
- LLM có thể "bịa" facts không có trong input
- Ví dụ: "According to recent analyst report..." (không có trong prompt)

**Solutions**:

```python
# 1. Structured output format
def generate_llm_view_with_citations(asset, price_data, news_data):
    """Force LLM to cite sources."""
    
    prompt = f"""
    Analyze {asset} and provide view in JSON format:
    {{
        "predicted_return_annual": <float>,
        "confidence": <float>,
        "reasoning": "<explanation>",
        "evidence": [
            {{"source": "technical", "fact": "MA_ratio = +3.2%"}},
            {{"source": "news", "fact": "Foreign inflows +$10M"}},
            ...
        ]
    }}
    
    IMPORTANT: Only cite facts from the data provided above.
    Do NOT make up information.
    """
    
    response = call_llm_api(prompt)
    view = json.loads(response)
    
    # Verify citations
    for evidence in view['evidence']:
        if not verify_evidence(evidence, price_data, news_data):
            print(f"Warning: Unverified evidence: {evidence}")
            view['confidence'] *= 0.8  # Penalize
    
    return view

# 2. Multiple LLM cross-check
def ensemble_llm_views(asset, data):
    """Use multiple LLMs and check consistency."""
    
    gpt4_view = call_gpt4(asset, data)
    claude_view = call_claude(asset, data)
    gemini_view = call_gemini(asset, data)
    
    # Check consistency
    returns = [gpt4_view['return'], claude_view['return'], gemini_view['return']]
    
    if np.std(returns) > 0.05:  # High disagreement
        print("Warning: LLMs disagree significantly")
        # Use average or most conservative
        final_return = np.median(returns)
        final_confidence = min([v['confidence'] for v in [gpt4_view, claude_view, gemini_view]])
    else:
        final_return = np.mean(returns)
        final_confidence = np.mean([v['confidence'] for v in [gpt4_view, claude_view, gemini_view]])
    
    return {
        'return': final_return,
        'confidence': final_confidence
    }
```

### 8.3. Challenge 3: Cost Optimization

**Vấn đề**:
- LLM API costs tăng với số lượng calls
- 4 assets × 5 rebalances/day × 252 days = 5,040 calls/year
- @$0.035/call = $176/year (chỉ cho 1 strategy)

**Solutions**:

```python
# 1. Caching
import hashlib
from functools import lru_cache

class LLMCache:
    def __init__(self, cache_file='llm_cache.json'):
        self.cache_file = cache_file
        self.cache = self.load_cache()
    
    def get_cache_key(self, asset, price_data, news_data):
        """Generate unique key for caching."""
        # Hash của input data
        data_str = f"{asset}_{price_data.tail(5).to_json()}_{hash(tuple(news_data[:3]))}"
        return hashlib.md5(data_str.encode()).hexdigest()
    
    def get(self, asset, price_data, news_data):
        key = self.get_cache_key(asset, price_data, news_data)
        return self.cache.get(key)
    
    def set(self, asset, price_data, news_data, view):
        key = self.get_cache_key(asset, price_data, news_data)
        self.cache[key] = view
        self.save_cache()

# 2. Batch processing
def batch_generate_llm_views(assets, data, batch_size=4):
    """Process multiple assets in single API call."""
    
    prompt = """
    Analyze the following assets and provide views for ALL of them:
    
    Asset 1: E1VFVN30
    [data for E1VFVN30]
    
    Asset 2: GOLD
    [data for GOLD]
    
    Asset 3: DCDS
    [data for DCDS]
    
    Asset 4: MBBOND
    [data for MBBOND]
    
    Return JSON array:
    [
        {"asset": "E1VFVN30", "return": ..., "confidence": ...},
        {"asset": "GOLD", "return": ..., "confidence": ...},
        ...
    ]
    """
    
    response = call_llm_api(prompt)
    views = json.loads(response)
    
    # Cost: 1 call instead of 4
    # Savings: 75%
    
    return views

# 3. Selective calling
def smart_llm_caller(asset, price_data, news_data, rule_view):
    """Only call LLM when needed."""
    
    # Nếu rule-based view đã rất clear (high confidence)
    if rule_view['confidence'] > 0.8:
        # Skip LLM call, save cost
        return None
    
    # Nếu có tin tức quan trọng
    important_news = filter_important_news(news_data)
    if len(important_news) == 0:
        # No news, skip LLM
        return None
    
    # Otherwise, call LLM
    return call_llm_api(asset, price_data, important_news)
```

---

## 9. Roadmap Implementation

### Phase 1: Proof of Concept (2 tuần)

**Mục tiêu**: Validate feasibility

**Tasks**:
1. ✅ Setup OpenAI API account
2. ✅ Write basic LLM view generator
3. ✅ Test trên 1 asset (E1VFVN30)
4. ✅ Compare với rule-based view
5. ✅ Document findings

**Deliverable**: Working prototype cho 1 asset

### Phase 2: Full Implementation (1 tháng)

**Mục tiêu**: Scale to all assets

**Tasks**:
1. Implement news crawler (CafeF, VnExpress)
2. Integrate LLM với backtest pipeline
3. Test cả 3 options (XGBoost, LSTM, LLM)
4. Compare performance
5. Optimize costs (caching, batching)

**Deliverable**: Full working system

### Phase 3: Thesis Writing (2 tháng)

**Mục tiêu**: Document research

**Tasks**:
1. Literature review (ML in finance)
2. Methodology chapter
3. Results & analysis
4. Discussion & limitations
5. Conclusion & future work

**Deliverable**: Thesis draft

### Phase 4: Refinement (1 tháng)

**Mục tiêu**: Polish & publish

**Tasks**:
1. Advisor feedback & revisions
2. Additional experiments if needed
3. Prepare presentation
4. Consider publication (conference/journal)

**Deliverable**: Final thesis + presentation

---

## 10. Kết luận

### 10.1. Key Takeaways

1. **LLM mang lại giá trị mới**:
   - Kết hợp quant + qual data
   - Natural language reasoning
   - Zero-shot learning

2. **Không phải silver bullet**:
   - Cost, latency, hallucination risks
   - Cần kết hợp với traditional methods
   - Ensemble approach is best

3. **Research opportunity**:
   - Novel application (LLM for BL views)
   - Publication potential
   - Practical impact

### 10.2. Recommendations cho Thesis

**Approach gợi ý**:

1. **Chapter 1**: Giới thiệu
   - Động lực nghiên cứu
   - Research questions
   - Contributions

2. **Chapter 2**: Literature Review
   - Black-Litterman model
   - ML in finance
   - LLMs for financial analysis

3. **Chapter 3**: Methodology
   - Rule-based (baseline)
    - Option 1: XGBoost
   - Option 2: LSTM (nếu có thời gian)
   - Option 3: LLM (GPT-4)

4. **Chapter 4**: Experiments & Results
   - Backtest setup
   - Performance comparison
   - Statistical significance tests
   - Ablation studies

5. **Chapter 5**: Discussion
   - Why LLM works/doesn't work
   - Limitations
   - Practical considerations

6. **Chapter 6**: Conclusion
   - Summary of findings
   - Future work
   - Implications

### 10.3. Next Steps

1. **Ngay lập tức**:
   - Đọc tài liệu này kỹ
   - Chạy code trong `llm_view_generators.py`
   - Test với API key

2. **Tuần tới**:
   - Báo cáo với giảng viên về hướng LLM
   - Xin feedback & approval
   - Lên plan chi tiết

3. **Tháng tới**:
    - Implement Option 1 (XGBoost) - dễ nhất
   - Nếu tốt, proceed với LLM
   - Document results

**Chúc bạn thành công!** 🚀

---

**Tài liệu tham khảo**:

1. OpenAI API Documentation: https://platform.openai.com/docs
2. "Large Language Models in Finance" (Lopez-Lira & Tang, 2023)
3. "FinGPT: Open-Source Financial LLMs" (Yang et al., 2023)
4. "BloombergGPT: A Large Language Model for Finance" (Wu et al., 2023)
