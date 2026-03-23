-- Migration to fix field_keys unique constraint
-- Remove UNIQUE(project_id, name) to allow multiple fields with same name but different keys
-- (e.g. multiple custom fields across different projects synced to same clean layer)

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'field_keys_project_id_name_key'
        AND conrelid = 'clean_jira.field_keys'::regclass
    ) THEN
        ALTER TABLE clean_jira.field_keys DROP CONSTRAINT field_keys_project_id_name_key;
    END IF;
END $$;

-- Also try dropping index directly if it was created as an index
DROP INDEX IF EXISTS clean_jira.field_keys_project_id_name_key;
