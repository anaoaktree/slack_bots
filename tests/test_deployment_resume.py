#!/usr/bin/env python3
"""
Tests for deployment script resume/retry functionality.

These tests mock all external dependencies to avoid actual API calls or file system operations.
"""

import json
import os
import pytest
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, MagicMock

# Add the scripts directory to the path so we can import the deployment script
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import deploy_to_pythonanywhere as deploy


class TestDeploymentState:
    """Test deployment state management functions."""
    
    def test_save_upload_state_success(self):
        """Test successful saving of upload state."""
        uploaded_files = {"/test/file1.py", "/test/file2.py"}
        failed_files = {"/test/file3.py"}
        total_files = 3
        
        mock_file = mock_open()
        with patch("builtins.open", mock_file), \
             patch("json.dump") as mock_json_dump, \
             patch("time.time", return_value=1234567890.0):
            
            deploy.save_upload_state(uploaded_files, failed_files, total_files)
            
            # Verify file was opened for writing
            mock_file.assert_called_once_with("deployment_state.json", "w")
            
            # Verify JSON was written with correct structure
            expected_state = {
                "uploaded_files": ["/test/file1.py", "/test/file2.py"],
                "failed_files": ["/test/file3.py"],
                "total_files": 3,
                "timestamp": 1234567890.0
            }
            mock_json_dump.assert_called_once()
            actual_state = mock_json_dump.call_args[0][0]
            
            assert actual_state["total_files"] == expected_state["total_files"]
            assert actual_state["timestamp"] == expected_state["timestamp"]
            assert set(actual_state["uploaded_files"]) == set(expected_state["uploaded_files"])
            assert set(actual_state["failed_files"]) == set(expected_state["failed_files"])
    
    def test_save_upload_state_file_error(self, capsys):
        """Test handling of file write errors when saving state."""
        with patch("builtins.open", side_effect=IOError("Permission denied")):
            deploy.save_upload_state(set(), set(), 0)
            
            captured = capsys.readouterr()
            assert "⚠️  Failed to save upload state: Permission denied" in captured.out
    
    def test_load_upload_state_success(self, capsys):
        """Test successful loading of upload state."""
        mock_state = {
            "uploaded_files": ["/test/file1.py", "/test/file2.py"],
            "failed_files": ["/test/file3.py"],
            "total_files": 3,
            "timestamp": 1234567890.0
        }
        
        mock_file = mock_open(read_data=json.dumps(mock_state))
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_file), \
             patch("json.load", return_value=mock_state):
            
            result = deploy.load_upload_state()
            
            assert result == mock_state
            captured = capsys.readouterr()
            assert "📂 Loaded previous upload state from deployment_state.json" in captured.out
            assert "2 files already uploaded" in captured.out
            assert "1 files previously failed" in captured.out
    
    def test_load_upload_state_no_file(self):
        """Test loading state when no file exists."""
        with patch("os.path.exists", return_value=False):
            result = deploy.load_upload_state()
            assert result is None
    
    def test_load_upload_state_corrupted_file(self, capsys):
        """Test handling of corrupted JSON state file."""
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="invalid json")), \
             patch("json.load", side_effect=json.JSONDecodeError("Invalid JSON", "", 0)):
            
            result = deploy.load_upload_state()
            
            assert result is None
            captured = capsys.readouterr()
            assert "⚠️  Failed to load upload state:" in captured.out
    
    def test_load_upload_state_missing_keys(self, capsys):
        """Test loading state with missing keys (graceful handling)."""
        incomplete_state = {"uploaded_files": ["/test/file1.py"]}  # Missing other keys
        
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open()), \
             patch("json.load", return_value=incomplete_state):
            
            result = deploy.load_upload_state()
            
            assert result == incomplete_state
            captured = capsys.readouterr()
            assert "1 files already uploaded" in captured.out
            assert "0 files previously failed" in captured.out  # Uses .get() with default
    
    def test_clear_upload_state_success(self, capsys):
        """Test successful clearing of upload state."""
        with patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove:
            
            deploy.clear_upload_state()
            
            mock_remove.assert_called_once_with("deployment_state.json")
            captured = capsys.readouterr()
            assert "🧹 Cleared upload state file" in captured.out
    
    def test_clear_upload_state_no_file(self, capsys):
        """Test clearing state when no file exists."""
        with patch("os.path.exists", return_value=False):
            deploy.clear_upload_state()
            
            captured = capsys.readouterr()
            # Should not print anything since file doesn't exist
            assert "🧹 Cleared upload state file" not in captured.out
    
    def test_clear_upload_state_error(self, capsys):
        """Test handling of errors when clearing state."""
        with patch("os.path.exists", return_value=True), \
             patch("os.remove", side_effect=OSError("Permission denied")):
            
            deploy.clear_upload_state()
            
            captured = capsys.readouterr()
            assert "⚠️  Failed to clear upload state: Permission denied" in captured.out


class TestCommandLineHandling:
    """Test command line argument handling for resume/retry functionality."""
    
    @patch.dict(os.environ, {
        'PA_API_TOKEN': 'test_token',
        'PA_USERNAME': 'test_user', 
        'PA_DOMAIN': 'test.com',
        'PA_HOST': 'www.pythonanywhere.com'
    })
    def test_retry_failed_no_previous_state(self, capsys):
        """Test --retry-failed when no previous state exists."""
        with patch("sys.argv", ["deploy_to_pythonanywhere.py", "--retry-failed"]), \
             patch("deploy_to_pythonanywhere.load_upload_state", return_value=None), \
             pytest.raises(SystemExit):
            
            deploy.main()
            
            captured = capsys.readouterr()
            assert "🔄 Retry mode: Will retry only previously failed uploads." in captured.out
            assert "No previous deployment state found" in captured.out
    
    @patch.dict(os.environ, {
        'PA_API_TOKEN': 'test_token',
        'PA_USERNAME': 'test_user',
        'PA_DOMAIN': 'test.com', 
        'PA_HOST': 'www.pythonanywhere.com'
    })
    def test_retry_failed_no_failed_files(self, capsys):
        """Test --retry-failed when no failed files exist."""
        mock_state = {
            "uploaded_files": ["/test/file1.py"],
            "failed_files": [],
            "total_files": 1,
            "timestamp": 1234567890.0
        }
        
        with patch("sys.argv", ["deploy_to_pythonanywhere.py", "--retry-failed"]), \
             patch("deploy_to_pythonanywhere.load_upload_state", return_value=mock_state), \
             pytest.raises(SystemExit):
            
            deploy.main()
            
            captured = capsys.readouterr()
            assert "🔄 Retry mode: Will retry only previously failed uploads." in captured.out
            assert "No failed files found to retry" in captured.out
    
    @patch.dict(os.environ, {
        'PA_API_TOKEN': 'test_token',
        'PA_USERNAME': 'test_user',
        'PA_DOMAIN': 'test.com',
        'PA_HOST': 'www.pythonanywhere.com'
    })
    def test_retry_failed_with_failed_files(self, capsys):
        """Test --retry-failed when failed files exist."""
        mock_state = {
            "uploaded_files": ["/test/file1.py"],
            "failed_files": ["/test/file2.py", "/test/file3.py"],
            "total_files": 3,
            "timestamp": 1234567890.0
        }
        
        with patch("sys.argv", ["deploy_to_pythonanywhere.py", "--retry-failed"]), \
             patch("deploy_to_pythonanywhere.load_upload_state", return_value=mock_state), \
             patch("deploy_to_pythonanywhere.save_upload_state") as mock_save, \
             patch("deploy_to_pythonanywhere.test_api_connection", return_value=(True, {})), \
             patch("deploy_to_pythonanywhere.upload_directory", return_value=True), \
             patch("deploy_to_pythonanywhere.upload_env_file", return_value=True), \
             patch("deploy_to_pythonanywhere.run_post_deployment_tasks", return_value=True), \
             patch("deploy_to_pythonanywhere.reload_webapp", return_value=True), \
             patch("deploy_to_pythonanywhere.clear_upload_state"):
            
            deploy.main()
            
            captured = capsys.readouterr()
            assert "🔄 Retry mode: Will retry only previously failed uploads." in captured.out
            assert "Found 2 failed files to retry" in captured.out
            
            # Verify new state was saved with only failed files
            mock_save.assert_called_once_with(set(), {"/test/file2.py", "/test/file3.py"}, 2)
    
    @patch.dict(os.environ, {
        'PA_API_TOKEN': 'test_token',
        'PA_USERNAME': 'test_user',
        'PA_DOMAIN': 'test.com',
        'PA_HOST': 'www.pythonanywhere.com'
    })
    def test_clear_state_command(self, capsys):
        """Test --clear-state command."""
        with patch("sys.argv", ["deploy_to_pythonanywhere.py", "--clear-state"]), \
             patch("deploy_to_pythonanywhere.clear_upload_state") as mock_clear, \
             pytest.raises(SystemExit):
            
            deploy.main()
            
            mock_clear.assert_called_once()
            captured = capsys.readouterr()
            assert "🧹 Cleared deployment state. Next run will start fresh." in captured.out
    
    def test_help_command(self, capsys):
        """Test --help command."""
        with patch("sys.argv", ["deploy_to_pythonanywhere.py", "--help"]), \
             pytest.raises(SystemExit):
            
            deploy.main()
            
            captured = capsys.readouterr()
            assert "PythonAnywhere Deployment Script" in captured.out
            assert "--resume" in captured.out
            assert "--retry-failed" in captured.out
            assert "Rate limiting (35 requests/minute)" in captured.out


class TestUploadDirectoryResume:
    """Test upload_directory function with resume functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.mock_headers = {"Authorization": "Token test_token"}
        self.test_local_dir = Path("/test/local")
        self.test_remote_path = "/home/test_user/app"
    
    @patch("deploy_to_pythonanywhere.should_exclude")
    @patch("os.walk")
    @patch("builtins.input")
    def test_upload_directory_resume_user_says_yes(self, mock_input, mock_walk, mock_should_exclude, capsys):
        """Test upload directory with resume when user chooses to resume."""
        # Mock file structure
        mock_walk.return_value = [
            ("/test/local", [], ["file1.py", "file2.py", "file3.py"])
        ]
        mock_should_exclude.return_value = False
        
        # Mock previous state
        previous_state = {
            "uploaded_files": ["/home/test_user/app/file1.py"],
            "failed_files": ["/home/test_user/app/file2.py"],
            "total_files": 3,
            "timestamp": 1234567890.0
        }
        
        # Mock user input to resume
        mock_input.return_value = "y"
        
        with patch("deploy_to_pythonanywhere.load_upload_state", return_value=previous_state), \
             patch("deploy_to_pythonanywhere.upload_file") as mock_upload, \
             patch("deploy_to_pythonanywhere.save_upload_state") as mock_save, \
             patch("deploy_to_pythonanywhere.clear_upload_state") as mock_clear, \
             patch.object(Path, "relative_to") as mock_relative_to:
            
            # Mock relative_to to return predictable paths
            mock_relative_to.side_effect = lambda base: Path("file1.py") if "file1" in str(self) else (
                Path("file2.py") if "file2" in str(self) else Path("file3.py")
            )
            
            # Mock successful uploads for remaining files
            mock_upload.return_value = True
            
            result = deploy.upload_directory(self.test_local_dir, self.test_remote_path, self.mock_headers)
            
            assert result is True
            
            captured = capsys.readouterr()
            assert "📂 Loaded previous upload state" in captured.out
            assert "Already uploaded: 1" in captured.out
            assert "Previously failed: 1" in captured.out
            assert "Remaining: 2" in captured.out
            
            # Should only upload remaining files (file2.py retry + file3.py new)
            assert mock_upload.call_count == 2
            mock_clear.assert_called_once()  # Clear state on success
    
    @patch("deploy_to_pythonanywhere.should_exclude")
    @patch("os.walk")
    @patch("builtins.input")
    def test_upload_directory_resume_user_says_no(self, mock_input, mock_walk, mock_should_exclude, capsys):
        """Test upload directory with resume when user chooses fresh start."""
        # Mock file structure
        mock_walk.return_value = [
            ("/test/local", [], ["file1.py", "file2.py"])
        ]
        mock_should_exclude.return_value = False
        
        # Mock previous state
        previous_state = {
            "uploaded_files": ["/home/test_user/app/file1.py"],
            "failed_files": [],
            "total_files": 2,
            "timestamp": 1234567890.0
        }
        
        # Mock user input to start fresh
        mock_input.return_value = "n"
        
        with patch("deploy_to_pythonanywhere.load_upload_state", return_value=previous_state), \
             patch("deploy_to_pythonanywhere.upload_file", return_value=True) as mock_upload, \
             patch("deploy_to_pythonanywhere.save_upload_state"), \
             patch("deploy_to_pythonanywhere.clear_upload_state"), \
             patch.object(Path, "relative_to", return_value=Path("file1.py")):
            
            result = deploy.upload_directory(self.test_local_dir, self.test_remote_path, self.mock_headers)
            
            assert result is True
            
            captured = capsys.readouterr()
            assert "🔄 Starting fresh upload..." in captured.out
            
            # Should upload all files (fresh start)
            assert mock_upload.call_count == 2
    
    @patch("deploy_to_pythonanywhere.should_exclude")
    @patch("os.walk")
    def test_upload_directory_no_previous_state(self, mock_walk, mock_should_exclude, capsys):
        """Test upload directory with no previous state (normal deployment)."""
        # Mock file structure
        mock_walk.return_value = [
            ("/test/local", [], ["file1.py", "file2.py"])
        ]
        mock_should_exclude.return_value = False
        
        with patch("deploy_to_pythonanywhere.load_upload_state", return_value=None), \
             patch("deploy_to_pythonanywhere.upload_file", return_value=True) as mock_upload, \
             patch("deploy_to_pythonanywhere.save_upload_state"), \
             patch("deploy_to_pythonanywhere.clear_upload_state"), \
             patch.object(Path, "relative_to", return_value=Path("file1.py")):
            
            result = deploy.upload_directory(self.test_local_dir, self.test_remote_path, self.mock_headers)
            
            assert result is True
            
            captured = capsys.readouterr()
            assert "Total files to process: 2" in captured.out
            assert "Already uploaded: 0" in captured.out
            assert "Previously failed: 0" in captured.out
            assert "Remaining: 2" in captured.out
            
            # Should upload all files
            assert mock_upload.call_count == 2
    
    @patch("deploy_to_pythonanywhere.should_exclude")
    @patch("os.walk")
    def test_upload_directory_all_files_already_uploaded(self, mock_walk, mock_should_exclude, capsys):
        """Test upload directory when all files are already uploaded."""
        # Mock file structure
        mock_walk.return_value = [
            ("/test/local", [], ["file1.py", "file2.py"])
        ]
        mock_should_exclude.return_value = False
        
        # Mock state where all files are already uploaded
        previous_state = {
            "uploaded_files": [
                "/home/test_user/app/file1.py",
                "/home/test_user/app/file2.py"
            ],
            "failed_files": [],
            "total_files": 2,
            "timestamp": 1234567890.0
        }
        
        with patch("deploy_to_pythonanywhere.load_upload_state", return_value=previous_state), \
             patch("deploy_to_pythonanywhere.upload_file") as mock_upload, \
             patch("deploy_to_pythonanywhere.save_upload_state"), \
             patch("deploy_to_pythonanywhere.clear_upload_state"), \
             patch.object(Path, "relative_to") as mock_relative_to, \
             patch("builtins.input", return_value="y"):
            
            # Mock relative_to to return predictable paths
            mock_relative_to.side_effect = lambda base: Path("file1.py") if "file1" in str(self) else Path("file2.py")
            
            result = deploy.upload_directory(self.test_local_dir, self.test_remote_path, self.mock_headers)
            
            assert result is True
            
            captured = capsys.readouterr()
            assert "Already uploaded: 2" in captured.out
            assert "Remaining: 0" in captured.out
            assert "✅ All files uploaded successfully!" in captured.out
            
            # Should not upload any files (all already uploaded)
            mock_upload.assert_not_called()
    
    @patch("deploy_to_pythonanywhere.should_exclude")
    @patch("os.walk")
    def test_upload_directory_with_failures(self, mock_walk, mock_should_exclude, capsys):
        """Test upload directory when some files fail to upload."""
        # Mock file structure
        mock_walk.return_value = [
            ("/test/local", [], ["file1.py", "file2.py", "file3.py"])
        ]
        mock_should_exclude.return_value = False
        
        def mock_upload_side_effect(local_path, remote_path, headers):
            # Simulate file2.py failing to upload
            if "file2.py" in str(remote_path):
                return False
            return True
        
        with patch("deploy_to_pythonanywhere.load_upload_state", return_value=None), \
             patch("deploy_to_pythonanywhere.upload_file", side_effect=mock_upload_side_effect) as mock_upload, \
             patch("deploy_to_pythonanywhere.save_upload_state"), \
             patch.object(Path, "relative_to") as mock_relative_to:
            
            # Mock relative_to to return predictable paths
            def relative_to_side_effect(base):
                path_str = str(self)
                if "file1" in path_str:
                    return Path("file1.py")
                elif "file2" in path_str:
                    return Path("file2.py") 
                else:
                    return Path("file3.py")
            
            mock_relative_to.side_effect = relative_to_side_effect
            
            result = deploy.upload_directory(self.test_local_dir, self.test_remote_path, self.mock_headers)
            
            assert result is False  # Should return False due to failures
            
            captured = capsys.readouterr()
            assert "Failed uploads: 1" in captured.out
            assert "❌ Failed files:" in captured.out
            assert "💡 You can re-run the script to retry failed uploads." in captured.out
            
            # Should attempt to upload all files
            assert mock_upload.call_count == 3


class TestRateLimiter:
    """Test the RateLimiter class."""
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization with custom rates."""
        # Test default rate
        limiter = deploy.RateLimiter()
        assert limiter.requests_per_minute == 35
        assert limiter.min_interval == 60.0 / 35
        
        # Test custom rate
        custom_limiter = deploy.RateLimiter(requests_per_minute=10)
        assert custom_limiter.requests_per_minute == 10
        assert custom_limiter.min_interval == 6.0
    
    def test_rate_limiter_no_wait_needed(self, capsys):
        """Test rate limiter when no wait is needed."""
        limiter = deploy.RateLimiter(requests_per_minute=60)  # 1 request per second
        
        with patch("time.time", side_effect=[0, 2]):  # 2 seconds elapsed
            limiter.wait_if_needed()
            
            captured = capsys.readouterr()
            assert "Rate limiting: waiting" not in captured.out
    
    def test_rate_limiter_wait_needed(self, capsys):
        """Test rate limiter when wait is needed."""
        limiter = deploy.RateLimiter(requests_per_minute=60)  # 1 request per second
        limiter.last_request_time = 10.0  # Set a previous request time
        
        with patch("time.time", return_value=10.5), \
             patch("time.sleep") as mock_sleep:
            
            limiter.wait_if_needed()
            
            # Should wait for the remaining time
            mock_sleep.assert_called_once_with(0.5)
            captured = capsys.readouterr()
            assert "⏱️  Rate limiting: waiting 0.5 seconds..." in captured.out


if __name__ == "__main__":
    pytest.main([__file__]) 