## Finding
Class: injection
Location: app/db.py:9
Evidence: looks like string SQL
Verdict: confirmed
Severity: High

## Finding
Class: injection
Location: app/safe.py:5
Evidence: query built with request id
Verdict: confirmed
Severity: High

## Coverage
- app/db.py: injection
- app/safe.py: injection
