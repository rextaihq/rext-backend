#!/usr/bin/env python3
"""
Data Verification Script for Wrext Backend Database

This script verifies that the dummy data was created successfully
and provides a detailed summary of what's available for frontend testing.

Uses direct SQL queries to avoid model import issues.

Run with: python verify_dummy_data.py
"""

import os
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from collections import defaultdict

# Load environment variables
load_dotenv()

# Database setup
SQLALCHEMY_DATABASE_URL = os.getenv("POSTGRES_URI_CUSTOM")
if not SQLALCHEMY_DATABASE_URL:
    print("❌ Error: POSTGRES_URI_CUSTOM environment variable not set")
    exit(1)

engine = create_engine(SQLALCHEMY_DATABASE_URL)

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"

def verify_data():
    """Verify all dummy data was created successfully using direct SQL"""

    with engine.connect() as connection:
        print("🔍 Verifying dummy data in Wrext Backend Database...")
        print("=" * 70)

        # Check users
        users_result = connection.execute(text("""
            SELECT email, display_name, first_name, last_name, status, email_verified, created_at
            FROM users
            ORDER BY created_at
        """))
        users = list(users_result)

        print(f"👥 Users: {len(users)}")
        for user in users:
            display_name = user.display_name or f"{user.first_name or ''} {user.last_name or ''}".strip() or "No name"
            status_icon = "✅" if user.email_verified else "❌"
            print(f"   {status_icon} {user.email} ({display_name}) - Status: {user.status}")

        print()

        # Check workspaces with owners
        workspaces_result = connection.execute(text("""
            SELECT w.name, w.description, w.url, w.created_at,
                   u.display_name as owner_name, u.email as owner_email
            FROM workspace w
            LEFT JOIN users u ON w.user_id = u.id
            ORDER BY w.created_at
        """))
        workspaces = list(workspaces_result)

        print(f"🏢 Workspaces: {len(workspaces)}")
        for workspace in workspaces:
            owner_name = workspace.owner_name or "Unknown Owner"
            print(f"   • {workspace.name}")
            print(f"     URL: {workspace.url}")
            print(f"     Owner: {owner_name} ({workspace.owner_email})")
            print(f"     Description: {workspace.description[:80]}{'...' if len(workspace.description) > 80 else ''}")

        print()

        # Check brand voices
        brand_voices_result = connection.execute(text("""
            SELECT bv.*, w.name as workspace_name
            FROM brand_voice bv
            JOIN workspace w ON bv.workspace_id = w.id
            ORDER BY w.name
        """))
        brand_voices = list(brand_voices_result)

        print(f"🎯 Brand Voices: {len(brand_voices)}")
        for bv in brand_voices:
            # Parse JSON fields
            try:
                target_audience = json.loads(bv.target_audience) if bv.target_audience else []
                brand_voice_attrs = json.loads(bv.brand_voice) if bv.brand_voice else []
                competitors = json.loads(bv.competitors) if bv.competitors else []
                content_strategy = json.loads(bv.content_strategy) if bv.content_strategy else []
            except (json.JSONDecodeError, TypeError):
                target_audience = brand_voice_attrs = competitors = content_strategy = []

            print(f"   • {bv.workspace_name}")
            print(f"     Target Audience: {len(target_audience)} segments")
            print(f"     Brand Voice: {len(brand_voice_attrs)} characteristics")
            print(f"     Competitors: {len(competitors)} listed")
            print(f"     Content Strategy: {len(content_strategy)} pillars")
            print(f"     About: {bv.about[:100]}{'...' if len(bv.about) > 100 else ''}")

        print()

        # Check web knowledge with detailed status info
        websites_result = connection.execute(text("""
            SELECT ws.url, ws.status, ws.word_count, ws.char_count, w.name as workspace_name
            FROM website ws
            JOIN workspace w ON ws.workspace_id = w.id
            ORDER BY w.name, ws.url
        """))
        websites = list(websites_result)

        print(f"🌐 Web Knowledge: {len(websites)}")
        status_counts = defaultdict(int)

        for website in websites:
            status_counts[website.status] += 1
            status_icon = {
                'completed': '✅',
                'scraping': '🔄',
                'processing': '⚙️',
                'pending': '⏳',
                'failed': '❌'
            }.get(website.status, '❓')

            print(f"   {status_icon} {website.url}")
            print(f"     Workspace: {website.workspace_name}")
            print(f"     Status: {website.status}")
            if website.word_count and website.char_count:
                print(f"     Content: {website.word_count} words, {website.char_count} chars")

        print(f"\n   📊 Status Distribution:")
        for status, count in sorted(status_counts.items()):
            icon = {
                'completed': '✅',
                'scraping': '🔄',
                'processing': '⚙️',
                'pending': '⏳',
                'failed': '❌'
            }.get(status, '❓')
            print(f"     {icon} {status}: {count}")

        print()

        # Check file knowledge with file type analysis
        files_result = connection.execute(text("""
            SELECT kf.file_name, kf.file_type, kf.file_size, kf.file_path,
                   w.name as workspace_name
            FROM knowledge_files kf
            JOIN workspace w ON kf.workspace_id = w.id
            ORDER BY w.name, kf.file_name
        """))
        files = list(files_result)

        print(f"📁 File Knowledge: {len(files)}")
        file_types = defaultdict(int)
        total_size = 0
        workspace_files = defaultdict(list)

        for file in files:
            file_types[file.file_type] += 1
            total_size += file.file_size
            workspace_files[file.workspace_name].append(file)

        # Show files by workspace
        for workspace_name, workspace_file_list in workspace_files.items():
            print(f"\n   📂 {workspace_name}:")
            for file in workspace_file_list:
                file_icon = {
                    'application/pdf': '📄',
                    'text/plain': '📝',
                    'text/markdown': '📋',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '📘',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '📊',
                    'application/vnd.openxmlformats-officedocument.presentationml.presentation': '📑'
                }.get(file.file_type, '📎')

                print(f"     {file_icon} {file.file_name} ({format_file_size(file.file_size)})")

        print(f"\n   📊 File Type Distribution:")
        for file_type, count in sorted(file_types.items()):
            file_icon = {
                'application/pdf': '📄',
                'text/plain': '📝',
                'text/markdown': '📋'
            }.get(file_type, '📎')
            short_type = file_type.split('/')[-1].upper()
            if 'officedocument' in file_type:
                if 'wordprocessing' in file_type:
                    short_type, file_icon = 'DOCX', '📘'
                elif 'spreadsheet' in file_type:
                    short_type, file_icon = 'XLSX', '📊'
                elif 'presentation' in file_type:
                    short_type, file_icon = 'PPTX', '📑'
            print(f"     {file_icon} {short_type}: {count} files")

        print(f"   💾 Total Size: {format_file_size(total_size)}")

        print()

        # Check text knowledge with content analysis
        texts_result = connection.execute(text("""
            SELECT tk.content, w.name as workspace_name
            FROM text_knowledge tk
            JOIN workspace w ON tk.workspace_id = w.id
            ORDER BY w.name, LENGTH(tk.content) DESC
        """))
        texts = list(texts_result)

        print(f"📝 Text Knowledge: {len(texts)}")
        total_text_length = 0
        workspace_texts = defaultdict(list)

        for text_entry in texts:
            total_text_length += len(text_entry.content)
            workspace_texts[text_entry.workspace_name].append(text_entry)

        # Show text content by workspace
        for workspace_name, workspace_text_list in workspace_texts.items():
            print(f"\n   📝 {workspace_name} ({len(workspace_text_list)} entries):")
            for i, text_entry in enumerate(workspace_text_list, 1):
                content_length = len(text_entry.content)
                word_count = len(text_entry.content.split())

                # Extract title from content (first line that looks like a title)
                lines = text_entry.content.split('\n')
                title = "Untitled"
                for line in lines:
                    line = line.strip()
                    if line.startswith('#'):
                        title = line.replace('#', '').strip()
                        break
                    elif line and not line.startswith('-') and not line.startswith('*'):
                        title = line[:50] + ('...' if len(line) > 50 else '')
                        break

                print(f"     • {title}")
                print(f"       Length: {content_length} chars, ~{word_count} words")

        print(f"\n   📊 Text Content Summary:")
        print(f"     Total Characters: {total_text_length:,}")
        print(f"     Average Length: {total_text_length // len(texts) if texts else 0:,} chars per entry")

        print("\n" + "=" * 70)
        print("✅ Data verification completed successfully!")

        # Summary for frontend testing
        print(f"\n🚀 Frontend Testing Summary:")
        print(f"   👥 {len(users)} test users available")
        print(f"   🏢 {len(workspaces)} workspaces with rich content")
        print(f"   🌐 {len(websites)} web knowledge entries in various states")
        print(f"   📁 {len(files)} file uploads across different types")
        print(f"   📝 {len(texts)} text content pieces")
        print(f"   🎯 {len(brand_voices)} brand voices with complete data")

        print(f"\n📋 Test Scenarios Available:")
        print(f"   • Workspace navigation and details")
        print(f"   • Web knowledge with different statuses ({', '.join(status_counts.keys())})")
        print(f"   • File management across {len(file_types)} file types")
        print(f"   • Text content with varying lengths")
        print(f"   • Brand voice display with rich metadata")
        print(f"   • Search and filtering across all knowledge types")

        print(f"\n🔑 Test User Credentials (password: 'password123'):")
        for user in users:
            display_name = user.display_name or f"{user.first_name or ''} {user.last_name or ''}".strip()
            if display_name and display_name != "No name":
                print(f"   • {user.email} → {display_name}")
            else:
                print(f"   • {user.email}")

        # Special highlight for primary test user
        primary_users = [u for u in users if 'test@example.com' in u.email]
        if primary_users:
            print(f"\n⭐ Recommended Primary Test User: test@example.com")

if __name__ == "__main__":
    try:
        verify_data()
    except Exception as e:
        print(f"❌ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        exit(1)