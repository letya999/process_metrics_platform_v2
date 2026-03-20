import os
import sys

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add project root to path to allow importing pipelines
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipelines.calculations.slicing_utils import get_slice_rules
from pipelines.utils.smart_slicer import SmartSlicer

load_dotenv()


def get_engine():
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "process_metrics_v2")
    DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(DATABASE_URL)


def run_diagnostics():
    engine = get_engine()
    print("--- STEP 1: DB STATE ---")
    with engine.connect() as conn:
        print("\n[metrics.slice_rules]")
        res = conn.execute(text("SELECT * FROM metrics.slice_rules"))
        df_rules = pd.DataFrame(res.fetchall(), columns=res.keys())
        print(df_rules)

        print("\n[metrics.definitions for velocity]")
        res = conn.execute(
            text("SELECT * FROM metrics.definitions WHERE metric_code='velocity'")
        )
        df_def = pd.DataFrame(res.fetchall(), columns=res.keys())
        print(df_def)

        velocity_def_id = None
        if not df_def.empty:
            velocity_def_id = df_def.iloc[0]["id"]

        print("\n[fact_values slice counts]")
        res = conn.execute(
            text(
                "SELECT count(*) FROM metrics.fact_values WHERE slice_rule_id IS NOT NULL"
            )
        )
        print(f"Count WITH slice_rule_id: {res.scalar()}")
        res = conn.execute(
            text("SELECT count(*) FROM metrics.fact_values WHERE slice_rule_id IS NULL")
        )
        print(f"Count WITHOUT slice_rule_id: {res.scalar()}")

    print("\n--- STEP 2: get_slice_rules simulation ---")
    if velocity_def_id:
        print(f"Getting rules for velocity def_id={velocity_def_id}")
        rules_df = get_slice_rules(engine, target_definition_id=velocity_def_id)
        print(rules_df)
        if rules_df.empty:
            print(f"PROBLEM: no rules returned for velocity def_id={velocity_def_id}")
    else:
        print("SKIP: velocity definition not found")
        rules_df = pd.DataFrame()

    print("\n--- STEP 3: SmartSlicer path test ---")
    slicer = SmartSlicer(engine)
    source_table = "clean_jira.issues"

    if not rules_df.empty:
        for _, rule in rules_df.iterrows():
            group_by_col = rule["group_by_source_column"]
            source_rule_table = rule["source_table"]
            full_target = f"{source_rule_table}.{group_by_col}"

            print(
                f"\nTesting resolution for rule '{rule['rule_name']}' targetting {full_target}"
            )
            # SmartSlicer.find_target_for_column expects (source_table, group_by_column)
            # but wait, plan says find_target_for_column('clean_jira.issues', rule.group_by_column)
            # but rule.group_by_column in SmartSlicer context is the target column in the target table.

            # SmartSlicer logic:
            # find_target_for_column(self, table_name, column_name) -> Optional[str]
            # Returns the target table that has this column_name and is reachable from table_name

            target_full = slicer.find_target_for_column(source_table, group_by_col)
            print(f"Resolved target: {target_full}")

            if target_full:
                mapping = slicer.get_slice_mapping(source_table, target_full)
                if mapping is not None and not mapping.is_empty():
                    print("Mapping found! Head(5):")
                    print(mapping.head(5))
                elif mapping is None:
                    print("PROBLEM: Mapping is None (error during resolution)")
                else:
                    print("PROBLEM: Mapping is empty")
            else:
                print(
                    f"PROBLEM: cannot resolve column {group_by_col} from {source_table}"
                )
    else:
        print("SKIP: No rules to test")

    print("\n--- STEP 4: issues_for_slicing test ---")
    with engine.connect() as conn:
        query = text(
            """
            SELECT i.id, i.project_id, it.name AS type_name
            FROM clean_jira.issues i
            LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
            LIMIT 5
        """
        )
        res = conn.execute(query)
        rows = res.fetchall()
        print("\nSample from issues join types:")
        for row in rows:
            print(row)

        res = conn.execute(
            text(
                "SELECT DISTINCT it.name FROM clean_jira.issues i LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id"
            )
        )
        types = [r[0] for r in res.fetchall()]
        print(f"\nUnique type_name values: {types}")
        print(f"issue_type alias would produce: {types}")

    print("\n--- STEP 5: Full trace ---")
    with engine.connect() as conn:
        res = conn.execute(
            text(
                "SELECT * FROM metrics.v_facts WHERE slice_rule_name IS NOT NULL LIMIT 5"
            )
        )
        df_vfacts = pd.DataFrame(res.fetchall(), columns=res.keys())
        if df_vfacts.empty:
            print("PROBLEM: No sliced facts in v_facts")
        else:
            print("Sliced facts in v_facts (head 5):")
            print(df_vfacts)


if __name__ == "__main__":
    run_diagnostics()
