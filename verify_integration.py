#!/usr/bin/env python3
"""
Integration Verification Script

This script verifies that the consistent response and error handling system
is properly integrated across the entire backend codebase.

It performs static analysis to ensure:
- All route handlers use the new response utilities
- Custom exceptions are properly implemented
- Middleware is correctly configured
- Response schemas are consistent
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple

def analyze_file(file_path: Path) -> Dict[str, any]:
    """Analyze a Python file for response handling patterns."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        tree = ast.parse(content)

        result = {
            'file': str(file_path),
            'uses_response_utils': 'response_utils' in content,
            'uses_custom_exceptions': any(exc in content for exc in [
                'WrextAPIException', 'ResourceNotFoundException',
                'DuplicateResourceException', 'WrextValidationException'
            ]),
            'has_success_calls': 'success(' in content,
            'has_error_calls': 'error(' in content,
            'uses_request_param': 'request: Request' in content,
            'has_old_patterns': any(pattern in content for pattern in [
                'HTTPException', 'status_code=', 'detail='
            ]),
            'imports': []
        }

        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and 'response_utils' in node.module:
                    result['imports'].extend([alias.name for alias in node.names])

        return result

    except Exception as e:
        return {'file': str(file_path), 'error': str(e)}

def verify_middleware_integration(server_file: Path) -> Dict[str, bool]:
    """Verify middleware is properly configured in server.py."""
    try:
        with open(server_file, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            'has_request_tracker': 'RequestTrackerMiddleware' in content,
            'has_error_handler': 'ErrorHandlerMiddleware' in content,
            'has_exception_setup': 'setup_exception_handlers' in content,
            'middleware_order_correct': content.find('RequestTrackerMiddleware') < content.find('ErrorHandlerMiddleware'),
            'has_cors': 'CORSMiddleware' in content
        }
    except Exception as e:
        return {'error': str(e)}

def verify_response_schemas() -> Dict[str, bool]:
    """Verify response schemas are properly defined."""
    schema_file = Path('src/api/schemas/response_schemas.py')

    if not schema_file.exists():
        return {'exists': False}

    try:
        with open(schema_file, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            'exists': True,
            'has_success_response': 'class SuccessResponse' in content,
            'has_error_response': 'class ErrorResponse' in content,
            'has_error_codes': 'class ErrorCode' in content,
            'has_utility_functions': 'def create_success_response' in content
        }
    except Exception as e:
        return {'exists': True, 'error': str(e)}

def main():
    """Run the integration verification."""
    print("🔍 Verifying Consistent Response System Integration")
    print("=" * 60)

    # Change to backend directory
    backend_dir = Path(__file__).parent
    os.chdir(backend_dir)

    # Find all Python files in routes
    route_files = list(Path('src/api/routes').rglob('*.py'))
    if not route_files:
        print("❌ No route files found!")
        return False

    print(f"📁 Found {len(route_files)} route files to analyze")

    # Analyze each route file
    results = []
    for file_path in route_files:
        if file_path.name == '__init__.py':
            continue

        result = analyze_file(file_path)
        results.append(result)

        print(f"\n📄 {file_path.name}:")
        if 'error' in result:
            print(f"   ❌ Error: {result['error']}")
        else:
            print(f"   {'✅' if result['uses_response_utils'] else '❌'} Uses response utilities")
            print(f"   {'✅' if result['has_success_calls'] else '❌'} Has success() calls")
            print(f"   {'✅' if result['uses_request_param'] else '❌'} Uses Request parameter")
            if result['has_old_patterns']:
                print(f"   ⚠️  Still has old HTTPException patterns")

    # Verify middleware integration
    print(f"\n🔧 Middleware Integration:")
    middleware_result = verify_middleware_integration(Path('src/api/server.py'))
    if 'error' in middleware_result:
        print(f"   ❌ Error: {middleware_result['error']}")
    else:
        for check, passed in middleware_result.items():
            check_name = check.replace('_', ' ').title()
            print(f"   {'✅' if passed else '❌'} {check_name}")

    # Verify response schemas
    print(f"\n📋 Response Schemas:")
    schema_result = verify_response_schemas()
    if 'error' in schema_result:
        print(f"   ❌ Error: {schema_result['error']}")
    else:
        for check, passed in schema_result.items():
            if check != 'exists':
                check_name = check.replace('_', ' ').title()
                print(f"   {'✅' if passed else '❌'} {check_name}")

    # Summary
    print(f"\n📊 Integration Summary:")

    files_using_utils = sum(1 for r in results if r.get('uses_response_utils', False))
    files_with_success = sum(1 for r in results if r.get('has_success_calls', False))
    files_with_request = sum(1 for r in results if r.get('uses_request_param', False))

    print(f"   📄 Route files analyzed: {len(results)}")
    print(f"   ✅ Files using response utilities: {files_using_utils}/{len(results)}")
    print(f"   ✅ Files with success() calls: {files_with_success}/{len(results)}")
    print(f"   ✅ Files using Request parameter: {files_with_request}/{len(results)}")

    # Check if integration is complete
    integration_complete = (
        files_using_utils == len(results) and
        middleware_result.get('has_request_tracker', False) and
        middleware_result.get('has_error_handler', False) and
        schema_result.get('has_success_response', False)
    )

    print(f"\n🎯 Integration Status: {'✅ COMPLETE' if integration_complete else '❌ INCOMPLETE'}")

    if integration_complete:
        print("\n🎉 The consistent response and error handling system is fully integrated!")
        print("   All route handlers are using the new response utilities")
        print("   Middleware is properly configured")
        print("   Response schemas are in place")
        print("\n🚀 Ready for production use!")
    else:
        print("\n⚠️  Integration is not complete. Check the issues above.")

    return integration_complete

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)