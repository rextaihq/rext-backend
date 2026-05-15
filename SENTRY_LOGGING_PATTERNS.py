#!/usr/bin/env python3
"""
SENTRY LOGGING PATTERNS - Reference Guide (2026)

This file demonstrates the recommended patterns for using Sentry SDK
in Python backend code. Use these patterns in all new code.
"""

import sentry_sdk
from sentry_sdk import capture_message, capture_exception, push_scope


# ============================================================================
# PATTERN 1: Simple Info Message
# ============================================================================
def pattern_info_message():
    """Send an info-level message to Sentry."""
    with push_scope() as scope:
        scope.set_tag("module", "my_module")
        scope.set_tag("status", "processing")
        capture_message("Process started successfully", level="info")


# ============================================================================
# PATTERN 2: Warning with Context
# ============================================================================
def pattern_warning_with_context(user_id: str, action: str):
    """Send a warning with structured context data."""
    with push_scope() as scope:
        scope.set_tag("module", "auth_module")
        scope.set_tag("severity", "warning")
        scope.set_context("user_action", {
            "user_id": user_id,
            "action": action,
            "timestamp": "2026-05-15T10:30:00Z"
        })
        capture_message(f"User {user_id} attempted {action}", level="warning")


# ============================================================================
# PATTERN 3: Exception Capture
# ============================================================================
def pattern_exception_capture():
    """Capture an exception with full traceback and context."""
    try:
        result = 10 / 0  # This will raise ZeroDivisionError
    except Exception as e:
        with push_scope() as scope:
            scope.set_tag("module", "calculation_module")
            scope.set_tag("operation", "division")
            scope.set_context("calculation", {
                "numerator": 10,
                "denominator": 0,
                "operation": "divide"
            })
            # capture_exception includes full traceback
            capture_exception(e)


# ============================================================================
# PATTERN 4: Error Message with Multiple Tags
# ============================================================================
def pattern_error_with_tags(query: str, result_count: int):
    """Send an error message with multiple categorizing tags."""
    if result_count == 0:
        with push_scope() as scope:
            scope.set_tag("module", "search_module")
            scope.set_tag("operation", "search")
            scope.set_tag("result_status", "empty_results")
            scope.set_tag("severity", "error")
            scope.set_context("search_params", {
                "query": query,
                "result_count": result_count
            })
            capture_message(f"No results found for query: {query}", level="error")


# ============================================================================
# PATTERN 5: Conditional Logging
# ============================================================================
def pattern_conditional_logging(data: dict, required_fields: list):
    """Log only when specific conditions are met."""
    missing_fields = [f for f in required_fields if f not in data]
    
    if missing_fields:
        with push_scope() as scope:
            scope.set_tag("module", "validation_module")
            scope.set_tag("validation_type", "required_fields")
            scope.set_context("validation_result", {
                "missing_fields": missing_fields,
                "required_fields": required_fields,
                "provided_fields": list(data.keys())
            })
            capture_message(
                f"Validation failed: missing fields {missing_fields}",
                level="warning"
            )
        return False
    
    return True


# ============================================================================
# PATTERN 6: Breadcrumb Trail for Debugging
# ============================================================================
def pattern_breadcrumb_trail(user_id: str, action_steps: list):
    """Create a breadcrumb trail for complex multi-step operations."""
    for idx, step in enumerate(action_steps, 1):
        # Add breadcrumb for tracking
        sentry_sdk.add_breadcrumb(
            category=f"step_{idx}",
            message=f"Processing {step}",
            level="info",
            data={"user_id": user_id, "step_number": idx}
        )
        
        # Simulate processing
        try:
            result = process_step(step)
        except Exception as e:
            with push_scope() as scope:
                scope.set_tag("module", "workflow_module")
                scope.set_tag("failed_step", str(idx))
                scope.set_context("workflow", {
                    "user_id": user_id,
                    "total_steps": len(action_steps),
                    "failed_at_step": idx,
                    "step_name": step
                })
                capture_exception(e)
            break


def process_step(step: str) -> any:
    """Simulate step processing."""
    return f"Completed: {step}"


# ============================================================================
# PATTERN 7: Performance Metrics
# ============================================================================
def pattern_performance_monitoring(operation_name: str, duration_ms: float):
    """Log performance metrics."""
    threshold_ms = 100  # Alert if operation takes longer than 100ms
    
    if duration_ms > threshold_ms:
        with push_scope() as scope:
            scope.set_tag("module", "performance_module")
            scope.set_tag("status", "slow_operation")
            scope.set_context("performance", {
                "operation": operation_name,
                "duration_ms": duration_ms,
                "threshold_ms": threshold_ms,
                "exceeded_by_ms": duration_ms - threshold_ms
            })
            capture_message(
                f"Slow operation detected: {operation_name} took {duration_ms}ms",
                level="warning"
            )


# ============================================================================
# PATTERN 8: State Validation Logging
# ============================================================================
def pattern_state_validation(state: dict, required_keys: list):
    """Validate state and log issues with full context."""
    missing = [k for k in required_keys if k not in state]
    
    if missing:
        with push_scope() as scope:
            scope.set_tag("module", "state_validation")
            scope.set_tag("validation_type", "missing_keys")
            scope.set_context("state_info", {
                "missing_keys": missing,
                "state_keys_available": list(state.keys()),
                "required_keys": required_keys
            })
            capture_message(
                f"State validation failed: missing {missing}",
                level="error"
            )
        return False
    
    return True


# ============================================================================
# PATTERN 9: API Request Logging
# ============================================================================
def pattern_api_request_logging(method: str, url: str, status_code: int):
    """Log API requests with appropriate level based on status."""
    level = "info" if status_code < 400 else "warning" if status_code < 500 else "error"
    
    with push_scope() as scope:
        scope.set_tag("module", "api_module")
        scope.set_tag("http_method", method)
        scope.set_tag("status_code", str(status_code))
        scope.set_context("request", {
            "method": method,
            "url": url,
            "status_code": status_code
        })
        capture_message(f"{method} {url} - {status_code}", level=level)


# ============================================================================
# PATTERN 10: Data Integrity Checks
# ============================================================================
def pattern_data_integrity(entity_id: str, expected_count: int, actual_count: int):
    """Log data integrity issues."""
    if actual_count != expected_count:
        with push_scope() as scope:
            scope.set_tag("module", "data_integrity")
            scope.set_tag("check_type", "count_mismatch")
            scope.set_context("integrity_check", {
                "entity_id": entity_id,
                "expected_count": expected_count,
                "actual_count": actual_count,
                "difference": actual_count - expected_count
            })
            capture_message(
                f"Data integrity issue for {entity_id}: expected {expected_count} but got {actual_count}",
                level="warning"
            )


# ============================================================================
# USAGE GUIDE
# ============================================================================
if __name__ == "__main__":
    print("Sentry Logging Patterns Reference")
    print("=" * 60)
    print()
    print("Available patterns:")
    print("  1. Simple Info Message")
    print("  2. Warning with Context")
    print("  3. Exception Capture")
    print("  4. Error with Multiple Tags")
    print("  5. Conditional Logging")
    print("  6. Breadcrumb Trail")
    print("  7. Performance Monitoring")
    print("  8. State Validation")
    print("  9. API Request Logging")
    print("  10. Data Integrity Checks")
    print()
    print("Key Takeaways:")
    print("  ✓ Always use push_scope() for context")
    print("  ✓ Add tags for filtering in Sentry")
    print("  ✓ Include context dict for debugging")
    print("  ✓ Use appropriate log level (info/warning/error)")
    print("  ✓ Use capture_exception() for caught exceptions")
    print()
