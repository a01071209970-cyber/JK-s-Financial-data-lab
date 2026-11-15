
import json
from pathlib import Path

import duckdb
import pandas as pd

# 1. 파일 위치 설정
ROOT = Path(__file__).resolve().parent.parent

json_path = ROOT / "data/raw/pltr_companyfacts.json"
db_path = ROOT / "data/processed/financial_data.duckdb"

# 2. SEC JSON 불러오기
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

cik = data["cik"]

# 3. 중첩 JSON을 행 단위로 변환
rows = []

for taxonomy, tags in data["facts"].items():
    for tag, concept in tags.items():
        for unit, observations in concept["units"].items():
            for obs in observations:
                rows.append({
                    "cik": cik,
                    "taxonomy": taxonomy,
                    "tag": tag,
                    "label": concept.get("label"),
                    "unit": unit,
                    "period_start": obs.get("start"),
                    "period_end": obs.get("end"),
                    "value_raw": str(obs["val"]),
                    "form": obs.get("form"),
                    "filed": obs.get("filed"),
                    "accn": obs.get("accn"),
                    "fy": obs.get("fy"),
                    "fp": obs.get("fp"),
                    "frame": obs.get("frame")
                })

df = pd.DataFrame(rows)

# 4. DuckDB 연결
db_path.parent.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(db_path))

# 5. 기업 정보 테이블 생성
con.execute("""
CREATE TABLE IF NOT EXISTS companies (
    cik BIGINT PRIMARY KEY,
    ticker VARCHAR,
    company_name VARCHAR,
    source_url VARCHAR
)
""")

# 6. 재무 원본 관측값 테이블 생성
con.execute("""
CREATE TABLE IF NOT EXISTS financial_facts (
    cik BIGINT,
    taxonomy VARCHAR,
    tag VARCHAR,
    label VARCHAR,
    unit VARCHAR,
    period_start DATE,
    period_end DATE,
    value_raw VARCHAR,
    value_num DOUBLE,
    form VARCHAR,
    filed DATE,
    accn VARCHAR,
    fy INTEGER,
    fp VARCHAR,
    frame VARCHAR
)
""")

# 7. pandas 데이터를 DuckDB에 등록
con.register("incoming_facts", df)

# 8. 한 기업의 데이터를 안전하게 갱신
con.begin()

try:
    con.execute(
        "DELETE FROM financial_facts WHERE cik = ?",
        [cik]
    )

    con.execute("""
        INSERT OR REPLACE INTO companies
        VALUES (?, ?, ?, ?)
    """, [
        cik,
        "PLTR",
        data["entityName"],
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    ])

    con.execute("""
        INSERT INTO financial_facts
        SELECT
            cik,
            taxonomy,
            tag,
            label,
            unit,
            CAST(period_start AS DATE),
            CAST(period_end AS DATE),
            value_raw,
            TRY_CAST(value_raw AS DOUBLE),
            form,
            CAST(filed AS DATE),
            accn,
            CAST(fy AS INTEGER),
            fp,
            frame
        FROM incoming_facts
    """)

    con.commit()

except Exception:
    con.rollback()
    raise

# 9. 저장 결과 확인
result = con.execute("""
    SELECT COUNT(*)
    FROM financial_facts
    WHERE cik = ?
""", [cik]).fetchone()

print("Company:", data["entityName"])
print("JSON records:", len(df))
print("Database records:", result[0])
print("Database:", db_path)

assert len(df) == result[0], "행 개수가 일치하지 않습니다."

con.close()
print("Validation: PASS")