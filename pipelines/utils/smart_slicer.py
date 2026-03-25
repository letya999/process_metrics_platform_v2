import logging
from typing import Dict, List, Optional, Tuple

import polars as pl
from sqlalchemy import Engine, inspect


class SmartSlicer:
    """
    Dynamic Slicing Engine that resolves join paths based on database Foreign Keys.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.logger = logging.getLogger("SmartSlicer")
        self._schema_cache: Optional[Dict[str, List[Tuple[str, str, str]]]] = None
        self._columns_cache: Dict[str, List[str]] = {}

    def _get_schema_graph(
        self, schema: str = "clean_jira"
    ) -> Dict[str, List[Tuple[str, str, str]]]:
        """
        Builds an adjacency list of tables based on Foreign Keys.
        Returns: { 'table_a': [('table_b', 'a_col', 'b_col'), ...] }
        """
        if self._schema_cache is not None:
            return self._schema_cache

        inspector = inspect(self.engine)
        graph = {}

        for table_name in inspector.get_table_names(schema=schema):
            full_name = f"{schema}.{table_name}"
            if full_name not in graph:
                graph[full_name] = []

            # Get Foreign Keys originating from this table
            fks = inspector.get_foreign_keys(table_name, schema=schema)
            for fk in fks:
                referred_table = (
                    f"{fk['referred_schema'] or schema}.{fk['referred_table']}"
                )
                # Path: table -> referred (Outbound)
                for local_col, ref_col in zip(
                    fk["constrained_columns"], fk["referred_columns"], strict=False
                ):
                    graph[full_name].append((referred_table, local_col, ref_col))

                    # Also add Inbound path for reverse traversal
                    if referred_table not in graph:
                        graph[referred_table] = []
                    graph[referred_table].append((full_name, ref_col, local_col))

        self._schema_cache = graph
        return graph

    def _find_path(
        self, start_table: str, end_table: str
    ) -> Optional[List[Tuple[str, str, str]]]:
        """
        Finds the shortest path between two tables using BFS.
        """
        graph = self._get_schema_graph()
        if start_table not in graph or end_table not in graph:
            return None

        queue = [[(start_table, None, None)]]
        visited = {start_table}

        while queue:
            path = queue.pop(0)
            current_table = path[-1][0]

            if current_table == end_table:
                return path[1:]  # Return edges (skip start node)

            for neighbor, local_col, ref_col in graph.get(current_table, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append((neighbor, local_col, ref_col))
                    queue.append(new_path)
        return None

    def _get_table_columns(self, schema: str, table_name: str) -> List[str]:
        """Get column names for a table, using cache if available."""
        full_name = f"{schema}.{table_name}"
        if full_name in self._columns_cache:
            return self._columns_cache[full_name]

        inspector = inspect(self.engine)
        try:
            cols = [c["name"] for c in inspector.get_columns(table_name, schema=schema)]
            self._columns_cache[full_name] = cols
            return cols
        except Exception:
            return []

    def get_slice_mapping(
        self, source_table: str, target_column: str
    ) -> Optional[pl.DataFrame]:
        """
        Dynamically resolves the join path and returns a mapping DataFrame [source_id, slice_value].
        Example: target_column = "clean_jira.issue_types.name"
        """
        try:
            parts = target_column.split(".")
            if len(parts) < 3:
                self.logger.error(
                    f"Invalid target_column format: {target_column}. Expected schema.table.column"
                )
                return None

            schema, target_table_name, col_name = parts[0], parts[1], parts[2]
            target_table = f"{schema}.{target_table_name}"

            # 1. Validation: Check if columns/tables exist
            cols = self._get_table_columns(schema, target_table_name)
            if not cols:
                self.logger.warning(
                    f"Slicing skipped: Table {target_table} not found or empty."
                )
                return None

            if col_name not in cols:
                self.logger.warning(
                    f"Slicing skipped: Column {col_name} not found in {target_table}."
                )
                return None

            # 2. Pathfinding
            if source_table == target_table:
                # Direct column in the same table
                query = f"SELECT CAST(id AS TEXT) AS source_id, {col_name} AS slice_value FROM {source_table}"  # noqa: S608
            else:
                path = self._find_path(source_table, target_table)
                if not path:
                    self.logger.warning(
                        f"Slicing skipped: No path found between {source_table} and {target_table}"
                    )
                    return None

                # 3. SQL Construction — CAST UUID to TEXT so Polars gets strings, not Object
                sql_parts = [
                    f"SELECT CAST(t0.id AS TEXT) AS source_id, t{len(path)}.{col_name} AS slice_value"
                ]
                sql_parts.append(f"FROM {source_table} t0")

                for i, (_, local_col, ref_col) in enumerate(path):
                    next_table = path[i][0]
                    sql_parts.append(
                        f"JOIN {next_table} t{i + 1} ON t{i}.{local_col} = t{i + 1}.{ref_col}"
                    )

                query = " ".join(sql_parts)  # noqa: S608

            # 4. Execution
            with self.engine.connect() as conn:
                return pl.read_database(query, conn)

        except Exception as e:
            self.logger.error(f"Error resolving slice mapping: {e}")
            return None

    def find_target_for_column(self, source_table: str, col_name: str) -> Optional[str]:
        """
        Search FK-adjacent tables (1 hop) for a table containing col_name.
        Returns schema.table.col_name string for get_slice_mapping, or None.
        """
        graph = self._get_schema_graph()

        # Check source table itself first
        src_table_parts = source_table.split(".")
        if len(src_table_parts) >= 2:
            src_schema = src_table_parts[0]
            src_table_name = src_table_parts[1]
            src_cols = self._get_table_columns(src_schema, src_table_name)
            if col_name in src_cols:
                return f"{source_table}.{col_name}"

        # Check FK neighbors (1 hop)
        for neighbor, _, _ in graph.get(source_table, []):
            neighbor_parts = neighbor.split(".")
            if len(neighbor_parts) < 2:
                continue
            neighbor_schema = neighbor_parts[0]
            neighbor_table = neighbor_parts[1]
            try:
                neighbor_cols = self._get_table_columns(neighbor_schema, neighbor_table)
                if col_name in neighbor_cols:
                    return f"{neighbor}.{col_name}"
            except Exception as e:
                self.logger.debug(f"Error inspecting neighbor {neighbor}: {e}")
                continue
        return None
