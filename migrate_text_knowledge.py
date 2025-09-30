"""
Migration script to add title, tags, metadata, created_at, and updated_at columns to text_knowledge table.
Run this script to update the database schema.
"""

from sqlalchemy import text
from src.api.database.database import engine
import sys

def run_migration():
    """Run the migration to add missing columns to text_knowledge table."""

    migration_sql = """
    -- Add title column with default value
    ALTER TABLE text_knowledge
    ADD COLUMN IF NOT EXISTS title VARCHAR NOT NULL DEFAULT 'Untitled Note';

    -- Add tags column (JSONB for array of strings)
    ALTER TABLE text_knowledge
    ADD COLUMN IF NOT EXISTS tags JSONB NULL;

    -- Add custom_metadata column (JSONB for key-value pairs)
    -- Note: 'metadata' is reserved in SQLAlchemy, so we use 'custom_metadata'
    ALTER TABLE text_knowledge
    ADD COLUMN IF NOT EXISTS custom_metadata JSONB NULL;

    -- Add created_at column with default value
    ALTER TABLE text_knowledge
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;

    -- Add updated_at column (no default, only set on updates)
    ALTER TABLE text_knowledge
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NULL;
    """

    try:
        with engine.connect() as connection:
            print("Running migration to add columns to text_knowledge table...")

            # Execute each statement separately
            statements = [s.strip() for s in migration_sql.split(';') if s.strip()]
            for statement in statements:
                print(f"Executing: {statement[:50]}...")
                connection.execute(text(statement))

            connection.commit()
            print("✓ Migration completed successfully!")

            # Verify the changes
            print("\nVerifying columns in text_knowledge table:")
            result = connection.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'text_knowledge'
                ORDER BY ordinal_position
            """))

            print("\nColumns in text_knowledge table:")
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