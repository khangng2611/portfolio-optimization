"""Repeat the same strategies allowing exchange-session flat SJC quote rows."""
import os

import pandas as pd

from .portfolio import portfolios
from .score import score


def sensitivity(out):
    alt = out / "dated_quotes"
    alt.mkdir()
    os.link(out / "forecasts.csv", alt / "forecasts.csv")
    quotes = pd.read_csv(out / "gold_quotes.csv")
    quotes[["bid","ask"]] = quotes[["archive_bid","archive_ask"]].to_numpy()
    quotes.rename(columns={"execution_status":"primary_execution_status"}, inplace=True)
    quotes["execution_status"] = quotes.bid.notna().map({True:"dated_two_sided",False:"archive_row_missing"})
    quotes.to_csv(alt / "gold_quotes.csv", index=False)
    portfolios(alt)
    score(alt)
