
from pathlib import Path
import sys
import duckdb

ROOT = Path(__file__).resolve().parent.parent

# 1. 실행할 SQL 파일 선택
if len(sys.argv) < 2:
    raise SystemExit(
        "사용법: python src/run_sql.py sql/파일이름.sql"
    )

sql_dir = (ROOT / "sql").resolve()
sql_path = (ROOT / sys.argv[1]).resolve()

# 2. 프로젝트의 sql 폴더에 있는 파일만 허용
if not sql_path.is_relative_to(sql_dir):
    raise ValueError("sql 폴더 안의 파일만 실행하세요.")

query = sql_path.read_text(encoding="utf-8")

# 3. DuckDB 연결
db_path = ROOT / "data/processed/financial_data.duckdb"
con = duckdb.connect(str(db_path), read_only=True)

try:
    result = con.execute(query).df()
    print(result.to_string(index=False))
finally:
    con.close()