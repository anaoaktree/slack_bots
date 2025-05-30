#!/usr/bin/env python3
"""
Simple test runner for deployment tests.
Run this to validate the deployment resume/retry functionality tests.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts"))

def run_basic_tests():
    """Run basic tests without pytest to validate functionality."""
    print("🧪 Running basic deployment state tests...")
    
    # Import after path setup
    from unittest.mock import patch, mock_open
    import json
    
    # Import the deployment module
    import deploy_to_pythonanywhere as deploy
    
    test_count = 0
    passed_count = 0
    
    def run_test(test_name, test_func):
        nonlocal test_count, passed_count
        test_count += 1
        try:
            test_func()
            print(f"✅ {test_name}")
            passed_count += 1
        except Exception as e:
            print(f"❌ {test_name}: {e}")
    
    # Test 1: Save upload state
    def test_save_state():
        with patch("builtins.open", mock_open()) as mock_file, \
             patch("json.dump") as mock_json_dump, \
             patch("time.time", return_value=1234567890.0):
            
            deploy.save_upload_state({"/test/file1.py"}, {"/test/file2.py"}, 2)
            mock_file.assert_called_once_with("deployment_state.json", "w")
            mock_json_dump.assert_called_once()
    
    # Test 2: Load upload state - no file
    def test_load_state_no_file():
        with patch("os.path.exists", return_value=False):
            result = deploy.load_upload_state()
            assert result is None
    
    # Test 3: Load upload state - success
    def test_load_state_success():
        mock_state = {"uploaded_files": ["/test/file1.py"], "failed_files": [], "total_files": 1}
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open()), \
             patch("json.load", return_value=mock_state):
            
            result = deploy.load_upload_state()
            assert result == mock_state
    
    # Test 4: Clear upload state
    def test_clear_state():
        with patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove:
            
            deploy.clear_upload_state()
            mock_remove.assert_called_once_with("deployment_state.json")
    
    # Test 5: Rate limiter initialization
    def test_rate_limiter():
        limiter = deploy.RateLimiter(requests_per_minute=60)
        assert limiter.requests_per_minute == 60
        assert limiter.min_interval == 1.0
    
    # Run all tests
    run_test("Save upload state", test_save_state)
    run_test("Load upload state - no file", test_load_state_no_file)
    run_test("Load upload state - success", test_load_state_success)
    run_test("Clear upload state", test_clear_state)
    run_test("Rate limiter initialization", test_rate_limiter)
    
    print(f"\n📊 Test Results: {passed_count}/{test_count} tests passed")
    
    if passed_count == test_count:
        print("🎉 All basic tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        return False


def run_pytest_if_available():
    """Run pytest if available."""
    try:
        import pytest
        print("\n🧪 Running full pytest suite...")
        
        test_file = Path(__file__).parent / "test_deployment_resume.py"
        exit_code = pytest.main([str(test_file), "-v"])
        
        if exit_code == 0:
            print("🎉 All pytest tests passed!")
        else:
            print("❌ Some pytest tests failed!")
        
        return exit_code == 0
    
    except ImportError:
        print("⚠️  pytest not available, skipping full test suite")
        print("   Install with: pip install pytest")
        return True


if __name__ == "__main__":
    print("🚀 Deployment Resume/Retry Test Suite")
    print("=" * 50)
    
    # Run basic tests first
    basic_passed = run_basic_tests()
    
    # Run pytest if available
    pytest_passed = run_pytest_if_available()
    
    print("\n" + "=" * 50)
    if basic_passed and pytest_passed:
        print("✅ All tests completed successfully!")
        sys.exit(0)
    else:
        print("❌ Some tests failed!")
        sys.exit(1) 