from sqlalchemy import create_engine, text


def get_metadata():
    db_url = "postgresql://postgres:woJX9+pYcU+y2JApOCcqs5HP@localhost:5432/process_metrics_v2"
    engine = create_engine(db_url)

    with engine.connect() as conn:
        print("Definitions:")
        result = conn.execute(text("SELECT * FROM metrics.definitions"))
        for row in result:
            print(f"  {row}")

        print("\nCalculations:")
        result = conn.execute(text("SELECT * FROM metrics.calculations"))
        for row in result:
            print(f"  {row}")


if __name__ == "__main__":
    get_metadata()
