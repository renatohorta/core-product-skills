## Finding
Class: injection
Location: app/db.py:9
Evidence: request id concatenated into SQL, no binding
Verdict: confirmed
Severity: High

## Finding
Class: ssrf
Location: app/fetch.py:8
Evidence: request-controlled url to urlopen, no allowlist
Verdict: confirmed
Severity: High

## Finding
Class: injection
Location: app/safe.py:5
Evidence: query with request id, but it is a bound parameter
Verdict: false positive — parameterized

## Coverage
- app/db.py: all
- app/fetch.py: all
- app/safe.py: all
