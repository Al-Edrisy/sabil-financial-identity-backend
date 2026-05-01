#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  Sabil Country DBs — Launch & Verify Script
#
#  Usage:
#    chmod +x scripts/run_country_dbs.sh
#    ./scripts/run_country_dbs.sh [up|down|verify|connect-langflow]
#
#  Requirements: Docker Desktop must be running.
# ═══════════════════════════════════════════════════════════════════════════════

set -e

COMPOSE_FILE="docker/country-dbs/docker-compose.country-dbs.yml"
LANGFLOW_CONTAINER="09e4f20b14dd"   # existing Langflow container ID
NETWORK="sabil_country_net"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

banner() { echo -e "\n${CYAN}══════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}══════════════════════════════════════════${NC}\n"; }
ok()     { echo -e "${GREEN}  ✓ $1${NC}"; }
warn()   { echo -e "${YELLOW}  ⚠ $1${NC}"; }
err()    { echo -e "${RED}  ✗ $1${NC}"; }

ACTION="${1:-up}"

case "$ACTION" in

# ─────────────────────────────────────────────────────────────────────────────
up)
  banner "Starting 3 Country PostgreSQL Databases"
  docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
  echo ""
  echo "Waiting for containers to be healthy..."
  sleep 8

  for name in sabil_db_libya sabil_db_yemen sabil_db_egypt; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null || echo "missing")
    if [[ "$STATUS" == "healthy" ]]; then
      ok "$name is healthy"
    else
      warn "$name status: $STATUS (give it a few more seconds)"
    fi
  done

  echo ""
  ok "Libya  DB → postgresql://sabil:sabil123@localhost:5433/sabil_ly"
  ok "Yemen  DB → postgresql://sabil:sabil123@localhost:5434/sabil_ye"
  ok "Egypt  DB → postgresql://sabil:sabil123@localhost:5435/sabil_eg"
  echo ""
  warn "Run './scripts/run_country_dbs.sh connect-langflow' to link Langflow to the network."
  ;;

# ─────────────────────────────────────────────────────────────────────────────
down)
  banner "Stopping Country Databases"
  docker compose -f "$COMPOSE_FILE" down
  ok "All country DB containers stopped."
  ;;

# ─────────────────────────────────────────────────────────────────────────────
verify)
  banner "Verifying Seeded Data"

  echo -e "\n${YELLOW}── LIBYA (sabil_ly) ──────────────────────${NC}"
  docker exec sabil_db_libya psql -U sabil -d sabil_ly -c "
    SELECT u.id, u.full_name, u.country_code, s.score, s.risk_level,
           s.avg_monthly_income, s.avg_monthly_expense, s.income_sources
    FROM users u
    JOIN sabil_scores s ON s.user_id = u.id;
  "
  docker exec sabil_db_libya psql -U sabil -d sabil_ly -c "
    SELECT u.full_name, COUNT(t.id) AS tx_count,
           ROUND(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 2) AS total_income,
           ROUND(SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END), 2) AS total_expense
    FROM users u JOIN transactions t ON t.user_id = u.id
    GROUP BY u.full_name;
  "
  docker exec sabil_db_libya psql -U sabil -d sabil_ly -c "
    SELECT u.full_name, r.receipt_date, r.merchant_name, r.total_amount, r.payment_method
    FROM receipts r JOIN users u ON u.id = r.user_id ORDER BY r.receipt_date;
  "

  echo -e "\n${YELLOW}── YEMEN (sabil_ye) ──────────────────────${NC}"
  docker exec sabil_db_yemen psql -U sabil -d sabil_ye -c "
    SELECT u.id, u.full_name, u.country_code, s.score, s.risk_level,
           s.avg_monthly_income, s.avg_monthly_expense, s.income_sources
    FROM users u
    JOIN sabil_scores s ON s.user_id = u.id;
  "
  docker exec sabil_db_yemen psql -U sabil -d sabil_ye -c "
    SELECT u.full_name, COUNT(t.id) AS tx_count,
           ROUND(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 2) AS total_income,
           ROUND(SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END), 2) AS total_expense
    FROM users u JOIN transactions t ON t.user_id = u.id
    GROUP BY u.full_name;
  "
  docker exec sabil_db_yemen psql -U sabil -d sabil_ye -c "
    SELECT u.full_name, r.receipt_date, r.merchant_name, r.total_amount, r.payment_method
    FROM receipts r JOIN users u ON u.id = r.user_id ORDER BY r.receipt_date;
  "

  echo -e "\n${YELLOW}── EGYPT (sabil_eg) ──────────────────────${NC}"
  docker exec sabil_db_egypt psql -U sabil -d sabil_eg -c "
    SELECT u.id, u.full_name, u.country_code, s.score, s.risk_level,
           s.avg_monthly_income, s.avg_monthly_expense, s.income_sources
    FROM users u
    JOIN sabil_scores s ON s.user_id = u.id;
  "
  docker exec sabil_db_egypt psql -U sabil -d sabil_eg -c "
    SELECT u.full_name, COUNT(t.id) AS tx_count,
           ROUND(SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END), 2) AS total_income,
           ROUND(SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END), 2) AS total_expense
    FROM users u JOIN transactions t ON t.user_id = u.id
    GROUP BY u.full_name;
  "
  docker exec sabil_db_egypt psql -U sabil -d sabil_eg -c "
    SELECT u.full_name, r.receipt_date, r.merchant_name, r.total_amount, r.payment_method
    FROM receipts r JOIN users u ON u.id = r.user_id ORDER BY r.receipt_date;
  "

  banner "Verification Complete"
  ;;

# ─────────────────────────────────────────────────────────────────────────────
connect-langflow)
  banner "Connecting Langflow to Country DB Network"

  if ! docker network ls --format '{{.Name}}' | grep -q "^${NETWORK}$"; then
    err "Network $NETWORK does not exist. Run './scripts/run_country_dbs.sh up' first."
    exit 1
  fi

  if docker inspect "$LANGFLOW_CONTAINER" > /dev/null 2>&1; then
    docker network connect "$NETWORK" "$LANGFLOW_CONTAINER" 2>/dev/null || \
      warn "Langflow already connected to $NETWORK (or error)"
    ok "Langflow container ($LANGFLOW_CONTAINER) connected to $NETWORK"
    echo ""
    echo "  Langflow can now reach databases at:"
    ok "  Libya  → host: sabil_db_libya  port: 5432  db: sabil_ly"
    ok "  Yemen  → host: sabil_db_yemen  port: 5432  db: sabil_ye"
    ok "  Egypt  → host: sabil_db_egypt  port: 5432  db: sabil_eg"
    echo "  user: sabil  password: sabil123"
  else
    err "Langflow container '$LANGFLOW_CONTAINER' not found."
    warn "Find your container ID with: docker ps | grep langflow"
  fi
  ;;

*)
  echo "Usage: $0 [up|down|verify|connect-langflow]"
  exit 1
  ;;
esac
