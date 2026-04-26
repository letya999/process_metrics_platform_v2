import json

from sqlalchemy import create_engine, text

DB = "postgresql://pmp_user:bsU2Seggj1ik95Yx_lz4FIxvEtxSvot2azvM7cZOd5A@postgres:5432/process_metrics_v2"
engine = create_engine(DB)

expected = []
for s, c, d in [
    ("Mon Sprint 13", 84, 81),
    ("GM Sprint 42", 128, 19),
    ("Mon Sprint 14", 67, 80),
    ("GM Sprint 43", 2, 73),
    ("Mon Sprint 15", 84, 10),
    ("GM Sprint 44", 56, 7),
    ("GM Sprint 45", 14, 22),
    ("Mon Sprint 16", 3, 77),
    ("TWBACK Sprint 1", 91, 143),
    ("TWBACK Sprint 2", 182, 123),
    ("TWBACK Sprint 3", 151, 86),
    ("TWBACK Sprint 4", 160, 81),
]:
    expected.append(("TWBACKEND", s, float(c), float(d)))
for s, c, d in [
    ("TWNB Sprint 38", 116, 62),
    ("TWNB Sprint 39", 35, 20),
    ("TWNB Sprint 40", 119, 63),
    ("TWNB Sprint 41", 77, 13),
    ("TWNB Sprint 42", 134, 106),
    ("TWNB Sprint 43", 89, 8),
    ("TWNB Sprint 44", 134, 83),
    ("TWNB Sprint 45", 101, 8),
    ("TWNB Sprint 46", 130, 83),
    ("TWNB Sprint 47", 107, 19),
    ("TWNB Sprint 48", 123, 44),
    ("TWNB Sprint 49", 45, 45),
]:
    expected.append(("TWWB", s, float(c), float(d)))
for s, c, d in [
    ("Sprint 31", 85, 45),
    ("Sprint 32", 104, 51),
    ("Sprint 33", 81, 40),
    ("Sprint 34", 83, 46),
    ("Sprint 35", 80, 46),
    ("Sprint 36", 45, 75),
    ("Sprint 37", 92, 49),
    ("Sprint 38", 78, 79),
    ("Sprint 39", 69, 40),
    ("Sprint 40", 87, 25),
    ("Sprint 41", 127, 29),
    ("Sprint 42", 108, 25),
]:
    expected.append(("TWMOB", s, float(c), float(d)))

with engine.begin() as conn:
    calc = dict(
        conn.execute(
            text(
                "SELECT calc_code,id::text FROM metrics.calculations WHERE calc_code IN ('velocity_planned_sp','velocity_completed_sp')"
            )
        ).fetchall()
    )
    projects = (
        conn.execute(
            text(
                "SELECT p.external_key, p.id::text AS project_id, dp.id::text AS project_agg_id FROM clean_jira.projects p JOIN metrics.dim_projects dp ON dp.project_id=p.id"
            )
        )
        .mappings()
        .all()
    )
    pmap = {r["external_key"]: r for r in projects}

    alias = {"TWBACKEND": ["TWBACKEND", "TWBACK"], "TWWB": ["TWWB"], "TWMOB": ["TWMOB"]}
    out = []
    for pkey, sname, exp_p, exp_c in expected:
        pr = None
        for c in alias.get(pkey, [pkey]):
            if c in pmap:
                pr = pmap[c]
                break
        if not pr:
            out.append(
                {
                    "project_key": pkey,
                    "sprint_name": sname,
                    "exp_planned": exp_p,
                    "exp_completed": exp_c,
                    "status": "PROJECT_NOT_FOUND",
                }
            )
            continue

        sprint = conn.execute(
            text(
                "SELECT id::text FROM clean_jira.sprints WHERE project_id=CAST(:pid AS uuid) AND name=:n LIMIT 1"
            ),
            {"pid": pr["project_id"], "n": sname},
        ).scalar()
        if not sprint:
            out.append(
                {
                    "project_key": pr["external_key"],
                    "sprint_name": sname,
                    "exp_planned": exp_p,
                    "exp_completed": exp_c,
                    "status": "SPRINT_NOT_FOUND",
                }
            )
            continue

        rows = (
            conn.execute(
                text(
                    """
            SELECT metric_id::text AS metric_id, value, updated_at
            FROM metrics.fact_values
            WHERE project_agg_id=CAST(:pa AS uuid)
              AND entity_id=:sid
              AND metric_id IN (CAST(:m1 AS uuid),CAST(:m2 AS uuid))
              AND slice_rule_id IS NULL
            ORDER BY updated_at DESC
        """
                ),
                {
                    "pa": pr["project_agg_id"],
                    "sid": sprint,
                    "m1": calc["velocity_planned_sp"],
                    "m2": calc["velocity_completed_sp"],
                },
            )
            .mappings()
            .all()
        )

        latest_p = latest_c = None
        max_p = max_c = 0.0
        cnt_p = cnt_c = 0
        for r in rows:
            if r["metric_id"] == calc["velocity_planned_sp"]:
                cnt_p += 1
                v = float(r["value"] or 0)
                max_p = max(max_p, v)
                if latest_p is None:
                    latest_p = v
            elif r["metric_id"] == calc["velocity_completed_sp"]:
                cnt_c += 1
                v = float(r["value"] or 0)
                max_c = max(max_c, v)
                if latest_c is None:
                    latest_c = v

        out.append(
            {
                "project_key": pr["external_key"],
                "sprint_name": sname,
                "exp_planned": exp_p,
                "exp_completed": exp_c,
                "db_planned": latest_p,
                "db_completed": latest_c,
                "d_planned": None if latest_p is None else round(latest_p - exp_p, 2),
                "d_completed": None if latest_c is None else round(latest_c - exp_c, 2),
                "rows_planned": cnt_p,
                "rows_completed": cnt_c,
                "status": "OK",
            }
        )
print(json.dumps(out, ensure_ascii=False))
