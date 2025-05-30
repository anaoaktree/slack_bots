#!/usr/bin/env python3
"""
Script to fetch logs from PythonAnywhere for a specific date.

This script helps retrieve historical logs that have been rotated,
useful for investigating issues that occurred on specific dates.

USAGE:
    python get_logs_by_date.py <date> [log_types...]

ARGUMENTS:
    date                    - Target date in various formats (required)
    log_types (optional)    - Specific log types: access, error, server

DATE FORMATS SUPPORTED:
    - YYYY-MM-DD           (e.g., 2024-01-15)
    - MM/DD/YYYY           (e.g., 01/15/2024)
    - DD/MM/YYYY           (e.g., 15/01/2024)
    - yesterday, today     (relative keywords)
    - N                    (N days ago, e.g., 1, 7, 30)

USAGE EXAMPLES:
    python get_logs_by_date.py yesterday
    python get_logs_by_date.py 7                     # 7 days ago
    python get_logs_by_date.py 2024-01-15
    python get_logs_by_date.py today error           # Only error logs for today
    python get_logs_by_date.py yesterday access server
    python get_logs_by_date.py 01/15/2024 error      # US date format

EXPECTED OUTPUTS:

1. Successful execution:
   === PythonAnywhere Historical Logs Fetcher ===
   Target date: 2024-01-15
   Current date: 2024-01-17
   
   📅 Fetching logs from 2 days ago
   
   ✓ API connection successful!
   
   Fetching all log types (access, error, server)
   
   === LOG ANALYSIS FOR 2024-01-15 ===
   
   ACCESS LOG:
     ✓ Successfully fetched
     📄 Lines: 456
     💾 Size: 78.3 KB
     📊 HTTP Status codes:
        ✅ 200: 320 requests
        ⚠️ 404: 15 requests
        ❌ 500: 12 requests
     🔝 First entry: 192.168.1.100 - - [15/Jan/2024:00:01:23 +0000]...
     🔻 Last entry:  203.45.67.89 - - [15/Jan/2024:23:58:45 +0000]...
   
   ERROR LOG:
     ✓ Successfully fetched
     📄 Lines: 89
     💾 Size: 15.7 KB
     🔍 Error breakdown:
        • ERROR: 8
        • Exception: 3
        • Failed: 1
   
   === SUMMARY FOR 2024-01-15 ===
   Successfully fetched: 3/3 log files
   🔍 Error analysis: 12 total error entries found
      Review error log details in downloaded files!

2. No logs found:
   === SUMMARY FOR 2024-01-01 ===
   Successfully fetched: 0/3 log files
   ❌ No logs found for this date.
      This could mean:
      - Logs for this date have been deleted/rotated
      - The date is too recent (logs might still be in current files)
      - The date format or log file naming convention has changed
   
   💡 Try:
      - Checking logs for adjacent dates
      - Using 'get_latest_logs.py' for recent logs
      - Using 'log_utils.py list' to see available historical logs

3. Invalid date format:
   Error parsing date: Unable to parse date: invalid-date
   Supported formats:
     - YYYY-MM-DD (e.g., 2024-01-15)
     - today, yesterday
     - Number of days ago (e.g., 1, 7, 30)

4. Invalid log types:
   Invalid log types: ['invalid_type']
   Valid types are: ['access', 'error', 'server']

OUTPUT FILES:
    Historical logs are saved with date and timestamp format:
    - access_log_2024-01-15_143022.txt
    - error_log_2024-01-15_143022.txt
    - server_log_2024-01-15_143022.txt

LOG FILE SEARCH STRATEGY:
    The script tries multiple naming conventions for rotated logs:
    - domain.log_type.log.YYYY-MM-DD
    - domain.log_type.log-YYYY-MM-DD  
    - domain.log_type.YYYY-MM-DD.log

TROUBLESHOOTING TIPS:
    - Recent dates (today/yesterday): Use get_latest_logs.py instead
    - Old dates: Logs may have been automatically deleted
    - Check available dates: Use python log_utils.py list
    - Alternative dates: Try adjacent dates (±1 day)

ENVIRONMENT REQUIREMENTS:
    PA_API_TOKEN, PA_USERNAME, PA_DOMAIN, PA_HOST must be set in .env file
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add current directory to Python path to import log_utils
sys.path.insert(0, str(Path(__file__).parent))

from log_utils import PythonAnywhereLogFetcher


def parse_date_input(date_input: str) -> str:
    """
    Parse various date input formats and return YYYY-MM-DD format.
    
    Supports:
    - YYYY-MM-DD (exact format)
    - yesterday, today
    - 1, 2, 3 (days ago)
    """
    date_input = date_input.lower().strip()
    
    # Handle relative date keywords
    if date_input == "today":
        return datetime.now().strftime("%Y-%m-%d")
    elif date_input == "yesterday":
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Handle "N days ago" format
    if date_input.isdigit():
        days_ago = int(date_input)
        target_date = datetime.now() - timedelta(days=days_ago)
        return target_date.strftime("%Y-%m-%d")
    
    # Try to parse as direct date
    try:
        # Support different input formats
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]:
            try:
                date_obj = datetime.strptime(date_input, fmt)
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        # If no format matches, raise error
        raise ValueError(f"Unable to parse date: {date_input}")
        
    except ValueError as e:
        print(f"Error parsing date: {e}")
        print("Supported formats:")
        print("  - YYYY-MM-DD (e.g., 2024-01-15)")
        print("  - today, yesterday")
        print("  - Number of days ago (e.g., 1, 7, 30)")
        sys.exit(1)


def main():
    """Main function to fetch logs by date."""
    print("=== PythonAnywhere Historical Logs Fetcher ===")
    
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python get_logs_by_date.py <date> [log_types...]")
        print()
        print("Date formats:")
        print("  - YYYY-MM-DD (e.g., 2024-01-15)")
        print("  - yesterday, today")
        print("  - Number of days ago (e.g., 1, 7, 30)")
        print()
        print("Log types (optional):")
        print("  - access, error, server")
        print("  - If not specified, fetches all types")
        print()
        print("Examples:")
        print("  python get_logs_by_date.py yesterday")
        print("  python get_logs_by_date.py 7")
        print("  python get_logs_by_date.py 2024-01-15 error")
        print("  python get_logs_by_date.py today access server")
        sys.exit(1)
    
    # Parse the date
    date_input = sys.argv[1]
    try:
        target_date = parse_date_input(date_input)
    except SystemExit:
        return
    
    # Parse log types if provided
    log_types = None
    if len(sys.argv) > 2:
        log_types = sys.argv[2:]
        # Validate log types
        valid_types = ["access", "error", "server"]
        invalid_types = [t for t in log_types if t not in valid_types]
        if invalid_types:
            print(f"Invalid log types: {invalid_types}")
            print(f"Valid types are: {valid_types}")
            return
    
    print(f"Target date: {target_date}")
    print(f"Current date: {datetime.now().strftime('%Y-%m-%d')}")
    print()
    
    # Calculate days ago for context
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        days_ago = (datetime.now() - target_dt).days
        if days_ago == 0:
            print("📅 Fetching logs for today")
        elif days_ago == 1:
            print("📅 Fetching logs for yesterday")
        elif days_ago > 0:
            print(f"📅 Fetching logs from {days_ago} days ago")
        else:
            print(f"📅 Fetching logs for future date (not typical)")
    except ValueError:
        pass
    
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
    
    if log_types:
        print(f"Fetching specific log types: {log_types}")
    else:
        print("Fetching all log types (access, error, server)")
    
    # Fetch the logs
    results = fetcher.get_log_by_date(target_date, log_types)
    
    print(f"\n=== LOG ANALYSIS FOR {target_date} ===")
    
    # Analyze and display results
    total_errors = 0
    successful_logs = 0
    
    for log_type, (success, content) in results.items():
        print(f"\n{log_type.upper()} LOG:")
        
        if success:
            successful_logs += 1
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
                        if 'error_rate_percent' in analysis:
                            error_emoji = "❌" if analysis['error_rate_percent'] > 10 else "⚠️" if analysis['error_rate_percent'] > 5 else "✅"
                            print(f"     • Error rate: {analysis['error_rate_percent']}% {error_emoji}")
            
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
            print(f"  ❌ {content}")
    
    # Summary
    print(f"\n=== SUMMARY FOR {target_date} ===")
    total_count = len(results)
    print(f"Successfully fetched: {successful_logs}/{total_count} log files")
    
    if successful_logs == 0:
        print("❌ No logs found for this date.")
        print("   This could mean:")
        print("   - Logs for this date have been deleted/rotated")
        print("   - The date is too recent (logs might still be in current files)")
        print("   - The date format or log file naming convention has changed")
        print("\n💡 Try:")
        print("   - Checking logs for adjacent dates")
        print("   - Using 'get_latest_logs.py' for recent logs")
        print("   - Using 'log_utils.py list' to see available historical logs")
    else:
        if total_errors > 0:
            print(f"🔍 Error analysis: {total_errors} total error entries found")
            print("   Review error log details in downloaded files")
        else:
            print("✅ No errors detected in logs")
    
    print(f"\n📁 Logs saved to: {fetcher.LOGS_DIR}")


if __name__ == "__main__":
    main() 