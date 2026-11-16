
from pathlib import Path
import duckdb

# 1. Project paths
ROOT = Path(__file__).resolve().parent.parent

DB_PATH = ROOT / "data/processed/financial_data.duckdb"
SQL_DIR = ROOT / "sql"

REVENUE_SQL = SQL_DIR / "09_quarterly_revenue_12q.sql"
INCOME_SQL = SQL_DIR / "10_quarterly_operating_income_12q.sql"
MARGIN_SQL = SQL_DIR / "11_quarterly_operating_margin_12q.sql"

# 2. Connect to DuckDB
con = duckdb.connect(str(DB_PATH), read_only=True)

try:
    # 3. Run existing revenue SQL
    revenue_query = REVENUE_SQL.read_text(encoding="utf-8")
    revenue_df = con.execute(revenue_query).df()

    # 4. Run existing operating income SQL
    income_query = INCOME_SQL.read_text(encoding="utf-8")
    income_df = con.execute(income_query).df()

    # 5. Validate quarter coverage
    keys = ["fiscal_year", "fiscal_quarter"]

    for name, df in [
        ("Revenue", revenue_df),
        ("Operating Income", income_df)
    ]:
        if len(df) != 12:
            raise ValueError(f"{name}: Expected 12 quarters")

        if df.duplicated(subset=keys).any():
            raise ValueError(f"{name}: Duplicate quarters")

    revenue_periods = set(
        map(tuple, revenue_df[keys].to_numpy())
    )
    income_periods = set(
        map(tuple, income_df[keys].to_numpy())
    )

    if revenue_periods != income_periods:
        raise ValueError("Quarter coverage does not match")

    # 6. Register temporary SQL views
    con.register("quarterly_revenue", revenue_df)
    con.register("quarterly_operating_income", income_df)

    # 7. Execute operating margin SQL
    margin_query = MARGIN_SQL.read_text(encoding="utf-8")
    result = con.execute(margin_query).df()

    # 8. Validate the final results
    if len(result) != 12:
        raise ValueError("Final result must contain 12 quarters")

    if result["operating_margin_pct"].isna().any():
        raise ValueError("Missing operating margin values")

    print(result.to_string(index=False))
    print()
    print("Quarters:", len(result))
    print("Operating Margin Validation: PASS")

finally:
    con.close()