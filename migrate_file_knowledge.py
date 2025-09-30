"""
Migration script to add status, char_count, word_count, and created_at columns to knowledge_files table.
Run this script to update the database schema.
"""

from sqlalchemy import text
from src.api.database.database import engine
import sys

def run_migration():
    """Run the migration to add missing columns to knowledge_files table."""

    migration_sql = """
    -- Add status column with default value
    ALTER TABLE knowledge_files
    ADD COLUMN IF NOT EXISTS status VARCHAR NOT NULL DEFAULT 'completed';

    -- Add char_count column
    ALTER TABLE knowledge_files
    ADD COLUMN IF NOT EXISTS char_count INTEGER NULL;

    -- Add word_count column
    ALTER TABLE knowledge_files
    ADD COLUMN IF NOT EXISTS word_count INTEGER NULL;

    -- Add created_at column with default value
    ALTER TABLE knowledge_files
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
    """

    try:
        with engine.connect() as connection:
            print("Running migration to add columns to knowledge_files table...")

            # Execute each statement separately
            statements = [s.strip() for s in migration_sql.split(';') if s.strip()]
            for statement in statements:
                print(f"Executing: {statement[:50]}...")
                connection.execute(text(statement))

            connection.commit()
            print("✓ Migration completed successfully!")

            # Verify the changes
            print("\nVerifying columns in knowledge_files table:")
            result = connection.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'knowledge_files'
                ORDER BY ordinal_position
            """))

            print("\nColumns in knowledge_files table:")
            print("-" * 80)
            for row in result:
                print(f"  {row[0]:<20} {row[1]:<25} nullable={row[2]:<5} default={row[3]}")
            print("-" * 80)

            return True

    except Exception as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)