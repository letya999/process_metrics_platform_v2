import os

from sqlalchemy import create_engine, text

engine = create_engine(
    os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/process_metrics"
    )
)

with engine.connect() as conn:
    print("=== TABLES IN METRICS SCHEMA ===")
    tables = conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'metrics' AND table_type = 'BASE TABLE'"
        )
    ).fetchall()
    for (t,) in tables:
        print(f"\nTABLE: {t}")
        cols = conn.execute(
            text(
                f"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'metrics' AND table_name = '{t}'"
            )
        ).fetchall()
        for c, d in cols:
            print(f"  - {c} ({d})")

        print("  Example row:")
        try:
            row = conn.execute(text(f"SELECT * FROM metrics.{t} LIMIT 1")).fetchone()
            if row:
                print(f"    {dict(row._mapping)}")
            else:
                print("    (empty)")
        except Exception as e:
            print(f"    Error getting row: {e}")

    print("\n=== DEFINITIONS ===")
    try:
        defs = conn.execute(
            text("SELECT metric_code, name, description FROM metrics.definitions")
        ).fetchall()
        for d in defs:
            print(f"  - {d[0]}: {d[1]} ({d[2]})")
    except Exception as e:
        print(f"  Error reading metrics.definitions: {e}")

    print("\n=== CALCULATIONS ===")
    try:
        calcs = conn.execute(
            text(
                "SELECT calc_code, metric_code, name, description FROM metrics.calculations"
            )
        ).fetchall()
        for c in calcs:
            print(f"  - {c[0]} (Metric: {c[1]}): {c[2]} ({c[3]})")
    except Exception as e:
        print(f"  Error reading metrics.calculations: {e}")
