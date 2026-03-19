import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def parse_markdown_velocity(path: Path) -> dict[int, dict[str, int]]:
    content = path.read_text(encoding="utf-8")
    result: dict[int, dict[str, int]] = {}
    pattern = re.compile(
        r"\|\s*ADS\s+[^\d\|]*?(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
        flags=re.IGNORECASE,
    )
    for m in pattern.finditer(content):
        sprint_num = int(m.group(1))
        result[sprint_num] = {"plan": int(m.group(2)), "fact": int(m.group(3))}
    return result


def load_db_velocity() -> dict[int, dict[str, int | str]]:
    load_dotenv(dotenv_path=Path(".env"))
    engine = create_engine(
        "postgresql://{user}:{pwd}@{host}:{port}/{db}".format(
            user=os.getenv("POSTGRES_USER", "postgres"),
            pwd=os.getenv("POSTGRES_PASSWORD", "postgres"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            db=os.getenv("POSTGRES_DB", "process_metrics_v2"),
        )
    )

    query = text(
        """
        WITH velocity AS (
          SELECT
            vf.entity_id::uuid AS sprint_id,
            MAX(CASE WHEN vf.calc_code = 'velocity_planned_sp' THEN vf.value END) AS planned_sp,
            MAX(CASE WHEN vf.calc_code = 'velocity_completed_sp' THEN vf.value END) AS completed_sp
          FROM metrics.v_facts vf
          WHERE vf.metric_code = 'velocity'
            AND vf.project_key = 'TWAD'
            AND vf.slice_rule_name IS NULL
          GROUP BY vf.entity_id
        )
        SELECT s.name, velocity.planned_sp, velocity.completed_sp
        FROM velocity
        JOIN clean_jira.sprints s ON s.id = velocity.sprint_id
        WHERE s.name LIKE 'ADS %'
        """
    )

    data: dict[int, dict[str, int | str]] = {}
    with engine.connect() as conn:
        for sprint_name, planned_sp, completed_sp in conn.execute(query).fetchall():
            m = re.search(r"(\d+)$", sprint_name or "")
            if not m:
                continue
            sprint_num = int(m.group(1))
            data[sprint_num] = {
                "name": sprint_name,
                "plan": int(planned_sp or 0),
                "fact": int(completed_sp or 0),
            }
    return data


def main() -> None:
    md_data = parse_markdown_velocity(Path("sprints_velocity.md"))
    db_data = load_db_velocity()

    print("sprint_num,md_plan,md_fact,db_plan,db_fact,delta_plan,delta_fact,status")
    for sprint_num in sorted(md_data.keys()):
        md = md_data[sprint_num]
        db = db_data.get(sprint_num)
        if not db:
            print(
                f"{sprint_num},{md['plan']},{md['fact']},N/A,N/A,N/A,N/A,MISSING_IN_DB"
            )
            continue

        delta_plan = int(db["plan"]) - md["plan"]
        delta_fact = int(db["fact"]) - md["fact"]
        status = "OK" if delta_plan == 0 and delta_fact == 0 else "DIFF"
        print(
            f"{sprint_num},{md['plan']},{md['fact']},"
            f"{int(db['plan'])},{int(db['fact'])},"
            f"{delta_plan:+},{delta_fact:+},{status}"
        )


if __name__ == "__main__":
    main()
