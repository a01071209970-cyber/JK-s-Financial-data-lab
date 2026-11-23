# V0.5 — Candidate SEC Financial Tag Preflight

**Historical cutoff:** 2026-11-17 (filings strictly earlier)
**State:** FINANCIAL_TAG_CANDIDATES_ONLY — NOT ONBOARDED

| Ticker | Revenue | Operating income | OCF | CAPEX | Latest revenue period | Direct revenue period ends |
|---|---|---|---|---|---|---:|
| AMZN | CANDIDATE | CANDIDATE | CANDIDATE | CANDIDATE | 2026-09-30 | 68 |
| META | CANDIDATE | CANDIDATE | CANDIDATE | CANDIDATE | 2026-09-30 | 47 |
| GOOGL | CANDIDATE | CANDIDATE | CANDIDATE | CANDIDATE | 2026-09-30 | 37 |
| AVGO | CANDIDATE | CANDIDATE | CANDIDATE | CANDIDATE | 2026-08-02 | 34 |
| ANET | CANDIDATE | CANDIDATE | CANDIDATE | CANDIDATE | 2026-09-30 | 48 |
| CRDO | CANDIDATE | CANDIDATE | CANDIDATE | CANDIDATE | 2026-08-01 | 17 |

## Candidate concepts and provenance

### AMZN

- Verified CIK: `0001018724`
- Raw SHA-256: `acddb7c0a6973a1fd08372de3b292298a34eae7f42a7eedc4bdebd3ac659c8fd`
- Missing candidate groups: None
- Revenue: tags=RevenueFromContractWithCustomerExcludingAssessedTax, SalesRevenueGoodsNet, SalesRevenueNet, SalesRevenueServicesNet; latest period end=2026-09-30; latest eligible filing=2026-10-30; direct-length period ends=68
- Operating income: tags=OperatingIncomeLoss; latest period end=2026-09-30; latest eligible filing=2026-10-30; direct-length period ends=65
- Operating cash flow: tags=NetCashProvidedByUsedInOperatingActivities; latest period end=2026-09-30; latest eligible filing=2026-10-30; direct-length period ends=56
- CAPEX candidate: tags=PaymentsToAcquireProductiveAssets, PaymentsToAcquirePropertyPlantAndEquipment; latest period end=2026-09-30; latest eligible filing=2026-10-30; direct-length period ends=55

### META

- Verified CIK: `0001326801`
- Raw SHA-256: `f8e539cea9d363752df2f9bb33078c19ae897ff7f34d49fe4d9a732d032b94f7`
- Missing candidate groups: None
- Revenue: tags=RevenueFromContractWithCustomerExcludingAssessedTax, Revenues; latest period end=2026-09-30; latest eligible filing=2026-10-22; direct-length period ends=47
- Operating income: tags=OperatingIncomeLoss; latest period end=2026-09-30; latest eligible filing=2026-10-22; direct-length period ends=47
- Operating cash flow: tags=NetCashProvidedByUsedInOperatingActivities; latest period end=2026-09-30; latest eligible filing=2026-10-22; direct-length period ends=15
- CAPEX candidate: tags=PaymentsToAcquirePropertyPlantAndEquipment; latest period end=2026-09-30; latest eligible filing=2026-10-22; direct-length period ends=15

### GOOGL

- Verified CIK: `0001652044`
- Raw SHA-256: `e4b7685f57b8d6fc9be74c23dc891dfd81de5716d0551338914385fa11bf43a6`
- Missing candidate groups: None
- Revenue: tags=RevenueFromContractWithCustomerExcludingAssessedTax, Revenues; latest period end=2026-09-30; latest eligible filing=2026-10-29; direct-length period ends=37
- Operating income: tags=OperatingIncomeLoss; latest period end=2026-09-30; latest eligible filing=2026-10-29; direct-length period ends=37
- Operating cash flow: tags=NetCashProvidedByUsedInOperatingActivities; latest period end=2026-09-30; latest eligible filing=2026-10-29; direct-length period ends=12
- CAPEX candidate: tags=PaymentsToAcquirePropertyPlantAndEquipment; latest period end=2026-09-30; latest eligible filing=2026-10-29; direct-length period ends=24

### AVGO

- Verified CIK: `0001730168`
- Raw SHA-256: `3bdb6644c12addf1e63c4dc861008d7804fbf3d3f5aa6eb9b97f72c0e89a7adf`
- Missing candidate groups: None
- Revenue: tags=RevenueFromContractWithCustomerExcludingAssessedTax, Revenues, SalesRevenueNet; latest period end=2026-08-02; latest eligible filing=2026-09-10; direct-length period ends=34
- Operating income: tags=OperatingIncomeLoss; latest period end=2026-08-02; latest eligible filing=2026-09-10; direct-length period ends=34
- Operating cash flow: tags=NetCashProvidedByUsedInOperatingActivities; latest period end=2026-08-02; latest eligible filing=2026-09-10; direct-length period ends=9
- CAPEX candidate: tags=PaymentsToAcquirePropertyPlantAndEquipment; latest period end=2026-08-02; latest eligible filing=2026-09-10; direct-length period ends=9

### ANET

- Verified CIK: `0001596532`
- Raw SHA-256: `3c6e88dae7c6ee8891f2c4eacdfff23599876320021bb2c568754ace3015a457`
- Missing candidate groups: None
- Revenue: tags=RevenueFromContractWithCustomerExcludingAssessedTax, RevenueFromContractWithCustomerIncludingAssessedTax, SalesRevenueGoodsNet, SalesRevenueNet, SalesRevenueServicesNet; latest period end=2026-09-30; latest eligible filing=2026-11-04; direct-length period ends=48
- Operating income: tags=OperatingIncomeLoss; latest period end=2026-09-30; latest eligible filing=2026-11-04; direct-length period ends=48
- Operating cash flow: tags=NetCashProvidedByUsedInOperatingActivities; latest period end=2026-09-30; latest eligible filing=2026-11-04; direct-length period ends=13
- CAPEX candidate: tags=PaymentsToAcquireIntangibleAssets, PaymentsToAcquireProductiveAssets, PaymentsToAcquirePropertyPlantAndEquipment; latest period end=2026-09-30; latest eligible filing=2026-11-04; direct-length period ends=13

### CRDO

- Verified CIK: `0001807794`
- Raw SHA-256: `42718952361414c81add8e89adf6803dd1fb6d1f511cc66b62b3e62484045323`
- Missing candidate groups: None
- Revenue: tags=RevenueFromContractWithCustomerExcludingAssessedTax; latest period end=2026-08-01; latest eligible filing=2026-09-02; direct-length period ends=17
- Operating income: tags=OperatingIncomeLoss; latest period end=2026-08-01; latest eligible filing=2026-09-02; direct-length period ends=17
- Operating cash flow: tags=NetCashProvidedByUsedInOperatingActivities; latest period end=2026-08-01; latest eligible filing=2026-09-02; direct-length period ends=6
- CAPEX candidate: tags=PaymentsToAcquirePropertyPlantAndEquipment; latest period end=2026-08-01; latest eligible filing=2026-09-02; direct-length period ends=6

## Interpretation

- A CANDIDATE tag is present, but its financial-statement definition is not approved.
- Direct-length periods are 70–110 days, not 12 validated fiscal quarters.
- Alternative taxonomy tags may represent different accounting definitions.
- OCF and CAPEX may be year-to-date; standalone quarters have not been reconstructed.
- Same-day filings are excluded pending acceptance-time verification.
- A filed date alone does not establish complete point-in-time availability.
- Existing four-company DuckDB tables and reports were not accessed or modified.
- Fiscal calendars, full 12-quarter coverage, FCF and valuation remain PENDING_REVIEW.

**Decision: DISCOVERY_ONLY — NO NEW COMPANY ADMITTED.**
