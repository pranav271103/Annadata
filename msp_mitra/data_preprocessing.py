"""
Annadata MSP Mitra — Data Preprocessing & Feature Engineering
=============================================================
Converts raw AgMarkNet CSV data into ML-ready feature matrices.

Features generated:
  - Temporal: day, month, year, day_of_week, week_of_year, quarter
  - Lag:      modal_price_lag_3, _5, _7
  - Rolling:  rolling_mean_7, _14, _30
  - Volatility: rolling_std_7, _14
  - Momentum: pct_change_3, pct_change_7
  - Encoded:  state_encoded, market_encoded, commodity_encoded
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from sklearn.preprocessing import LabelEncoder
import logging
import pickle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent
PRICE_CSV = DATA_DIR / "agmarknet_india_historical_prices_2024_2025.csv"
ENCODER_DIR = Path(__file__).parent / "models"
ENCODER_DIR.mkdir(exist_ok=True)


class DataPreprocessor:
    """End-to-end preprocessing for mandi price data."""

    # Column name mapping for convenience
    COL_DATE = "Price Date"
    COL_COMMODITY = "Commodity"
    COL_STATE = "State"
    COL_MARKET = "Market Name"
    COL_DISTRICT = "District Name"
    COL_VARIETY = "Variety"
    COL_GRADE = "Grade"
    COL_MIN = "Min Price (Rs./Quintal)"
    COL_MAX = "Max Price (Rs./Quintal)"
    COL_MODAL = "Modal Price (Rs./Quintal)"

    def __init__(self):
        self.label_encoders: Dict[str, LabelEncoder] = {}
        self._raw_df: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # 1. Load & Clean
    # ------------------------------------------------------------------
    def load_raw_data(self, path: Optional[str] = None) -> pd.DataFrame:
        """Load CSV, parse dates, drop junk rows."""
        csv_path = Path(path) if path else PRICE_CSV
        if not csv_path.exists():
            raise FileNotFoundError(f"Data file not found: {csv_path}")

        logger.info(f"Loading data from {csv_path} ...")
        df = pd.read_csv(csv_path)

        # Parse date
        df[self.COL_DATE] = pd.to_datetime(
            df[self.COL_DATE], format="%d %b %Y", errors="coerce"
        )

        # Drop rows with invalid dates or prices
        before = len(df)
        df = df.dropna(subset=[self.COL_DATE, self.COL_MODAL])
        df = df[df[self.COL_MODAL] > 0]
        after = len(df)
        logger.info(f"Cleaned: {before:,} → {after:,} rows ({before - after} dropped)")

        # Sort globally by date
        df = df.sort_values(self.COL_DATE).reset_index(drop=True)
        self._raw_df = df
        return df

    # ------------------------------------------------------------------
    # 2. Filter by commodity / state / market
    # ------------------------------------------------------------------
    def filter_data(
        self,
        df: pd.DataFrame,
        commodity: str,
        state: Optional[str] = None,
        market: Optional[str] = None,
    ) -> pd.DataFrame:
        """Filter DataFrame by commodity and optionally state/market."""
        mask = df[self.COL_COMMODITY].str.lower() == commodity.lower()
        if state:
            mask &= df[self.COL_STATE].str.lower() == state.lower()
        if market:
            mask &= df[self.COL_MARKET].str.lower() == market.lower()

        filtered = df[mask].copy()
        filtered = filtered.sort_values(self.COL_DATE).reset_index(drop=True)
        return filtered

    # ------------------------------------------------------------------
    # 3. Aggregate daily prices (mean modal across markets per day)
    # ------------------------------------------------------------------
    def aggregate_daily(
        self,
        df: pd.DataFrame,
        group_cols: Optional[list] = None,
    ) -> pd.DataFrame:
        """
        Aggregate to daily level. If group_cols provided, aggregates
        within those groups; otherwise aggregates across all markets.
        """
        if group_cols:
            agg = (
                df.groupby(group_cols + [self.COL_DATE])
                .agg(
                    modal_price=(self.COL_MODAL, "mean"),
                    min_price=(self.COL_MIN, "min"),
                    max_price=(self.COL_MAX, "max"),
                    num_markets=(self.COL_MARKET, "nunique"),
                )
                .reset_index()
            )
        else:
            agg = (
                df.groupby(self.COL_DATE)
                .agg(
                    modal_price=(self.COL_MODAL, "mean"),
                    min_price=(self.COL_MIN, "min"),
                    max_price=(self.COL_MAX, "max"),
                    num_markets=(self.COL_MARKET, "nunique"),
                )
                .reset_index()
            )

        agg = agg.sort_values(self.COL_DATE).reset_index(drop=True)

        # Forward-fill any gaps in the price series
        agg["modal_price"] = agg["modal_price"].ffill()
        agg["min_price"] = agg["min_price"].ffill()
        agg["max_price"] = agg["max_price"].ffill()

        return agg

    # ------------------------------------------------------------------
    # 4. Feature Engineering
    # ------------------------------------------------------------------
    def add_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract calendar features from the date column."""
        date_col = self.COL_DATE if self.COL_DATE in df.columns else "Price Date"
        if date_col not in df.columns:
            # Try common variants
            for c in df.columns:
                if "date" in c.lower():
                    date_col = c
                    break

        df["day"] = df[date_col].dt.day
        df["month"] = df[date_col].dt.month
        df["year"] = df[date_col].dt.year
        df["day_of_week"] = df[date_col].dt.dayofweek
        df["week_of_year"] = df[date_col].dt.isocalendar().week.astype(int)
        df["quarter"] = df[date_col].dt.quarter

        return df

    def add_lag_features(
        self, df: pd.DataFrame, col: str = "modal_price", lags: list = None
    ) -> pd.DataFrame:
        """Add past-price lag features."""
        if lags is None:
            lags = [3, 5, 7]
        for lag in lags:
            df[f"{col}_lag_{lag}"] = df[col].shift(lag)
        return df

    def add_rolling_features(
        self, df: pd.DataFrame, col: str = "modal_price"
    ) -> pd.DataFrame:
        """Add rolling mean and std (volatility)."""
        for window in [7, 14, 30]:
            df[f"rolling_mean_{window}"] = (
                df[col].rolling(window=window, min_periods=1).mean()
            )
        for window in [7, 14]:
            df[f"rolling_std_{window}"] = (
                df[col].rolling(window=window, min_periods=1).std().fillna(0)
            )
        return df

    def add_momentum_features(
        self, df: pd.DataFrame, col: str = "modal_price"
    ) -> pd.DataFrame:
        """Price momentum as percentage change over N days."""
        for period in [3, 7]:
            df[f"pct_change_{period}"] = df[col].pct_change(periods=period).fillna(0)
        return df

    def add_price_spread(self, df: pd.DataFrame) -> pd.DataFrame:
        """Spread between max and min price."""
        if "max_price" in df.columns and "min_price" in df.columns:
            df["price_spread"] = df["max_price"] - df["min_price"]
        return df

    def encode_categoricals(
        self, df: pd.DataFrame, columns: list = None
    ) -> pd.DataFrame:
        """Label-encode categorical columns."""
        if columns is None:
            columns = [self.COL_COMMODITY, self.COL_STATE, self.COL_MARKET]
        for col in columns:
            if col not in df.columns:
                continue
            if col not in self.label_encoders:
                le = LabelEncoder()
                df[f"{col}_encoded"] = le.fit_transform(df[col].astype(str))
                self.label_encoders[col] = le
            else:
                le = self.label_encoders[col]
                # Handle unseen labels gracefully
                known = set(le.classes_)
                df[f"{col}_encoded"] = df[col].astype(str).apply(
                    lambda x: le.transform([x])[0] if x in known else -1
                )
        return df

    def save_encoders(self):
        """Persist label encoders."""
        path = ENCODER_DIR / "label_encoders.pkl"
        with open(path, "wb") as f:
            pickle.dump(self.label_encoders, f)
        logger.info(f"Saved encoders → {path}")

    def load_encoders(self):
        """Load label encoders from disk."""
        path = ENCODER_DIR / "label_encoders.pkl"
        if path.exists():
            with open(path, "rb") as f:
                self.label_encoders = pickle.load(f)
            logger.info("Loaded label encoders from disk")

    # ------------------------------------------------------------------
    # 5. Full Pipeline
    # ------------------------------------------------------------------
    def prepare_ml_dataset(
        self,
        commodity: str,
        state: Optional[str] = None,
        market: Optional[str] = None,
        variety: Optional[str] = None,
        df: Optional[pd.DataFrame] = None,
    ) -> Tuple[pd.DataFrame, list]:
        """
        Full preprocessing pipeline → returns (df, feature_columns).
        """
        if df is None:
            df = self.load_raw_data()

        # Filter
        filtered = self.filter_data(df, commodity, state, market)
        if variety:
             filtered = filtered[filtered[self.COL_VARIETY].str.lower() == variety.lower()].copy()

        if filtered.empty:
            logger.warning(f"No data for {commodity}/{state}/{market}/{variety}")
            return pd.DataFrame(), []

        # Aggregate daily
        daily = self.aggregate_daily(filtered)

        if len(daily) < 15:
            logger.warning(f"Too few data points ({len(daily)}) for {commodity}")
            return pd.DataFrame(), []

        # Feature engineering
        daily = self.add_temporal_features(daily)
        daily = self.add_lag_features(daily)
        daily = self.add_rolling_features(daily)
        daily = self.add_momentum_features(daily)
        daily = self.add_price_spread(daily)

        # Drop NaN rows created by lags
        daily = daily.dropna().reset_index(drop=True)

        # Define feature columns
        feature_cols = [
            "day",
            "month",
            "year",
            "day_of_week",
            "week_of_year",
            "quarter",
            "modal_price_lag_3",
            "modal_price_lag_5",
            "modal_price_lag_7",
            "rolling_mean_7",
            "rolling_mean_14",
            "rolling_mean_30",
            "rolling_std_7",
            "rolling_std_14",
            "pct_change_3",
            "pct_change_7",
            "min_price",
            "max_price",
            "price_spread",
            "num_markets",
        ]

        # Only keep columns that exist
        feature_cols = [c for c in feature_cols if c in daily.columns]

        logger.info(
            f"ML dataset ready: {len(daily)} rows, {len(feature_cols)} features"
        )
        return daily, feature_cols

    def prepare_prophet_data(
        self,
        commodity: str,
        state: Optional[str] = None,
        market: Optional[str] = None,
        variety: Optional[str] = None,
        df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Prepare data in Prophet format: columns 'ds' and 'y'.
        """
        if df is None:
            df = self.load_raw_data()

        filtered = self.filter_data(df, commodity, state, market)
        if variety:
             filtered = filtered[filtered[self.COL_VARIETY].str.lower() == variety.lower()].copy()

        if filtered.empty:
            return pd.DataFrame()

        daily = self.aggregate_daily(filtered)
        prophet_df = daily[[self.COL_DATE, "modal_price"]].copy()
        prophet_df.columns = ["ds", "y"]
        prophet_df = prophet_df.sort_values("ds").reset_index(drop=True)
        return prophet_df


# --------------- Singleton ---------------
_preprocessor: Optional[DataPreprocessor] = None


def get_preprocessor() -> DataPreprocessor:
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = DataPreprocessor()
    return _preprocessor
