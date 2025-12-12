#!/bin/bash
# Reset database from scratch for fresh MVP deployment
# WARNING: This will delete all data!

set -e

echo "=========================================="
echo "🔄 Process Metrics Platform - DB Reset"
echo "=========================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Stop containers
echo -e "${YELLOW}[1/5] Stopping Docker containers...${NC}"
docker compose down -v 2>/dev/null || true
sleep 2

# Step 2: Start fresh containers
echo -e "${YELLOW}[2/5] Starting fresh Docker containers...${NC}"
docker compose up -d --build postgres app
sleep 10

# Step 3: Wait for database
echo -e "${YELLOW}[3/5] Waiting for database to be ready...${NC}"
for i in {1..30}; do
    if docker compose exec -T postgres pg_isready -U postgres &> /dev/null; then
        echo -e "${GREEN}✓ Database is ready${NC}"
        break
    fi
    echo "  Attempt $i/30..."
    sleep 1
done

# Step 4: Run init script
echo -e "${YELLOW}[4/5] Running database initialization script...${NC}"
docker compose exec -T postgres psql -U postgres < /db/init/01_create_schemas.sql

# Step 5: Run migrations
echo -e "${YELLOW}[5/5] Running Alembic migrations...${NC}"
docker compose exec app alembic upgrade head

echo ""
echo -e "${GREEN}=========================================="
echo "✅ Database reset complete!"
echo "==========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Configure Jira credentials in .env"
echo "2. Go to Dagster UI: http://localhost:3000"
echo "3. Trigger jira_sync job to load data"
echo "4. View dashboards in Metabase: http://localhost:3001"
