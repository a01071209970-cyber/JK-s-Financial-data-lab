
import json
from pathlib import Path

# 1. 저장된 SEC 원본 데이터 읽기
project_dir = Path(__file__).resolve().parent.parent
file_path = project_dir / "data/raw/pltr_companyfacts.json"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# 2. US-GAAP 재무 항목 추출
facts = data["facts"]["us-gaap"]

# 3. 분석할 재무 지표와 XBRL 태그
targets = {
    "Revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet"
    ],
    "Operating Income": [
        "OperatingIncomeLoss"
    ],
    "Operating Cash Flow": [
        "NetCashProvidedByUsedInOperatingActivities"
    ],
    "Capital Expenditure": [
        "PaymentsToAcquirePropertyPlantAndEquipment"
    ]
}

# 4. 각 지표의 실제 공시 데이터 확인
for metric, candidates in targets.items():

    tag = next(
        (t for t in candidates if t in facts),
        None
    )

    print(f"\n--- {metric} ---")

    if tag is None:
        print("Matching US-GAAP tag not found")
        continue

    records = facts[tag]["units"].get("USD", [])

    # 10-Q와 10-K 공시만 확인
    records = [
        r for r in records
        if r.get("form") in ("10-Q", "10-K")
    ]

    # 공시일 기준 최신순 정렬
    records.sort(
        key=lambda r: (
            r.get("filed", ""),
            r.get("end", ""),
            r.get("start", "")
        ),
        reverse=True
    )

    print("XBRL Tag:", tag)
    print("Unit: USD")
    print("Number of records:", len(records))

    # 최신 공시 관측값 3개 출력
    for r in records[:3]:
        print(
            f"Period: {r.get('start')} to {r['end']}",
            f"| Value: {r['val']:,.0f}",
            f"| Filed: {r['filed']}",
            f"| Form: {r['form']}",
            f"| Accession: {r['accn']}"
        )