# Decoy: looks query-ish but is parameterized (ground truth: NOT vulnerable).
def user_by_id(conn, req):
    uid = req["id"]
    # SAFE: bound parameter — a tempting but false positive for injection.
    return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
