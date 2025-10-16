#!/bin/bash
#
# Quick Stop Script
# Stops all Docker containers
#

echo "🛑 Stopping all Docker containers..."
docker-compose stop

echo "✅ All services stopped!"
echo ""
echo "To start again, run: ./start-dev.sh"
