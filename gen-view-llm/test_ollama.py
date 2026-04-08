"""
Test LLM View Generator with Ollama (FREE, Local)
===================================================

Ollama cho phép chạy LLMs như GPT-4 trên máy local, 100% miễn phí!
Không cần API key, không có giới hạn quota.
"""

import os
from pathlib import Path

import pandas as pd

# ====================== CHECK OLLAMA ======================

print("=" * 70)
print("TESTING LLM VIEW GENERATOR WITH OLLAMA (Local, FREE)")
print("=" * 70)

print("\nChecking if Ollama is installed...")

try:
    import subprocess

    result = subprocess.run(
        ["ollama", "list"], capture_output=True, text=True, timeout=5
    )

    if result.returncode == 0:
        print("✓ Ollama is installed!")
        print("\nInstalled models:")
        print(result.stdout)
    else:
        print("❌ Ollama not found")
        print("\nTo install Ollama:")
        print("1. Visit: https://ollama.com/download")
        print("2. Download for macOS")
        print("3. Or use: brew install ollama")
        print("\nAfter installation, run:")
        print("  ollama pull llama3.2:3b")
        print("  ollama pull qwen2.5:3b")
        exit(1)

except FileNotFoundError:
    print("❌ Ollama not found")
    print("\nTo install Ollama:")
    print("1. Visit: https://ollama.com/download")
    print("2. Download for macOS")
    print("3. Or use: brew install ollama")
    print("\nAfter installation, run:")
    print("  ollama pull llama3.2:3b")
    print("  ollama pull qwen2.5:3b")
    exit(1)

# ====================== LOAD TEST DATA ======================

ROOT_DIR = Path(__file__).resolve().parents[1]
DATASETS_DIR = ROOT_DIR / "datasets"

print("\nLoading test data...")

assets_data = {}

# E1VFVN30
e1_path = DATASETS_DIR / "stocks" / "test" / "E1VFVN30_test.csv"
if e1_path.exists():
    df = pd.read_csv(e1_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data["E1VFVN30"] = df["close"]
    print(f"  ✓ E1VFVN30: {len(df)} days")

# GOLD
gold_path = DATASETS_DIR / "gold" / "gold_test.csv"
if gold_path.exists():
    df = pd.read_csv(gold_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data["GOLD"] = df["sjc_sell"]
    print(f"  ✓ GOLD: {len(df)} days")

# Combine
prices = pd.DataFrame(assets_data)
prices = prices.tail(60)

print(f"\nTest data shape: {prices.shape}")
print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")

# ====================== SIMPLE OLLAMA LLM VIEW GENERATOR ======================


class OllamaViewGenerator:
    """Simple Ollama-based view generator."""

    def __init__(self, model_name="llama3.2:3b"):
        self.model_name = model_name
        self.total_calls = 0

    def _query_ollama(self, prompt: str) -> str:
        """Query Ollama API."""
        import subprocess
        import json

        try:
            result = subprocess.run(
                ["ollama", "run", self.model_name, prompt],
                capture_output=True,
                text=True,
                timeout=90,
            )

            if result.returncode == 0:
                self.total_calls += 1
                return result.stdout.strip()
            else:
                print(f"Error: {result.stderr}")
                return None

        except Exception as e:
            print(f"Error querying Ollama: {e}")
            return None

    def generate_view_for_asset(self, asset: str, prices: pd.Series) -> dict:
        """Generate view for one asset."""

        # Calculate simple indicators
        recent_return = (prices.iloc[-1] / prices.iloc[-5] - 1) * 100
        momentum_20 = (prices.iloc[-1] / prices.iloc[-20] - 1) * 100

        # Recent prices
        recent_str = "\n".join(
            [
                f"  {date.strftime('%Y-%m-%d')}: {price:,.0f}"
                for date, price in prices.tail(10).items()
            ]
        )

        # Construct prompt
        prompt = f"""Bạn là chuyên gia tài chính. Phân tích tài sản "{asset}":

Giá gần đây (10 ngày):
{recent_str}

Thông tin:
- Return 5 ngày: {recent_return:.2f}%
- Momentum 20 ngày: {momentum_20:.2f}%

Hãy trả lời ngắn gọn:
1. Xu hướng (tăng/giảm/ngang): 
2. Dự đoán lợi nhuận năm (%): 
3. Độ tin cậy (0-1): 
4. Lý do (1 câu):

Chỉ trả lời 4 dòng, mỗi dòng 1 thông tin."""

        print(f"\n  Querying Ollama for {asset}...")
        response = self._query_ollama(prompt)

        if not response:
            return None

        print(f"  Response: {response[:200]}...")

        # Parse response (simple parsing)
        lines = response.strip().split("\n")

        try:
            # Extract values (rough parsing)
            trend = "neutral"
            if "tăng" in response.lower() or "bullish" in response.lower():
                trend = "bullish"
            elif "giảm" in response.lower() or "bearish" in response.lower():
                trend = "bearish"

            # Default values
            annual_return = (
                0.05 if trend == "bullish" else -0.03 if trend == "bearish" else 0.0
            )
            confidence = 0.5

            # Try to extract numbers from response
            import re

            numbers = re.findall(r"-?\d+\.?\d*", response)
            if len(numbers) >= 2:
                annual_return = float(numbers[0]) / 100  # Convert % to decimal
                confidence = min(1.0, max(0.1, float(numbers[1])))

            return {
                "name": f"{asset}_ollama",
                "legs": {asset: 1.0},
                "view_return_annual": annual_return,
                "confidence": confidence,
                "source": "llm_local",
                "model": self.model_name,
                "trend": trend,
                "reasoning": response[:150],
            }

        except Exception as e:
            print(f"  Error parsing response: {e}")
            return None


# ====================== TEST OLLAMA ======================

print("\n" + "=" * 70)
print("GENERATING VIEWS WITH OLLAMA")
print("=" * 70)

# Try to use llama3.2:3b (fast, good quality)
ollama_gen = OllamaViewGenerator(model_name="llama3.2:3b")

views = []

for asset in prices.columns:
    price_series = prices[asset].dropna()

    if len(price_series) < 30:
        continue

    view = ollama_gen.generate_view_for_asset(asset, price_series)

    if view:
        views.append(view)

# ====================== RESULTS ======================

print("\n" + "=" * 70)
print("RESULTS")
print("=" * 70)

if views:
    print(f"\n✓ Generated {len(views)} views:")
    print()

    for i, view in enumerate(views, 1):
        print(f"{i}. {view['name']}")
        print(f"   Expected annual return: {view['view_return_annual']:.2%}")
        print(f"   Confidence: {view['confidence']:.2f}")
        print(f"   Trend: {view.get('trend', 'N/A')}")
        print(f"   Reasoning: {view.get('reasoning', 'N/A')[:100]}")
        print()
else:
    print("\n⚠ No views generated")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"\nTotal Ollama calls: {ollama_gen.total_calls}")