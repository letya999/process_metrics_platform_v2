#!/bin/bash
# =============================================================================
# Process Metrics Platform - Deployment Script
# =============================================================================
# Use this script to deploy the platform to a remote server.
#
# USAGE:
#   ./scripts/deploy.sh                    # Deploy with default settings
#   ./scripts/deploy.sh --build            # Build images locally
#   ./scripts/deploy.sh --pull             # Pull pre-built images
#   ./scripts/deploy.sh --migrate-only     # Only run migrations
#
# PREREQUISITES:
#   1. Docker and Docker Compose installed on target server
#   2. .env.prod file configured
#   3. config/projects.yaml configured with your projects
#
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
ACTION="deploy"  # deploy, build, pull, migrate

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --build) ACTION="build" ;;
        --pull) ACTION="pull" ;;
        --migrate-only) ACTION="migrate" ;;
        --help)
            echo "Usage: $0 [--build|--pull|--migrate-only]"
            exit 0
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Process Metrics Platform - Deployment${NC}"
echo -e "${BLUE}========================================${NC}"

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose not installed${NC}"
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}Error: $COMPOSE_FILE not found${NC}"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: $ENV_FILE not found${NC}"
    echo -e "${YELLOW}Hint: Copy .env.prod.example to .env.prod and configure it${NC}"
    exit 1
fi

if [ ! -f "config/projects.yaml" ]; then
    echo -e "${YELLOW}Warning: config/projects.yaml not found${NC}"
    echo -e "${YELLOW}Using environment variables for Jira configuration${NC}"
fi

echo -e "${GREEN}Prerequisites OK${NC}"

# Use docker compose (v2) or docker-compose (v1)
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# Execute action
case $ACTION in
    build)
        echo -e "\n${YELLOW}Building Docker images...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE build --parallel
        echo -e "${GREEN}Build complete!${NC}"

        echo -e "\n${YELLOW}Starting services...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE up -d
        ;;

    pull)
        echo -e "\n${YELLOW}Pulling Docker images...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE pull
        echo -e "${GREEN}Pull complete!${NC}"

        echo -e "\n${YELLOW}Starting services...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE up -d
        ;;

    migrate)
        echo -e "\n${YELLOW}Running database migrations...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE --profile migration run --rm alembic
        echo -e "${GREEN}Migrations complete!${NC}"
        exit 0
        ;;

    deploy)
        echo -e "\n${YELLOW}Pulling latest images...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE pull 2>/dev/null || true

        echo -e "\n${YELLOW}Starting main services...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE up -d

        echo -e "\n${YELLOW}Waiting for database to be ready...${NC}"
        sleep 10

        echo -e "\n${YELLOW}Running database migrations...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE --profile migration run --rm alembic

        echo -e "\n${YELLOW}Initializing Metabase configuration...${NC}"
        $COMPOSE_CMD -f $COMPOSE_FILE --profile migration run --rm metabase-init
        ;;
esac

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "\n${BLUE}Services:${NC}"
echo -e "  Admin Panel: http://localhost:${APP_PORT:-8000}"
echo -e "  Dagster UI:  http://localhost:${DAGSTER_PORT:-3000}"
echo -e "  Metabase:    http://localhost:${METABASE_PORT:-3001}"

echo -e "\n${BLUE}Useful commands:${NC}"
echo -e "  View logs:     $COMPOSE_CMD -f $COMPOSE_FILE logs -f"
echo -e "  Stop services: $COMPOSE_CMD -f $COMPOSE_FILE down"
echo -e "  Check status:  $COMPOSE_CMD -f $COMPOSE_FILE ps"
