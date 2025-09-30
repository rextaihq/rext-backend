-- Migration: Add status, char_count, word_count, and created_at columns to knowledge_files table
-- Run this SQL script against your PostgreSQL database

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

-- Optional: Update existing rows to set created_at to current timestamp if they don't have one
-- This is handled by the DEFAULT clause above, but you can run this if needed:
-- UPDATE knowledge_files SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;

-- Verify the changes
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'knowledge_files'
-- ORDER BY ordinal_position;