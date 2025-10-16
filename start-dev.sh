#!/bin/bash
#
# Development Server Startup Script
# Starts LangGraph dev server with all dependencies
#

set -e

echo "🚀 Starting Wrext Backend Development Server..."
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running"
    echo "   Please start Docker Desktop and try again"
    exit 1
fi

# Start infrastructure services (Redis, PostgreSQL)
echo "📦 Starting infrastructure services..."
docker-compose up -d redis langgraph-redis langgraph-postgres

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 3

# Check service health
echo "🔍 Checking service health..."
docker-compose ps

echo ""
echo "✅ Infrastructure ready!"
echo ""
echo "🎯 Starting LangGraph dev server..."
echo "   Backend will be available at: http://localhost:2024"
echo "   API Docs: http://localhost:2024/docs"
echo ""

# Start the dev server
.venv/bin/langgraph dev --allow-blocking --no-browser
