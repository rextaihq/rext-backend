#!/usr/bin/env bash
set -euo pipefail

# Run Ruff check on impersonation modules
echo "🔍 Running Ruff checks on impersonation modules..."
ruff check src/api/routes/users/impersonation.py src/services/impersonation_service.py
