
from pathlib import Path
import json
import os
import requests

# 1. Palantir의 고유 기업 식별번호
CIK = "0001321655"

# 2. SEC Company Facts API
url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"

# 3. 원본 데이터를 저장할 위치
project_dir = Path(__file__).resolve().parent.parent
output = project_dir / "data/raw/pltr_companyfacts.json"

# 4. SEC 요청자 식별
user_agent = os.getenv("SEC_USER_AGENT")

if not user_agent:
    raise SystemExit("SEC_USER_AGENT를 먼저 설정하세요.")

# 5. 기존 파일이 없을 때만 다운로드
if output.exists():
    raw = output.read_bytes()
    print("기존 파일을 사용합니다.")
else:
    response = requests.get(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json"
        },
        timeout=30
    )
    response.raise_for_status()
    raw = response.content

# 6. JSON 변환 및 기업 검증
data = json.loads(raw)

if data.get("cik") != int(CIK):
    raise ValueError("CIK가 일치하지 않습니다.")

if "palantir" not in data.get("entityName", "").lower():
    raise ValueError("기업명이 일치하지 않습니다.")

# 7. 정상 데이터만 저장
if not output.exists():
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)

# 8. 수집 결과 출력
print("Company:", data["entityName"])
print("CIK:", data["cik"])
print("Saved:", output)
print("File size:", output.stat().st_size, "bytes")
print("US-GAAP tags:", len(data["facts"].get("us-gaap", {})))