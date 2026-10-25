"""Operator-only AI pause/resume via a direct database connection. No public admin route."""

import argparse
from backend.auth_db import get_auth_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["pause", "resume", "status"])
    args = parser.parse_args()
    con = get_auth_connection()
    try:
        with con.cursor() as cur:
            if args.action != "status":
                cur.execute(
                    "UPDATE aura_deployment_control SET ai_enabled=%s,updated_at=NOW() WHERE id=1",
                    (args.action == "resume",),
                )
            cur.execute("SELECT ai_enabled FROM aura_deployment_control WHERE id=1")
            row = cur.fetchone()
        con.commit()
        print("AI generation:", "enabled" if row and row[0] else "paused")
    finally:
        con.close()


if __name__ == "__main__":
    main()
