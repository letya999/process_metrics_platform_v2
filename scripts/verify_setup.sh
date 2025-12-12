#!/bin/bash
# Verify that all MVP components are correctly set up

set -e

echo "=========================================="
echo "🔍 Verifying MVP Setup"
echo "=========================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check 1: Database migrations
echo -e "${YELLOW}[1/6] Checking database migrations...${NC}"
CURRENT_MIGRATION=$(docker compose exec -T app alembic current 2>/dev/null | grep -oE "0005_" || echo "none")
if [ "$CURRENT_MIGRATION" = "0005_" ]; then
    echo -e "${GREEN}✓ All migrations applied (current: 0005_add_default_jira_project)${NC}"
else
    echo -e "${RED}✗ Migrations not fully applied${NC}"
    exit 1
fi

# Check 2: Platform schema
echo -e "${YELLOW}[2/6] Checking platform schema tables...${NC}"
TABLES=$(docker compose exec -T postgres psql -U postgres -d metrics -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='platform'")
if [ "$TABLES" -gt 0 ]; then
    echo -e "${GREEN}✓ Platform schema has $TABLES tables${NC}"
else
    echo -e "${RED}✗ Platform schema not found${NC}"
    exit 1
fi

# Check 3: Clean Jira schema
echo -e "${YELLOW}[3/6] Checking clean_jira schema...${NC}"
TABLES=$(docker compose exec -T postgres psql -U postgres -d metrics -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='clean_jira'")
if [ "$TABLES" -gt 0 ]; then
    echo -e "${GREEN}✓ Clean Jira schema has $TABLES tables${NC}"
else
    echo -e "${RED}✗ Clean Jira schema not found${NC}"
    exit 1
fi

# Check 4: System user
echo -e "${YELLOW}[4/6] Checking system user...${NC}"
SYSTEM_USER=$(docker compose exec -T postgres psql -U postgres -d metrics -t -c \
    "SELECT count(*) FROM platform.users WHERE email='system@metrics.local'")
if [ "$SYSTEM_USER" -eq 1 ]; then
    echo -e "${GREEN}✓ System user created${NC}"
else
    echo -e "${RED}✗ System user not found${NC}"
    exit 1
fi

# Check 5: Jira integration type
echo -e "${YELLOW}[5/6] Checking Jira integration type...${NC}"
JIRA_INT=$(docker compose exec -T postgres psql -U postgres -d metrics -t -c \
    "SELECT count(*) FROM platform.integration_types WHERE name='jira_cloud'")
if [ "$JIRA_INT" -eq 1 ]; then
    echo -e "${GREEN}✓ Jira integration type registered${NC}"
else
    echo -e "${RED}✗ Jira integration type not found${NC}"
    exit 1
fi

# Check 6: Default Jira project
echo -e "${YELLOW}[6/6] Checking default Jira project...${NC}"
DEFAULT_PROJ=$(docker compose exec -T postgres psql -U postgres -d metrics -t -c \
    "SELECT count(*) FROM platform.projects WHERE id='00000000-0000-0000-0000-000000000001'")
if [ "$DEFAULT_PROJ" -eq 1 ]; then
    echo -e "${GREEN}✓ Default Jira System Project created${NC}"
else
    echo -e "${YELLOW}⚠ Default Jira project not found (will be created on first sync)${NC}"
fi

echo ""
echo -e "${GREEN}=========================================="
echo "✅ MVP Setup Verification Complete!"
echo "==========================================${NC}"
echo ""
echo -e "${BLUE}Services status:${NC}"
echo "  FastAPI Admin:  http://localhost:8000"
echo "  Dagster UI:     http://localhost:3000"
echo "  Metabase:       http://localhost:3001"
echo "  PostgreSQL:     localhost:5432"
