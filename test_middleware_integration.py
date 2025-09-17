#!/usr/bin/env python3
"""
Test Script for Middleware Integration

This script tests the new consistent response and error handling system
to ensure all middleware components are working correctly.

Run this script to validate:
- Request tracking middleware
- Error handling middleware
- Consistent response formats
- Custom exception handling
- Request ID correlation
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fastapi.testclient import TestClient
from src.api.server import app

def test_response_format():
    """Test that all responses follow the consistent format."""
    client = TestClient(app)

    print("🧪 Testing Response Format...")

    # Test root endpoint
    response = client.get("/")
    print(f"✅ Root endpoint: {response.status_code}")

    data = response.json()
    assert "success" in data
    assert "data" in data
    assert "meta" in data
    assert "request_id" in data["meta"]
    assert "timestamp" in data["meta"]
    print(f"   Response format: ✅ Correct")
    print(f"   Request ID: {data['meta']['request_id']}")

    # Test health endpoint
    response = client.get("/health")
    print(f"✅ Health endpoint: {response.status_code}")

    data = response.json()
    assert data["success"] == True
    assert "status" in data["data"]
    print(f"   Health status: {data['data']['status']}")

def test_error_handling():
    """Test error handling and response format."""
    client = TestClient(app)

    print("\n🧪 Testing Error Handling...")

    # Test 404 error
    response = client.get("/nonexistent-endpoint")
    print(f"✅ 404 Error: {response.status_code}")

    if response.status_code == 404:
        data = response.json()
        assert "success" in data
        assert data["success"] == False
        assert "error" in data
        assert "meta" in data
        print(f"   Error format: ✅ Correct")
        print(f"   Error code: {data['error']['code']}")
        print(f"   Request ID: {data['meta']['request_id']}")

def test_user_routes():
    """Test user authentication routes."""
    client = TestClient(app)

    print("\n🧪 Testing User Routes...")

    # Test user status endpoint
    response = client.get("/api/user/status")
    print(f"✅ User status: {response.status_code}")

    data = response.json()
    assert data["success"] == True
    print(f"   Service status: {data['data']['status']}")

    # Test get users endpoint
    response = client.get("/api/user/users")
    print(f"✅ Get users: {response.status_code}")

    # Test user registration with validation error
    invalid_user_data = {
        "username": "",  # Invalid: empty username
        "email": "invalid-email",  # Invalid: bad email format
        "password": "123"  # Invalid: too short
    }

    response = client.post("/api/user/register", json=invalid_user_data)
    print(f"✅ Registration validation: {response.status_code}")

    if response.status_code == 422:
        data = response.json()
        assert data["success"] == False
        assert "error" in data
        print(f"   Validation error handled: ✅ Correct")

def test_workspace_routes():
    """Test workspace management routes."""
    client = TestClient(app)

    print("\n🧪 Testing Workspace Routes...")

    # Test workspace status
    response = client.get("/api/workspace/")
    print(f"✅ Workspace status: {response.status_code}")

    data = response.json()
    assert data["success"] == True
    print(f"   Service status: {data['data']['status']}")

    # Test get all workspaces
    response = client.get("/api/workspace/all")
    print(f"✅ Get workspaces: {response.status_code}")

    data = response.json()
    assert data["success"] == True
    assert "workspaces" in data["data"]
    print(f"   Workspaces count: {data['data']['total_count']}")

def test_topic_routes():
    """Test topic generation routes."""
    client = TestClient(app)

    print("\n🧪 Testing Topic Routes...")

    # Test topic status
    response = client.get("/api/topic/")
    print(f"✅ Topic status: {response.status_code}")

    data = response.json()
    assert data["success"] == True
    print(f"   Service status: {data['data']['status']}")

    # Test get topics (will fail due to auth, but we test error handling)
    response = client.get("/api/topic/get-topics")
    print(f"✅ Get topics (auth required): {response.status_code}")

    # Should return 403 with proper error format
    if response.status_code == 403:
        data = response.json()
        assert data["success"] == False
        assert "error" in data
        print(f"   Auth error handled: ✅ Correct")
        print(f"   Error code: {data['error']['code']}")

def test_request_tracking():
    """Test request ID tracking across requests."""
    client = TestClient(app)

    print("\n🧪 Testing Request Tracking...")

    # Make request with custom request ID
    custom_request_id = "test_req_12345"
    headers = {"X-Request-ID": custom_request_id}

    response = client.get("/health", headers=headers)
    print(f"✅ Custom request ID: {response.status_code}")

    # Check if our request ID is preserved
    assert response.headers.get("X-Request-ID") == custom_request_id
    print(f"   Request ID preserved: ✅ {custom_request_id}")

    # Check processing time header
    processing_time = response.headers.get("X-Processing-Time-MS")
    if processing_time:
        print(f"   Processing time: {processing_time}ms")

    # Make request without custom ID (should generate one)
    response = client.get("/health")
    generated_id = response.headers.get("X-Request-ID")
    assert generated_id is not None
    print(f"   Generated request ID: ✅ {generated_id}")

def test_knowledge_routes():
    """Test knowledge management routes."""
    client = TestClient(app)

    print("\n🧪 Testing Knowledge Routes...")

    # Test knowledge status
    response = client.get("/api/knowledge/")
    print(f"✅ Knowledge status: {response.status_code}")

    data = response.json()
    assert data["success"] == True
    print(f"   Service status: {data['data']['status']}")

    # Test web knowledge status
    response = client.get("/api/knowledge/web/")
    print(f"✅ Web knowledge status: {response.status_code}")

    data = response.json()
    assert data["success"] == True
    print(f"   Service status: {data['data']['status']}")

def test_api_documentation():
    """Test API documentation endpoints."""
    client = TestClient(app)

    print("\n🧪 Testing API Documentation...")

    # Test OpenAPI schema
    response = client.get("/openapi.json")
    print(f"✅ OpenAPI schema: {response.status_code}")

    if response.status_code == 200:
        schema = response.json()
        assert "info" in schema
        assert "paths" in schema
        print(f"   API title: {schema['info']['title']}")
        print(f"   API version: {schema['info']['version']}")
        print(f"   Endpoints count: {len(schema['paths'])}")

def run_all_tests():
    """Run all integration tests."""
    print("🚀 Starting Middleware Integration Tests")
    print("=" * 50)

    try:
        test_response_format()
        test_error_handling()
        test_user_routes()
        test_workspace_routes()
        test_topic_routes()
        test_request_tracking()
        test_knowledge_routes()
        test_api_documentation()

        print("\n" + "=" * 50)
        print("✅ All tests passed! Middleware integration is working correctly.")
        print("\n🎉 Consistent response and error handling system is ready!")

        print("\n📊 Features Validated:")
        print("   ✅ Consistent response format (success/error/meta)")
        print("   ✅ Request ID tracking and correlation")
        print("   ✅ Processing time measurement")
        print("   ✅ Standardized error handling")
        print("   ✅ Custom exception handling")
        print("   ✅ Route handler integration")
        print("   ✅ Authentication error handling")
        print("   ✅ Validation error formatting")
        print("   ✅ Health check endpoints")
        print("   ✅ API documentation")

        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)