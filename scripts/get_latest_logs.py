#!/usr/bin/env python3
"""
Quick script to fetch the latest logs from PythonAnywhere.

This script provides a simple interface to get the current logs
with basic analysis and saves them to the local logs directory.

USAGE:
    python get_latest_logs.py [log_types...]

ARGUMENTS:
    log_types (optional)    - Specific log types to fetch: access, error, server
                             If not specified, fetches all log types

USAGE EXAMPLES:
    python get_latest_logs.py                    # Fetch all log types
    python get_latest_logs.py error              # Only error logs
    python get_latest_logs.py access server      # Access and server logs
    python get_latest_logs.py error access       # Error and access logs

EXPECTED OUTPUTS:

1. Successful execution:
   === PythonAnywhere Latest Logs Fetcher ===
   Timestamp: 2024-01-15 14:30:22
   
   ✓ API connection successful!
   
   Fetching all log types (access, error, server)
   
   === LOG ANALYSIS SUMMARY ===
   
   ACCESS LOG:
     ✓ Successfully fetched
     📄 Lines: 234
     💾 Size: 37.5 KB
     📊 HTTP Status codes:
        ✅ 200: 150 requests
        ⚠️ 404: 10 requests
        ❌ 500: 5 requests
     🔝 First entry: 184.72.95.75 - - [15/Jan/2024:10:22:45 +0000]...
     🔻 Last entry:  18.208.219.202 - - [15/Jan/2024:14:25:12 +0000]...
   
   ERROR LOG:
     ✓ Successfully fetched
     📄 Lines: 1,500
     💾 Size: 285.2 KB
     🔍 Error breakdown:
        • ERROR: 15
        • Exception: 8
        • Failed: 2
     🔝 First entry: 2024-01-15 10:15:23,086: Starting application...
     🔻 Last entry:  2024-01-15 14:25:12,563: Response: 200 for POST /event
   
   SERVER LOG:
     ✓ Successfully fetched
     📄 Lines: 890
     💾 Size: 156.3 KB
     🖥️  Server events:
        📊 Startup Events: 3
        🔄 Reload Events: 1
   
   === SUMMARY ===
   Successfully fetched: 3/3 log files
   🔍 Error analysis: 25 total error entries found
      Review error log details in downloaded files!
   
   📁 Logs saved to: /path/to/scripts/logs

2. Partial failure:
   ERROR LOG:
     ❌ Failed to fetch: Log file not found: /var/log/domain.error.log
   
   === SUMMARY ===
   Successfully fetched: 2/3 log files

3. Connection failure:
   ❌ Cannot connect to PythonAnywhere API. Exiting.

OUTPUT FILES:
    Downloaded logs are saved with timestamp format:
    - access_log_20240115_143022.txt
    - error_log_20240115_143022.txt
    - server_log_20240115_143022.txt

LOG ANALYSIS FEATURES:
    - HTTP status code breakdown with request counts (200: 150, 404: 10, 500: 5)
    - Specific error type categorization (ERROR, Exception, Failed, etc.)
    - Traffic metrics (total requests, unique IPs, error rate percentage)
    - HTTP method analysis (GET, POST, PUT, etc.)
    - Server event tracking (startup, reload, worker events)
    - File size and line count statistics
    - First and last log entry timestamps
    - Response size and bandwidth analysis

NEXT STEPS AFTER RUNNING:
    - Review downloaded files for detailed analysis
    - Use python log_utils.py date YYYY-MM-DD for historical logs
    - Use python troubleshoot.py for guided problem solving

ENVIRONMENT REQUIREMENTS:
    PA_API_TOKEN, PA_USERNAME, PA_DOMAIN, PA_HOST must be set in .env file
"""

import sys
from pathlib import Path
from datetime import datetime

# Add current directory to Python path to import log_utils
sys.path.insert(0, str(Path(__file__).parent))

from log_utils import PythonAnywhereLogFetcher


def main():
    """Main function to fetch latest logs."""
    print("=== PythonAnywhere Latest Logs Fetcher ===")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize the log fetcher
    try:
        fetcher = PythonAnywhereLogFetcher()
    except SystemExit:
        print("Failed to initialize log fetcher. Check your environment configuration.")
        return
    
    # Test API connection first
    if not fetcher.test_api_connection():
        print("Cannot connect to PythonAnywhere API. Exiting.")
        return
    
    print()
    
    # Parse command line arguments for specific log types
    log_types = None
    if len(sys.argv) > 1:
        log_types = sys.argv[1:]
        # Validate log types
        valid_types = ["access", "error", "server"]
        invalid_types = [t for t in log_types if t not in valid_types]
        if invalid_types:
            print(f"Invalid log types: {invalid_types}")
            print(f"Valid types are: {valid_types}")
            return
        print(f"Fetching specific log types: {log_types}")
    else:
        print("Fetching all log types (access, error, server)")
    
    # Fetch the logs
    results = fetcher.get_latest_logs(log_types)
    
    print("\n=== LOG ANALYSIS SUMMARY ===")
    
    # Analyze and display results
    total_errors = 0
    for log_type, (success, content) in results.items():
        print(f"\n{log_type.upper()} LOG:")
        
        if success:
            analysis = fetcher.analyze_log_summary(content, log_type)
            print(f"  ✓ Successfully fetched")
            print(f"  📄 Lines: {analysis['total_lines']:,}")
            print(f"  💾 Size: {analysis['file_size_kb']:.1f} KB")
            
            if log_type == "error" and 'error_counts' in analysis:
                error_counts = analysis['error_counts']
                if error_counts:
                    print(f"  🔍 Error breakdown:")
                    for error_type, count in error_counts.items():
                        print(f"     • {error_type}: {count:,}")
                        total_errors += count
                else:
                    print(f"  ✅ No errors detected")
                
            elif log_type == "access" and 'status_codes' in analysis:
                status_codes = analysis['status_codes']
                if status_codes:
                    print(f"  📊 HTTP Status codes:")
                    for code, count in sorted(status_codes.items()):
                        status_emoji = "✅" if code.startswith('2') else "⚠️" if code.startswith(('3', '4')) else "❌"
                        print(f"     {status_emoji} {code}: {count:,} requests")
                    
                    # Additional access metrics
                    if 'total_requests' in analysis:
                        print(f"  📈 Traffic summary:")
                        print(f"     • Total requests: {analysis['total_requests']:,}")
                        if 'unique_ips' in analysis:
                            print(f"     • Unique IPs: {analysis['unique_ips']:,}")
                        if 'error_rate_percent' in analysis:
                            error_emoji = "❌" if analysis['error_rate_percent'] > 10 else "⚠️" if analysis['error_rate_percent'] > 5 else "✅"
                            print(f"     • Error rate: {analysis['error_rate_percent']}% {error_emoji}")
                        if 'server_error_count' in analysis and analysis['server_error_count'] > 0:
                            print(f"     • Server errors (5xx): {analysis['server_error_count']:,}")
                        if 'client_error_count' in analysis and analysis['client_error_count'] > 0:
                            print(f"     • Client errors (4xx): {analysis['client_error_count']:,}")
                    
                    if 'request_methods' in analysis:
                        methods = analysis['request_methods']
                        if methods:
                            print(f"  🔧 Request methods:")
                            for method, count in sorted(methods.items(), key=lambda x: x[1], reverse=True):
                                print(f"     • {method}: {count:,}")
            
            elif log_type == "server" and 'server_events' in analysis:
                server_events = analysis['server_events']
                if server_events:
                    print(f"  🖥️  Server events:")
                    for event_type, count in server_events.items():
                        event_emoji = "⚠️" if "warning" in event_type.lower() else "🔄" if "reload" in event_type.lower() else "📊"
                        print(f"     {event_emoji} {event_type.replace('_', ' ').title()}: {count:,}")
                else:
                    print(f"  ✅ No significant server events")
            
            # Show first and last entries for context
            if analysis['first_entry'] != "N/A":
                print(f"  🔝 First entry: {analysis['first_entry'][:100]}...")
            if analysis['last_entry'] != "N/A":
                print(f"  🔻 Last entry:  {analysis['last_entry'][:100]}...")
        else:
            print(f"  ❌ Failed to fetch: {content}")
    
    # Summary
    print(f"\n=== SUMMARY ===")
    success_count = sum(1 for _, (success, _) in results.items() if success)
    total_count = len(results)
    print(f"Successfully fetched: {success_count}/{total_count} log files")
    
    if total_errors > 0:
        print(f"🔍 Error analysis: {total_errors} total error entries found")
        print("   Review error log details in downloaded files")
    else:
        print("✅ No errors detected in logs")
    
    print(f"\n📁 Logs saved to: {fetcher.LOGS_DIR}")
    print("\nTo analyze specific issues, check the downloaded log files or use:")
    print("  python log_utils.py date YYYY-MM-DD    # for historical logs")
    print("  python log_utils.py list               # to see available logs")


if __name__ == "__main__":
    main() 