"""Central configuration for the CITIMART Sales Forecasting module (Phase B).
Flat constants only, same style as config/settings.py -- no functions/classes
here besides the cache-dir mkdir() call.
"""
from __future__ import annotations

from config.settings import CACHE_DIR

FORECAST_CACHE_DIR = CACHE_DIR / "forecasts"
FORECAST_CACHE_DIR.mkdir(exist_ok=True)
CACHE_SCHEMA_VERSION = 1  # bump on any ForecastBundle shape change -- invalidates every cached forecast at once

RANDOM_SEED = 42

# Horizon is user-selectable and deliberately modest: DATASET.xlsx covers a
# single calendar year (181 days, Jan-Jun 2026) with no prior-year history, so
# a forecast is never presented as a confident long-range projection.
FORECAST_HORIZON_CHOICES = [7, 14, 30, 60, 90]
DEFAULT_HORIZON = 30
MIN_HISTORY_DAYS_FOR_FORECAST = 30  # below this, orchestrator returns insufficient_history=True instead of a misleading forecast

# Weekly seasonality is the strongest seasonal signal a single year of daily
# data can actually support -- there is no learnable yearly cycle yet.
SEASONAL_PERIOD = 7

# Walk-forward backtest: small folds, since only ~181 days total exist to
# split (not the usual multi-month holdout).
BACKTEST_FOLD_SIZE_DAYS = 7
BACKTEST_N_FOLDS = 4
BACKTEST_MIN_TRAIN_DAYS = 60
MAPE_EPSILON = 1e-6

CONFIDENCE_LEVEL = 0.90
BOOTSTRAP_N_SIMS = 500

# Full roster for the flagship single-series tabs (Sales, Footfall/NOB).
PRIMARY_MODEL_ROSTER = [
    "naive_seasonal", "arima", "sarima", "sarimax",
    "prophet", "random_forest", "hist_gradient_boosting", "xgboost",
]
# Cheaper subset for the products/vendors tabs, which backtest+forecast
# top_n+1 independent series in a single call -- Prophet's per-call cmdstan
# overhead and SARIMAX's grid search make the full roster impractically slow
# at 20+ series per page load.
PRODUCT_VENDOR_MODEL_ROSTER = ["naive_seasonal", "arima", "random_forest", "hist_gradient_boosting"]

ARIMA_ORDER_GRID = {"p": [0, 1, 2], "d": [0, 1], "q": [0, 1, 2]}
SARIMA_SEASONAL_ORDER_GRID = {"P": [0, 1], "D": [0, 1], "Q": [0, 1]}
MAX_GRID_SEARCH_COMBINATIONS = 18  # bounds ARIMA/SARIMA order-search time (selected once per series, not per fold)

RF_N_ESTIMATORS = 300
RF_MAX_DEPTH = 8
HGB_MAX_ITER = 300
XGB_N_ESTIMATORS = 300
XGB_MAX_DEPTH = 6
XGB_LEARNING_RATE = 0.05

FORECAST_LAG_FEATURES = (1, 7, 14, 28)
FORECAST_ROLLING_WINDOWS = (7, 14, 28)

TOP_N_PRODUCTS = 20
TOP_N_VENDORS = 20
TOP_N_PROMO_CAMPAIGNS = 15
OTHER_BUCKET_LABEL = "Other"

# item_code (35,559 uniques) is deliberately excluded -- too granular to
# forecast individually; product_style/department give a manageable top-N.
PRODUCT_FORECAST_LEVELS = ["product_style", "department"]
