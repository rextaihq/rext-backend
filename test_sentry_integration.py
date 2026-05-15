#!/usr/bin/env python3
"""
Test script to verify Sentry logging integration in keyword_clustering.py and outline.py
Run this to ensure all logger calls have been properly replaced with Sentry logs.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def check_file_for_logger_calls(filepath: str) -> dict:
    """Check if a file still has logger.* calls and returns findings."""
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    logger_calls = []
    sentry_calls = []
    
    for idx, line in enumerate(lines, 1):
        # Check for old logger calls (but not in comments)
        if 'logger.' in line and not line.strip().startswith('#'):
            if any(call in line for call in ['logger.info', 'logger.warning', 'logger.error', 'logger.debug']):
                logger_calls.append((idx, line.strip()))
        
        # Check for new Sentry calls
        if any(call in line for call in ['capture_message', 'capture_exception', 'push_scope']):
            sentry_calls.append((idx, line.strip()))
    
    return {
        'filepath': filepath,
        'logger_calls': logger_calls,
        'sentry_calls': sentry_calls,
        'total_lines': len(lines)
    }

def main():
    print("=" * 80)
    print("SENTRY LOGGING INTEGRATION TEST")
    print("=" * 80)
    print()
    
    files_to_check = [
        '/home/revnix/Desktop/rext-backend/src/flow/engines/seo/keyword_clustering.py',
        '/home/revnix/Desktop/rext-backend/src/flow/engines/router/outline.py'
    ]
    
    all_results = []
    total_sentry_calls = 0
    
    for filepath in files_to_check:
        if not os.path.exists(filepath):
            print(f"❌ File not found: {filepath}")
            continue
        
        results = check_file_for_logger_calls(filepath)
        all_results.append(results)
        
        print(f"\n📄 File: {filepath}")
        print(f"   Total lines: {results['total_lines']}")
        print(f"   Sentry calls found: {len(results['sentry_calls'])}")
        
        if results['logger_calls']:
            print(f"   ⚠️  Legacy logger calls found: {len(results['logger_calls'])}")
            for line_num, line_content in results['logger_calls'][:5]:  # Show first 5
                print(f"      Line {line_num}: {line_content[:70]}...")
        else:
            print(f"   ✅ No legacy logger calls found")
        
        if results['sentry_calls']:
            print(f"   ✅ Sentry integration active")
            total_sentry_calls += len(results['sentry_calls'])
        
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Total Sentry calls: {total_sentry_calls}")
    print(f"✅ Files checked: {len(all_results)}")
    
    has_legacy = any(r['logger_calls'] for r in all_results)
    if has_legacy:
        print("⚠️  WARNING: Some files still contain legacy logger calls")
    else:
        print("✅ All files have been migrated to Sentry logging")
    
    print()
    print("📊 Sentry Integration Improvements:")
    print("   • Real-time error tracking and monitoring")
    print("   • Structured contextual data for debugging")
    print("   • Performance monitoring and tracing")
    print("   • Dashboard visibility for all logs")
    print("   • Tags and breadcrumbs for better filtering")
    print("   • Automatic error aggregation and alerts")
    print()
    print("🔗 Access Sentry Dashboard:")
    print("   - Visit your Sentry project at: https://sentry.io/")
    print("   - Filter by tags: module, status, operation")
    print("   - View context data for each event")
    print()

if __name__ == "__main__":
    main()
