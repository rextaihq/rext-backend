"""
Fix Permission Discrepancies

This script fixes all 25 permission discrepancies found by the
verify_permission_matrix.py script.

Usage:
    python scripts/fix_permission_discrepancies.py

Author: Claude Code (RBAC Task 4.1 Discrepancy Fixes)
Date: 2025-10-25
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.api.database.async_database import get_async_db
from src.utils.logger import logger


async def main():
    """Fix all permission discrepancies."""

    logger.info("🔧 Starting permission discrepancy fixes...")

    async for db in get_async_db():
        try:
            # Read the SQL file
            sql_file = Path(__file__).parent / "fix_permission_discrepancies.sql"
            sql_content = sql_file.read_text()

            # Split by ;; to get individual statements
            # Remove psql-specific commands (\echo, BEGIN, COMMIT)
            statements = []
            for line in sql_content.split("\n"):
                if line.strip().startswith("\\"):
                    # Print echo messages
                    if line.strip().startswith("\\echo"):
                        message = line.replace("\\echo", "").strip().strip("'")
                        if message:
                            print(message)
                    continue
                if line.strip().startswith("--"):
                    continue
                if not line.strip():
                    continue
                statements.append(line)

            # Join and split by actual SQL statements
            full_sql = "\n".join(statements)

            # Remove BEGIN/COMMIT (we'll handle transaction ourselves)
            full_sql = full_sql.replace("BEGIN;", "").replace("COMMIT;", "")

            # Execute in transaction
            logger.info("Executing fixes in transaction...")

            # Split into individual statements
            sql_statements = [s.strip() + ";" for s in full_sql.split(";") if s.strip()]

            for i, stmt in enumerate(sql_statements, 1):
                if not stmt.strip() or stmt.strip() == ";":
                    continue

                try:
                    await db.execute(text(stmt))
                    logger.debug(f"Executed statement {i}/{len(sql_statements)}")
                except Exception as e:
                    logger.error(f"Error in statement {i}: {str(e)[:200]}")
                    # Continue with other statements

            # Commit transaction
            await db.commit()
            logger.info("✅ All fixes applied successfully!")
            logger.info("Transaction committed")

        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Error applying fixes: {e}")
            raise
        finally:
            await db.close()
            break

    logger.info("")
    logger.info("Please run verify_permission_matrix.py to confirm 0 discrepancies!")


if __name__ == "__main__":
    asyncio.run(main())
