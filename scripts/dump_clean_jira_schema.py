from sqlalchemy import create_engine, text

# Database URL from docker environment or local
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/process_metrics_v2"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    print("# Clean Jira Schema Documentation\n")

    tables = conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'clean_jira' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
    ).fetchall()

    for (table_name,) in tables:
        print(f"## Table: `clean_jira.{table_name}`")
        print("| Column | Type | Example |")
        print("| :--- | :--- | :--- |")

        cols_query = text(
            f"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'clean_jira' AND table_name = '{table_name}' ORDER BY ordinal_position"
        )
        cols = conn.execute(cols_query).fetchall()

        row_query = text(f"SELECT * FROM clean_jira.{table_name} LIMIT 1")
        row = conn.execute(row_query).fetchone()

        for col_name, data_type in cols:
            val = ""
            if row:
                val = str(row._mapping.get(col_name))
                if len(val) > 100:
                    val = val[:97] + "..."
            print(f"| `{col_name}` | `{data_type}` | {val} |")
        print("\n")
