# Planted vulnerability: SQL injection (ground truth: vulnerable).
import sqlite3


def user_by_id(conn, req):
    uid = req["id"]
    # VULN: request value concatenated straight into SQL, no parameterization.
    return conn.execute("SELECT * FROM users WHERE id = " + uid).fetchone()
