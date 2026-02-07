"""Check suspicious velocity sprints."""

import os

from sqlalchemy import create_engine, text

# Database connection
db_url = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/process_metrics"
)
engine = create_engine(db_url)

query = text(
    """
    SELECT
        iteration_name,
        project_id,
        planned_story_points,
        completed_story_points,
        ROUND(completed_story_points / NULLIF(planned_story_points, 0), 2) as ratio,
        planned_issues,
        completed_issues
    FROM metrics.fact_velocity
    WHERE planned_story_points > 10
      AND completed_story_points > planned_story_points * 5.0
    ORDER BY ratio DESC
"""
)

with engine.connect() as conn:
    result = conn.execute(query)
    rows = result.fetchall()

    print(f"\n🔍 Found {len(rows)} suspicious sprints:\n")
    print(
        f"{'Sprint':<30} {'Project':<15} {'Plan SP':>10} {'Fact SP':>10} {'Ratio':>8} {'Plan Issues':>12} {'Fact Issues':>12}"
    )
    print("=" * 120)

    for row in rows:
        print(
            f"{row[0]:<30} {row[1]:<15} {row[2]:>10.1f} {row[3]:>10.1f} {row[4]:>8.1f}x {row[5]:>12} {row[6]:>12}"
        )
