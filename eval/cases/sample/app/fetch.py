# Planted vulnerability: SSRF (ground truth: vulnerable).
import urllib.request


def fetch(req):
    url = req["url"]
    # VULN: request-controlled host, no allowlist, no block on internal ranges.
    return urllib.request.urlopen(url).read()
