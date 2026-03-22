from sqlalchemy import create_engine, text


def list_dbs():
    db_url = "postgresql://postgres:woJX9+pYcU+y2JApOCcqs5HP@localhost:5432/postgres"
    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT datname FROM pg_database WHERE datistemplate = false;")
        )
        for row in result:
            print(row[0])


if __name__ == "__main__":
    list_dbs()
