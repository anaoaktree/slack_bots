#!/usr/bin/env python3
"""
PythonAnywhere Log Fetching Utilities

This module provides utilities for fetching various types of logs from PythonAnywhere
using their API. It supports downloading access, error, and server logs
with proper authentication and error handling.

USAGE:
    python log_utils.py <command> [args...]

COMMANDS:
    test                    - Test API connection
    latest                  - Get latest logs for all types
    date YYYY-MM-DD         - Get logs for specific date
    list                    - List available log files on server

USAGE EXAMPLES:
    python log_utils.py test
    python log_utils.py latest
    python log_utils.py date 2024-01-15
    python log_utils.py list

EXPECTED OUTPUTS:

1. test command:
   ✓ API connection successful!
   OR
   ✗ API connection failed: 401 - Unauthorized

2. latest command:
   ACCESS LOG ANALYSIS:
     Lines: 234
     Size: 37.5 KB
     Status codes: {'200': 150, '404': 10, '500': 5}
     Total requests: 234
     Error rate: 6.4%
   
   ERROR LOG ANALYSIS:
     Lines: 1,500
     Size: 285.2 KB
     Error breakdown:
       ERROR: 15
       Exception: 8
       Failed: 2

3. date command:
   ACCESS LOG ANALYSIS for 2024-01-15:
     Lines: 456
     Size: 78.3 KB
   OR
   ❌ No access log found for date 2024-01-15

4. list command:
   ACCESS logs:
     chachibt.pythonanywhere.com.access.log
     chachibt.pythonanywhere.com.access.log.2024-01-14
   
   ERROR logs:
     chachibt.pythonanywhere.com.error.log

OUTPUT FILES:
    All downloaded logs are saved to scripts/logs/ with format:
    - access_log_YYYYMMDD_HHMMSS.txt
    - error_log_YYYYMMDD_HHMMSS.txt  
    - server_log_YYYYMMDD_HHMMSS.txt

ENVIRONMENT REQUIREMENTS:
    PA_API_TOKEN    - PythonAnywhere API token
    PA_USERNAME     - PythonAnywhere username
    PA_DOMAIN       - Your domain (e.g., username.pythonanywhere.com)
    PA_HOST         - API host (www.pythonanywhere.com or eu.pythonanywhere.com)
"""

import os
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json

# Add parent directory to path to import from the main project
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    
    # Load environment variables from .env or .prod.env.backup
    env_path = Path(__file__).parent.parent / ".env"
    backup_env_path = Path(__file__).parent.parent / ".prod.env.backup"
    
    if env_path.exists():
        print(f"Loading environment variables from {env_path}")
        load_dotenv(dotenv_path=env_path)
    elif backup_env_path.exists():
        print(f"Loading environment variables from {backup_env_path}")
        load_dotenv(dotenv_path=backup_env_path)
    else:
        print("Warning: No .env file found")
except ImportError:
    print("python-dotenv not installed. Using existing environment variables.")

# Configuration from environment variables
PA_API_TOKEN = os.environ.get("PA_API_TOKEN", "").strip()
PA_USERNAME = os.environ.get("PA_USERNAME", "").strip()
PA_DOMAIN = os.environ.get("PA_DOMAIN", "").strip()
PA_HOST = os.environ.get("PA_HOST", "www.pythonanywhere.com").strip()

# HTTP Status Codes
HTTP_OK = 200
HTTP_NOT_FOUND = 404
DEFAULT_TIMEOUT = 30

# API Configuration
API_BASE_URL = f"https://{PA_HOST}/api/v0/user/{PA_USERNAME}"
FILES_API_URL = f"{API_BASE_URL}/files/path"

# Authentication headers
if PA_API_TOKEN.startswith("Token "):
    PA_API_TOKEN = PA_API_TOKEN.replace("Token ", "")
AUTH_HEADER = "Token " + PA_API_TOKEN
HEADERS = {"Authorization": AUTH_HEADER}

# Log file paths on PythonAnywhere
LOG_PATHS = {
    "access": f"/var/log/{PA_DOMAIN}.access.log",
    "error": f"/var/log/{PA_DOMAIN}.error.log", 
    "server": f"/var/log/{PA_DOMAIN}.server.log"
}

# Local directories
SCRIPT_DIR = Path(__file__).parent
LOGS_DIR = SCRIPT_DIR / "logs"


class PythonAnywhereLogFetcher:
    """A class to fetch logs from PythonAnywhere using their API."""
    
    def __init__(self):
        self.LOGS_DIR = LOGS_DIR  # Make LOGS_DIR accessible as instance attribute
        self.validate_environment()
        self.ensure_logs_directory()
    
    def validate_environment(self):
        """Validate that required environment variables are set."""
        missing_vars = []
        for var_name, var_value in [
            ("PA_API_TOKEN", PA_API_TOKEN),
            ("PA_USERNAME", PA_USERNAME), 
            ("PA_DOMAIN", PA_DOMAIN),
        ]:
            if not var_value:
                missing_vars.append(var_name)
        
        if missing_vars:
            print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
            print("Please set these in your .env file or environment:")
            for var in missing_vars:
                print(f"  {var}=your_value_here")
            sys.exit(1)
        
        # Debug info without revealing full token
        masked_token = f"{PA_API_TOKEN[:4]}...{PA_API_TOKEN[-4:]}" if len(PA_API_TOKEN) > 8 else "***"
        print(f"Using API token: {masked_token} (length: {len(PA_API_TOKEN)})")
        print(f"Username: {PA_USERNAME}")
        print(f"Domain: {PA_DOMAIN}")
        print(f"Host: {PA_HOST}")
    
    def ensure_logs_directory(self):
        """Create logs directory if it doesn't exist."""
        LOGS_DIR.mkdir(exist_ok=True)
        print(f"Logs will be saved to: {LOGS_DIR}")
    
    def test_api_connection(self) -> bool:
        """Test the API connection."""
        print("Testing API connection...")
        
        # Test with a simple CPU endpoint
        test_url = f"{API_BASE_URL}/cpu/"
        
        try:
            response = requests.get(test_url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
            
            if response.status_code == HTTP_OK:
                print("✓ API connection successful!")
                return True
            else:
                print(f"✗ API connection failed: {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except Exception as e:
            print(f"✗ API connection error: {e}")
            return False
    
    def fetch_log_file(self, log_type: str, save_path: Optional[Path] = None) -> Tuple[bool, str]:
        """
        Fetch a specific log file from PythonAnywhere.
        
        Args:
            log_type: Type of log ('access', 'error', 'server')
            save_path: Optional custom path to save the file
            
        Returns:
            Tuple of (success, content_or_error_message)
        """
        if log_type not in LOG_PATHS:
            return False, f"Unknown log type: {log_type}. Available: {list(LOG_PATHS.keys())}"
        
        log_path = LOG_PATHS[log_type]
        url = f"{FILES_API_URL}{log_path}"
        
        print(f"Fetching {log_type} log from: {log_path}")
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
            
            if response.status_code == HTTP_OK:
                content = response.text
                
                # Save to file if path provided
                if save_path:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"✓ Saved {log_type} log to: {save_path}")
                
                return True, content
            
            elif response.status_code == HTTP_NOT_FOUND:
                return False, f"Log file not found: {log_path}"
            else:
                return False, f"Failed to fetch log: {response.status_code} - {response.text}"
                
        except Exception as e:
            return False, f"Error fetching log: {e}"
    
    def get_latest_logs(self, log_types: Optional[List[str]] = None) -> Dict[str, Tuple[bool, str]]:
        """
        Get the latest logs for specified types.
        
        Args:
            log_types: List of log types to fetch. If None, fetches all types.
            
        Returns:
            Dictionary mapping log_type to (success, content_or_error)
        """
        if log_types is None:
            log_types = list(LOG_PATHS.keys())
        
        results = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print(f"Fetching latest logs: {log_types}")
        
        for log_type in log_types:
            filename = f"{log_type}_log_{timestamp}.txt"
            save_path = LOGS_DIR / filename
            
            success, content = self.fetch_log_file(log_type, save_path)
            results[log_type] = (success, content if success else content)
            
            if success:
                lines = len(content.splitlines())
                size_kb = len(content.encode('utf-8')) / 1024
                print(f"  ✓ {log_type}: {lines} lines, {size_kb:.1f} KB")
            else:
                print(f"  ✗ {log_type}: {content}")
        
        return results
    
    def get_log_by_date(self, date_str: str, log_types: Optional[List[str]] = None) -> Dict[str, Tuple[bool, str]]:
        """
        Get logs for a specific date (if available in rotated logs).
        
        Args:
            date_str: Date in YYYY-MM-DD format
            log_types: List of log types to fetch
            
        Returns:
            Dictionary mapping log_type to (success, content_or_error)
        """
        if log_types is None:
            log_types = list(LOG_PATHS.keys())
        
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            return {log_type: (False, f"Invalid date format: {date_str}. Use YYYY-MM-DD") 
                   for log_type in log_types}
        
        results = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print(f"Fetching logs for date: {formatted_date}")
        
        for log_type in log_types:
            # Try different possible log file naming conventions for rotated logs
            possible_paths = [
                f"/var/log/{PA_DOMAIN}.{log_type}.log.{formatted_date}",
                f"/var/log/{PA_DOMAIN}.{log_type}.log-{formatted_date}",
                f"/var/log/{PA_DOMAIN}.{log_type}.{formatted_date}.log",
            ]
            
            success = False
            content = f"No {log_type} log found for date {formatted_date}"
            
            for log_path in possible_paths:
                url = f"{FILES_API_URL}{log_path}"
                
                try:
                    response = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
                    if response.status_code == HTTP_OK:
                        content = response.text
                        success = True
                        
                        # Save the file
                        filename = f"{log_type}_log_{formatted_date}_{timestamp}.txt"
                        save_path = LOGS_DIR / filename
                        
                        with open(save_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        
                        lines = len(content.splitlines())
                        size_kb = len(content.encode('utf-8')) / 1024
                        print(f"  ✓ {log_type}: {lines} lines, {size_kb:.1f} KB (from {log_path})")
                        break
                        
                except Exception as e:
                    continue
            
            if not success:
                print(f"  ✗ {log_type}: {content}")
            
            results[log_type] = (success, content)
        
        return results
    
    def list_available_logs(self) -> Dict[str, List[str]]:
        """
        List available log files in the /var/log directory.
        
        Returns:
            Dictionary mapping log types to available files
        """
        print("Checking available log files...")
        
        # Try to list files in /var/log directory
        url = f"{FILES_API_URL}/var/log/?path=/var/log/"
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
            
            if response.status_code == HTTP_OK:
                # Parse the directory listing response
                # Note: The exact format may vary, this is a basic implementation
                content = response.text
                
                available_logs = {}
                for log_type in LOG_PATHS.keys():
                    available_logs[log_type] = []
                    
                    # Look for files containing the domain and log type
                    lines = content.split('\n')
                    for line in lines:
                        if PA_DOMAIN in line and log_type in line and '.log' in line:
                            available_logs[log_type].append(line.strip())
                
                return available_logs
            else:
                print(f"Could not list log directory: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"Error listing logs: {e}")
            return {}
    
    def analyze_log_summary(self, log_content: str, log_type: str) -> Dict[str, any]:
        """
        Provide factual analysis summary of log content with specific statistics.
        
        Args:
            log_content: The log file content
            log_type: Type of log being analyzed
            
        Returns:
            Dictionary with factual analysis summary
        """
        lines = log_content.splitlines()
        total_lines = len(lines)
        
        if total_lines == 0:
            return {"total_lines": 0, "summary": "Empty log file"}
        
        analysis = {
            "total_lines": total_lines,
            "file_size_kb": len(log_content.encode('utf-8')) / 1024,
            "first_entry": lines[0] if lines else "N/A",
            "last_entry": lines[-1] if lines else "N/A",
        }
        
        if log_type == "error":
            # Count specific error types with factual counts
            error_stats = {
                "ERROR": 0,
                "CRITICAL": 0,
                "WARNING": 0,
                "Exception": 0,
                "Traceback": 0,
                "Failed": 0,
                "Timeout": 0,
                "Connection": 0,
                "Import": 0,
                "Syntax": 0
            }
            
            for line in lines:
                line_lower = line.lower()
                if "error" in line_lower:
                    error_stats["ERROR"] += 1
                if "critical" in line_lower:
                    error_stats["CRITICAL"] += 1
                if "warning" in line_lower:
                    error_stats["WARNING"] += 1
                if "exception" in line_lower:
                    error_stats["Exception"] += 1
                if "traceback" in line_lower:
                    error_stats["Traceback"] += 1
                if "failed" in line_lower:
                    error_stats["Failed"] += 1
                if "timeout" in line_lower:
                    error_stats["Timeout"] += 1
                if "connection" in line_lower and ("refused" in line_lower or "failed" in line_lower or "timeout" in line_lower):
                    error_stats["Connection"] += 1
                if "importerror" in line_lower or "modulenotfounderror" in line_lower:
                    error_stats["Import"] += 1
                if "syntaxerror" in line_lower:
                    error_stats["Syntax"] += 1
            
            # Only include non-zero counts
            analysis["error_counts"] = {k: v for k, v in error_stats.items() if v > 0}
        
        elif log_type == "access":
            # Detailed access log analysis with factual HTTP metrics
            status_codes = {}
            request_methods = {}
            unique_ips = set()
            response_sizes = []
            
            for line in lines:
                parts = line.split()
                
                # Extract IP address (first part of typical access log)
                if parts:
                    ip = parts[0]
                    if ip != "-":
                        unique_ips.add(ip)
                
                # Extract HTTP status codes
                for part in parts:
                    if part.isdigit() and len(part) == 3 and part.startswith(('2', '3', '4', '5')):
                        status_codes[part] = status_codes.get(part, 0) + 1
                        break
                
                # Extract HTTP methods from quoted request strings
                for i, part in enumerate(parts):
                    if part.startswith('"') and i + 1 < len(parts):
                        method = part.strip('"').upper()
                        if method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']:
                            request_methods[method] = request_methods.get(method, 0) + 1
                            break
                
                # Extract response sizes (usually second to last number)
                if len(parts) >= 2:
                    try:
                        size = int(parts[-2])
                        if size > 0:
                            response_sizes.append(size)
                    except (ValueError, IndexError):
                        pass
            
            analysis["status_codes"] = status_codes
            analysis["request_methods"] = request_methods
            analysis["unique_ips"] = len(unique_ips)
            analysis["total_requests"] = sum(status_codes.values())
            
            if response_sizes:
                analysis["avg_response_size"] = sum(response_sizes) / len(response_sizes)
                analysis["total_bytes_served"] = sum(response_sizes)
            
            # Calculate error rates
            total_requests = analysis["total_requests"]
            if total_requests > 0:
                error_requests = sum(count for code, count in status_codes.items() if code.startswith(('4', '5')))
                server_errors = sum(count for code, count in status_codes.items() if code.startswith('5'))
                client_errors = sum(count for code, count in status_codes.items() if code.startswith('4'))
                
                analysis["error_rate_percent"] = round((error_requests / total_requests) * 100, 2)
                analysis["server_error_count"] = server_errors
                analysis["client_error_count"] = client_errors
        
        elif log_type == "server":
            # Server log analysis with factual metrics
            server_stats = {
                "startup_events": 0,
                "shutdown_events": 0,
                "reload_events": 0,
                "worker_events": 0,
                "memory_warnings": 0,
                "process_events": 0
            }
            
            for line in lines:
                line_lower = line.lower()
                if any(word in line_lower for word in ["starting", "started", "spawn"]):
                    server_stats["startup_events"] += 1
                if any(word in line_lower for word in ["stopping", "stopped", "shutdown"]):
                    server_stats["shutdown_events"] += 1
                if "reload" in line_lower:
                    server_stats["reload_events"] += 1
                if "worker" in line_lower:
                    server_stats["worker_events"] += 1
                if "memory" in line_lower and "warning" in line_lower:
                    server_stats["memory_warnings"] += 1
                if any(word in line_lower for word in ["process", "pid", "signal"]):
                    server_stats["process_events"] += 1
            
            analysis["server_events"] = {k: v for k, v in server_stats.items() if v > 0}
        
        return analysis


def main():
    """CLI interface for the log fetcher."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python log_utils.py test           - Test API connection")
        print("  python log_utils.py latest         - Get latest logs")
        print("  python log_utils.py date YYYY-MM-DD - Get logs for specific date")
        print("  python log_utils.py list           - List available logs")
        sys.exit(1)
    
    fetcher = PythonAnywhereLogFetcher()
    command = sys.argv[1]
    
    if command == "test":
        fetcher.test_api_connection()
    
    elif command == "latest":
        results = fetcher.get_latest_logs()
        for log_type, (success, content) in results.items():
            if success:
                analysis = fetcher.analyze_log_summary(content, log_type)
                print(f"\n{log_type.upper()} LOG ANALYSIS:")
                print(f"  Lines: {analysis['total_lines']}")
                print(f"  Size: {analysis['file_size_kb']:.1f} KB")
                
                if log_type == "error" and 'error_counts' in analysis:
                    error_counts = analysis['error_counts']
                    if error_counts:
                        print(f"  Error breakdown:")
                        for error_type, count in error_counts.items():
                            print(f"    {error_type}: {count}")
                    else:
                        print(f"  No errors detected")
                
                elif log_type == "access" and 'status_codes' in analysis:
                    print(f"  Status codes: {analysis['status_codes']}")
                    if 'total_requests' in analysis:
                        print(f"  Total requests: {analysis['total_requests']}")
                    if 'error_rate_percent' in analysis:
                        print(f"  Error rate: {analysis['error_rate_percent']}%")
                
                elif log_type == "server" and 'server_events' in analysis:
                    server_events = analysis['server_events']
                    if server_events:
                        print(f"  Server events: {server_events}")
                    else:
                        print(f"  No significant server events")
    
    elif command == "date":
        if len(sys.argv) < 3:
            print("Please provide a date in YYYY-MM-DD format")
            sys.exit(1)
        
        date_str = sys.argv[2]
        results = fetcher.get_log_by_date(date_str)
        
        for log_type, (success, content) in results.items():
            if success:
                analysis = fetcher.analyze_log_summary(content, log_type)
                print(f"\n{log_type.upper()} LOG ANALYSIS for {date_str}:")
                print(f"  Lines: {analysis['total_lines']}")
                print(f"  Size: {analysis['file_size_kb']:.1f} KB")
    
    elif command == "list":
        available = fetcher.list_available_logs()
        for log_type, files in available.items():
            print(f"\n{log_type.upper()} logs:")
            for file in files:
                print(f"  {file}")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main() 