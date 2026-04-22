"""
Test LLM View Generator
========================

Script đơn giản để test LLM view generator với OpenAI API.
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from llm_view_generators import LLMViewGenerator

# Load environment variables from .env
load_dotenv()

# Verify API key loaded
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("ERROR: OPENAI_API_KEY not found in .env file")
    exit(1)

print("✓ API key loaded successfully")
print(f"  Key starts with: {api_key[:20]}...")

# ====================== LOAD TEST DATA ======================

ROOT_DIR = Path(__file__).resolve().parents[0]
DATASETS_DIR = ROOT_DIR / "datasets"

print("\nLoading test data...")

# Load recent price data for testing
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

# DCDS
dcds_path = DATASETS_DIR / "funds" / "test" / "DCDS_test.csv"
if dcds_path.exists():
    df = pd.read_csv(dcds_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data["DCDS"] = df["price"]
    print(f"  ✓ DCDS: {len(df)} days")

# MBBOND
mbbond_path = DATASETS_DIR / "funds" / "test" / "MBBOND_test.csv"
if mbbond_path.exists():
    df = pd.read_csv(mbbond_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    assets_data["MBBOND"] = df["price"]
    print(f"  ✓ MBBOND: {len(df)} days")

if not assets_data:
    print("\nERROR: No test data found!")
    print("Please run data crawlers first:")
    print("  python crawl/stock.py")
    print("  python crawl/gold.py")
    print("  python crawl/fund.py")
    exit(1)

# Combine into DataFrame
prices = pd.DataFrame(assets_data)

# Use last 60 days for testing
prices = prices.tail(60)

print(f"\nTest data shape: {prices.shape}")
print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")
print("\nRecent prices:")
print(prices.tail())

# ====================== TEST LLM GENERATOR ======================

print("\n" + "=" * 70)
print("TESTING LLM VIEW GENERATOR (OpenAI GPT-4)")
print("=" * 70)

# Initialize LLM generator
print("\nInitializing LLM generator...")
print("Using gpt-3.5-turbo (best for free tier)")
llm_gen = LLMViewGenerator(
    llm_provider="openai",
    model_name="gpt-3.5-turbo",  # Free tier model (thay vì gpt-4o-mini)
    temperature=0.5,  # Tăng lên 0.5 để flexible hơn
    max_tokens=300,  # Giảm xuống 300 để tiết kiệm tokens
    enable_caching=True,  # Bật cache để giảm cost
    cache_ttl_hours=24,
    enable_news=False,  # Tắt news cho lần test đầu (đơn giản hơn)
    news_lookback_days=7,
)

print("✓ LLM generator initialized")
print(f"  Provider: {llm_gen.llm_provider}")
print(f"  Model: {llm_gen.model_name}")
print(f"  Caching: {llm_gen.enable_caching}")
print(f"  News: {llm_gen.enable_news}")

# Generate views
print("\n" + "-" * 70)
print("Generating views... (this will take 10-20 seconds)")
print("-" * 70)

try:
    views = llm_gen.generate_views(prices, verbose=True)

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
            print(f"   Reasoning: {view.get('reasoning', 'N/A')}")
            print()
    else:
        print("\n⚠ No views generated")

    # Cost summary
    print("\n" + "=" * 70)
    print("COST SUMMARY")
    print("=" * 70)

    cost_summary = llm_gen.get_cost_summary()
    print(f"\nTotal API calls: {cost_summary['total_calls']}")
    print(f"Total cost: ${cost_summary['total_cost_usd']:.4f}")
    print(f"Average cost per call: ${cost_summary['avg_cost_per_call']:.4f}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE!")
    print("=" * 70)

    print("\nNext steps:")
    print("1. Check if views make sense based on recent price movements")
    print("2. Try running again - should use cache (0 cost)")
    print("3. Try with enable_news=True for more context")
    print("4. Integrate into backtest.py")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback

    traceback.print_exc()

    print("\nTroubleshooting:")
    print("1. Check API key is valid")
    print("2. Check internet connection")
    print("3. Check OpenAI API status: https://status.openai.com/")
