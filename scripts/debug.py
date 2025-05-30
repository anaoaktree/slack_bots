#!/usr/bin/env python3
"""
Quick launcher for PythonAnywhere debugging tools.

This script provides a simple menu to access all debugging functionality
without needing to remember specific script names and commands.

USAGE:
    python debug.py

DESCRIPTION:
    Main launcher script that provides a unified interface to all PythonAnywhere
    debugging tools. Features an interactive menu system with organized categories
    for quick log access, troubleshooting, and advanced utilities.

MENU INTERFACE:

📊 QUICK LOG ACCESS:
  1. Get latest logs (most common)
     - Runs: python get_latest_logs.py
     - Downloads current access, error, and server logs
     - Provides immediate analysis and statistics

  2. Get logs by date
     - Runs: python get_logs_by_date.py <user_input>
     - Prompts for date input (yesterday, 7, 2024-01-15, etc.)
     - Retrieves historical logs for investigation

  3. Test API connection
     - Runs: python log_utils.py test
     - Validates PythonAnywhere API credentials
     - Confirms environment configuration

🔍 TROUBLESHOOTING:
  4. Interactive troubleshooting guide
     - Runs: python troubleshoot.py
     - Guided problem-solving for common issues
     - Automated log pattern analysis

  5. Emergency: Get all recent logs
     - Runs: python get_latest_logs.py
     - Quick download for critical situations
     - Provides emergency response recommendations

⚙️ ADVANCED:
  6. Core log utilities (CLI)
     - Runs: python log_utils.py <command>
     - Direct access to utility functions
     - Commands: test, latest, date, list

  7. View logs directory
     - Shows: scripts/logs/ directory contents
     - Lists downloaded log files with timestamps
     - Displays file sizes and modification times

  8. Show README documentation
     - Displays: scripts/README.md
     - Complete usage documentation
     - Opens in pager (less) if available

EXPECTED OUTPUTS:

1. Main Menu:
   ============================================================
   🔧 PythonAnywhere Flask App Debugging Tools
   ============================================================
   
   Choose a debugging tool:
   
   📊 QUICK LOG ACCESS:
     1. Get latest logs (most common)
     2. Get logs by date
     3. Test API connection
   
   🔍 TROUBLESHOOTING:
     4. Interactive troubleshooting guide
     5. Emergency: Get all recent logs
   
   ⚙️  ADVANCED:
     6. Core log utilities (CLI)
     7. View logs directory
     8. Show README documentation
   
     0. Exit
   
   Enter your choice (0-8):

2. Date Input Prompt (Option 2):
   📅 Enter date for historical logs:
   Examples: yesterday, 3 (days ago), 2024-01-15
   
   Date: [user input]

3. Advanced CLI Prompt (Option 6):
   ⚙️  Core log utilities:
   Available commands:
     test    - Test API connection
     latest  - Get latest logs
     date    - Get logs for specific date
     list    - List available log files
   
   Enter command: [user input]

4. Logs Directory View (Option 7):
   📁 Logs directory: /path/to/scripts/logs
      Found 8 log files:
   
      📄 error_log_20240115_143022.txt (525.1 KB, 2024-01-15 14:30)
      📄 access_log_20240115_143022.txt (38.5 KB, 2024-01-15 14:30)
      📄 server_log_20240115_143022.txt (161.2 KB, 2024-01-15 14:30)
      ... and 5 more files
   
   💡 Tip: You can open these files in any text editor to review details.

5. Empty Logs Directory:
   📁 Logs directory is empty.
      Run a log fetching command to download logs.

6. Error Handling:
   ❌ Invalid choice. Please try again.
   OR
   Error running get_latest_logs.py: [error details]

NAVIGATION:
    - Use numeric choices (0-8) to navigate menu
    - Press Ctrl+C to exit at any time  
    - Press Enter to continue after each operation
    - Option 0 to exit the program cleanly

SUBPROCESS EXECUTION:
    All menu options execute the appropriate Python scripts as subprocesses
    while maintaining the current environment and working directory.

FILE ORGANIZATION:
    The launcher expects these files in the same directory:
    - log_utils.py          (core utilities)
    - get_latest_logs.py    (latest log fetcher)
    - get_logs_by_date.py   (historical log fetcher)
    - troubleshoot.py       (interactive guide)
    - README.md             (documentation)
    - logs/                 (output directory)

ERROR RECOVERY:
    - Invalid menu choices are handled gracefully
    - Subprocess errors are caught and displayed
    - Keyboard interrupts (Ctrl+C) are handled cleanly
    - Missing files or directories are reported clearly

ENVIRONMENT REQUIREMENTS:
    PA_API_TOKEN, PA_USERNAME, PA_DOMAIN, PA_HOST must be set in .env file
    All debugging scripts share the same environment requirements.
"""

import subprocess
import sys
from pathlib import Path

def print_banner():
    """Print welcome banner."""
    print("=" * 60)
    print("🔧 PythonAnywhere Flask App Debugging Tools")
    print("=" * 60)
    print()

def print_menu():
    """Print main menu options."""
    print("Choose a debugging tool:")
    print()
    print("📊 QUICK LOG ACCESS:")
    print("  1. Get latest logs (most common)")
    print("  2. Get logs by date")
    print("  3. Test API connection")
    print()
    print("🔍 TROUBLESHOOTING:")
    print("  4. Interactive troubleshooting guide")
    print("  5. Emergency: Get all recent logs")
    print()
    print("⚙️  ADVANCED:")
    print("  6. Core log utilities (CLI)")
    print("  7. View logs directory")
    print("  8. Show README documentation")
    print()
    print("  0. Exit")
    print()

def run_script(script_name, args=None):
    """Run a script with optional arguments."""
    script_path = Path(__file__).parent / script_name
    cmd = [sys.executable, str(script_path)]
    
    if args:
        cmd.extend(args)
    
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled.")
    except Exception as e:
        print(f"Error running {script_name}: {e}")

def show_logs_directory():
    """Show contents of logs directory."""
    logs_dir = Path(__file__).parent / "logs"
    
    if not logs_dir.exists():
        print("📁 Logs directory doesn't exist yet.")
        print("   Run a log fetching command first to create it.")
        return
    
    log_files = list(logs_dir.glob("*.txt"))
    
    if not log_files:
        print("📁 Logs directory is empty.")
        print("   Run a log fetching command to download logs.")
        return
    
    print(f"📁 Logs directory: {logs_dir}")
    print(f"   Found {len(log_files)} log files:")
    print()
    
    # Sort by modification time (newest first)
    log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    for log_file in log_files[:10]:  # Show most recent 10 files
        size_kb = log_file.stat().st_size / 1024
        mod_time = log_file.stat().st_mtime
        from datetime import datetime
        mod_str = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
        print(f"   📄 {log_file.name} ({size_kb:.1f} KB, {mod_str})")
    
    if len(log_files) > 10:
        print(f"   ... and {len(log_files) - 10} more files")
    
    print()
    print("💡 Tip: You can open these files in any text editor to review details.")

def show_readme():
    """Show README documentation."""
    readme_path = Path(__file__).parent / "README.md"
    
    if readme_path.exists():
        try:
            # Try to use a pager if available
            subprocess.run(["less", str(readme_path)], check=False)
        except FileNotFoundError:
            # Fallback to basic display
            with open(readme_path) as f:
                content = f.read()
                print(content)
    else:
        print("README.md not found in scripts directory.")

def get_date_input():
    """Get date input from user for historical logs."""
    print("📅 Enter date for historical logs:")
    print("Examples: yesterday, 3 (days ago), 2024-01-15")
    print()
    
    try:
        date_input = input("Date: ").strip()
        if not date_input:
            print("No date provided, using 'yesterday'")
            return "yesterday"
        return date_input
    except KeyboardInterrupt:
        print("\nCancelled.")
        return None

def main():
    """Main menu loop."""
    print_banner()
    
    while True:
        print_menu()
        
        try:
            choice = input("Enter your choice (0-8): ").strip()
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        
        print()
        
        if choice == "0":
            print("👋 Goodbye!")
            break
        
        elif choice == "1":
            print("🚀 Fetching latest logs...")
            run_script("get_latest_logs.py")
        
        elif choice == "2":
            date_input = get_date_input()
            if date_input:
                print(f"📅 Fetching logs for: {date_input}")
                run_script("get_logs_by_date.py", [date_input])
        
        elif choice == "3":
            print("🔌 Testing API connection...")
            run_script("log_utils.py", ["test"])
        
        elif choice == "4":
            print("🔍 Starting interactive troubleshooting...")
            run_script("troubleshoot.py")
        
        elif choice == "5":
            print("🆘 Emergency: Fetching all recent logs...")
            run_script("get_latest_logs.py")
            print("\n🚨 Also consider:")
            print("   - Check PythonAnywhere dashboard for resource usage")
            print("   - Review recent deployments")
            print("   - Consider restarting the web app")
        
        elif choice == "6":
            print("⚙️  Core log utilities:")
            print("Available commands:")
            print("  test    - Test API connection")
            print("  latest  - Get latest logs")
            print("  date    - Get logs for specific date")
            print("  list    - List available log files")
            print()
            
            try:
                cmd = input("Enter command: ").strip()
                if cmd:
                    args = [cmd]
                    if cmd == "date":
                        date_input = get_date_input()
                        if date_input:
                            args.append(date_input)
                        else:
                            continue
                    run_script("log_utils.py", args)
            except KeyboardInterrupt:
                print("\nCancelled.")
        
        elif choice == "7":
            show_logs_directory()
        
        elif choice == "8":
            show_readme()
        
        else:
            print("❌ Invalid choice. Please try again.")
        
        if choice != "0":
            input("\nPress Enter to continue...")
            print()

if __name__ == "__main__":
    main() 