#!/usr/bin/env python3
import fnmatch
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# HTTP Status Codes
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NO_CONTENT = 204
HTTP_UNAUTHORIZED = 401
HTTP_TOO_MANY_REQUESTS = 429

# Configuration Constants
MIN_TOKEN_LENGTH = 8
DEFAULT_TIMEOUT = 30  # seconds
REQUEST_TIMEOUT = DEFAULT_TIMEOUT
MAX_RETRIES = 5
BASE_RETRY_DELAY = 1  # seconds
REQUESTS_PER_MINUTE = 35  # Conservative limit (PA allows 40, we use 35 for safety)
UPLOAD_STATE_FILE = "deployment_state.json"  # Track upload progress

# Project configuration - this is the root directory of the slack bot project
LOCAL_PROJECT_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file in project directory
try:
    from dotenv import load_dotenv

    env_path = LOCAL_PROJECT_DIR / ".env"
    if env_path.exists():
        print(f"Loading environment variables from {env_path}")
        load_dotenv(dotenv_path=env_path)
    else:
        print(f"Warning: .env file not found at {env_path}")
except ImportError:
    print("python-dotenv not installed. Using existing environment variables.")

# Configuration from environment variables (with .env file precedence)
PA_API_TOKEN = os.environ.get("PA_API_TOKEN", "").strip()
PA_USERNAME = os.environ.get("PA_USERNAME", "").strip()
PA_DOMAIN = os.environ.get("PA_DOMAIN", "").strip()
PA_HOST = os.environ.get("PA_HOST", "").strip()
# Deployment configuration
PA_SOURCE_DIR = os.environ.get("PA_SOURCE_DIR", "").strip()  # Path to source directory on PythonAnywhere
PA_VIRTUALENV_PATH = (
    f"/home/{PA_USERNAME}/{PA_SOURCE_DIR}/venv"  # Path to virtualenv on PythonAnywhere
)
os.environ.setdefault("FLASK_ENV", "production")

# Default exclusions in case .gitignore can't be loaded
DEFAULT_EXCLUDE_DIRS = [
    ".git",
    ".github",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    "*.md",
    "**/tests/*",
    "**/test_*.py",
    "*.log",
    "*.db",  # Exclude local SQLite databases
    ".DS_Store",
    "pythonanywhere_deploy",
]

# Load .gitignore patterns
try:
    import pathspec

    gitignore_path = LOCAL_PROJECT_DIR / ".gitignore"
    if gitignore_path.exists():
        print(f"Loading exclusion patterns from {gitignore_path}")
        with open(gitignore_path) as f:
            gitignore_patterns = f.read().splitlines()
            # Filter out comments and empty lines
            gitignore_patterns = [p for p in gitignore_patterns if p and not p.startswith("#")]
            print(f"Loaded {len(gitignore_patterns)} exclusion patterns")

            # Create a pathspec object from the patterns
            gitignore_spec = pathspec.PathSpec.from_lines(
                pathspec.patterns.GitWildMatchPattern, gitignore_patterns
            )
    else:
        print(f"Warning: .gitignore not found at {gitignore_path}")
        gitignore_spec = None
except ImportError:
    print("Warning: pathspec not installed. Using default exclusions only.")
    gitignore_spec = None

# API endpoints
API_BASE_URL = f"https://{PA_HOST}/api/v0/user/{PA_USERNAME}"
FILES_API_URL = f"{API_BASE_URL}/files/path"
RELOAD_API_URL = f"{API_BASE_URL}/webapps/{PA_DOMAIN}/reload/"
CONSOLES_API_URL = f"{API_BASE_URL}/consoles/"
CPU_API_URL = f"{API_BASE_URL}/cpu/"

# Common headers for API requests - ensure token is properly formatted
if PA_API_TOKEN.startswith("Token "):
    PA_API_TOKEN = PA_API_TOKEN.replace("Token ", "")
AUTH_HEADER = "Token " + PA_API_TOKEN
HEADERS = {"Authorization": AUTH_HEADER}

# Load environment variables from .prod.env if it exists
if os.path.exists('.prod.env'):
    load_dotenv('.prod.env')
else:
    load_dotenv()

def validate_environment():
    """Check if all required environment variables are set and properly formatted."""
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

    if not PA_VIRTUALENV_PATH:
        print("Warning: PA_VIRTUALENV_PATH not set. Skipping pip install step.")

    # Debug token length without revealing it
    masked_token = (
        f"{PA_API_TOKEN[:4]}...{PA_API_TOKEN[-4:]}"
        if len(PA_API_TOKEN) > MIN_TOKEN_LENGTH
        else "***"
    )
    print(f"Using API token: {masked_token} (length: {len(PA_API_TOKEN)})")
    print(f"Auth header: {AUTH_HEADER.replace(PA_API_TOKEN, masked_token)}")

    # Validate host format
    valid_hosts = ["eu.pythonanywhere.com", "www.pythonanywhere.com", "pythonanywhere.com"]
    if PA_HOST not in valid_hosts:
        print(
            f"Warning: PA_HOST '{PA_HOST}' might be invalid. Valid options are: {', '.join(valid_hosts)}"
        )


def test_api_connection():
    """Test the API connection by making a simple request.

    Returns:
        tuple: (success, headers) where success is a boolean indicating if the connection was successful
               and headers are the validated request headers
    """
    print(f"Testing API connection to {PA_HOST}...")

    # Create a copy of the headers to work with
    current_headers = HEADERS.copy()

    # Debug the headers without revealing full token
    debug_headers = current_headers.copy()
    if "Authorization" in debug_headers and debug_headers["Authorization"].startswith("Token "):
        token = debug_headers["Authorization"].split(" ")[1]
        masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > MIN_TOKEN_LENGTH else "***"
        debug_headers["Authorization"] = f"Token {masked_token}"

    print(f"Using headers: {debug_headers}")
    print(f"API URL: {CPU_API_URL}")

    try:
        rate_limiter.wait_if_needed()
        response = make_request_with_retry(requests.get, CPU_API_URL, headers=current_headers, timeout=REQUEST_TIMEOUT)

        if response.status_code == HTTP_OK:
            print("API connection successful!")
            return True, current_headers
        else:
            print(f"API connection failed with status code: {response.status_code}")
            print(f"Response content: {response.text}")

            if response.status_code == HTTP_UNAUTHORIZED:
                print("\n=== AUTHENTICATION ERROR ===")
                print("The API token was rejected. Please check:")
                print("1. The token is correctly entered")
                print("2. The token has not expired")
                print("3. The token is for the correct user")
                print(
                    "4. The Authorization header is correctly formatted as: 'Token YOUR_TOKEN_HERE'"
                )
                print("5. You're using the correct API host for your account location")
                print("You can generate a new token in your PythonAnywhere account settings.")

                # Try the alternative format as a last resort
                alt_headers = {"Authorization": "Token " + PA_API_TOKEN}
                print("\nTrying alternative header format...")
                try:
                    rate_limiter.wait_if_needed()
                    alt_response = make_request_with_retry(
                        requests.get, CPU_API_URL, headers=alt_headers, timeout=REQUEST_TIMEOUT
                    )
                    if alt_response.status_code == HTTP_OK:
                        print("Alternative header format worked!")
                        return True, alt_headers
                    else:
                        print(f"Alternative format also failed: {alt_response.status_code}")
                except Exception as e:
                    print(f"Error with alternative format: {e}")

            return False, current_headers
    except Exception as e:
        print(f"API connection error: {e}")
        return False, current_headers


def make_request_with_retry(request_func, *args, max_retries=MAX_RETRIES, **kwargs):
    """
    Make a request with retry logic for rate limiting and transient errors.
    
    Args:
        request_func: The requests function to call (requests.get, requests.post, etc.)
        *args: Arguments to pass to the request function
        max_retries: Maximum number of retry attempts
        **kwargs: Keyword arguments to pass to the request function
    
    Returns:
        Response object
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            response = request_func(*args, **kwargs)
            
            if response.status_code == HTTP_TOO_MANY_REQUESTS:
                # Parse the retry-after header or use default
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        wait_time = int(retry_after)
                    except ValueError:
                        # Fallback if Retry-After is not a number
                        wait_time = BASE_RETRY_DELAY * (2 ** attempt)
                else:
                    # Extract wait time from response body if available
                    try:
                        error_data = response.json()
                        detail = error_data.get('detail', '')
                        if 'Expected available in' in detail:
                            # Extract number from "Expected available in 42 seconds"
                            import re
                            match = re.search(r'(\d+) seconds', detail)
                            wait_time = int(match.group(1)) if match else BASE_RETRY_DELAY * (2 ** attempt)
                        else:
                            wait_time = BASE_RETRY_DELAY * (2 ** attempt)
                    except:
                        wait_time = BASE_RETRY_DELAY * (2 ** attempt)
                
                if attempt < max_retries:
                    print(f"Rate limited (429). Waiting {wait_time} seconds before retry {attempt + 1}/{max_retries}...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"Max retries ({max_retries}) exceeded for rate limiting.")
                    return response
            
            # Check for other retryable errors (5xx server errors, connection issues)
            elif response.status_code >= 500:
                if attempt < max_retries:
                    wait_time = BASE_RETRY_DELAY * (2 ** attempt)
                    print(f"Server error {response.status_code}. Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"Max retries exceeded for server error {response.status_code}")
                    return response
            
            # Success or non-retryable error
            return response
            
        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = BASE_RETRY_DELAY * (2 ** attempt)
                print(f"Request exception: {e}. Retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                print(f"Max retries exceeded for request exception: {e}")
                raise e
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


def upload_file(local_path, remote_path, headers=HEADERS):
    """Upload a single file to PythonAnywhere with retry logic."""
    # Apply rate limiting before making the request
    rate_limiter.wait_if_needed()
    
    with open(local_path, "rb") as f:
        content = f.read()

    # Fix: Ensure remote_path starts with a slash but doesn't have duplicate slashes
    if not remote_path.startswith("/"):
        remote_path = f"/{remote_path}"

    url = f"{FILES_API_URL}{remote_path}"
    print(f"Uploading to: {url}")

    try:
        response = make_request_with_retry(
            requests.post,
            url, 
            headers=headers, 
            files={"content": ("filename", content)}, 
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code in (HTTP_OK, HTTP_CREATED):
            print(f"✅ Uploaded: {remote_path}")
            return True
        else:
            print(f"❌ Failed to upload {remote_path}: {response.status_code}")
            print(f"Response: {response.text[:500]}...")  # Print first 500 chars of response
            return False
    except Exception as e:
        print(f"❌ Error uploading {remote_path}: {e}")
        return False


def should_exclude(path):
    """Check if a path should be excluded from upload."""
    path_str = str(path)

    # Get the filename and extension
    filename = path.name

    # First check hardcoded exclusions for common directories
    for exclude_pattern in DEFAULT_EXCLUDE_DIRS:
        # Handle directory name exact matches (no wildcards)
        if (
            "*" not in exclude_pattern
            and "?" not in exclude_pattern
            and exclude_pattern in path_str.split(os.sep)
        ):
            print(f"Excluding (directory match): {path_str}")
            return True

        # Handle wildcard patterns using fnmatch
        if "*" in exclude_pattern or "?" in exclude_pattern:
            # Check against the full path (with forward slashes for consistency)
            norm_path = path_str.replace("\\", "/")
            # Handle patterns that start with ** (match anywhere in path)
            if exclude_pattern.startswith("**/"):
                pattern = exclude_pattern[3:]  # Remove **/ prefix
                # Check if pattern matches any part of the path
                for part in norm_path.split("/"):
                    if fnmatch.fnmatch(part, pattern):
                        print(f"Excluding (wildcard match '{exclude_pattern}'): {path_str}")
                        return True
                # Also check against the full path for patterns like **/tests/*
                if fnmatch.fnmatch(norm_path, f"*/{pattern}") or fnmatch.fnmatch(
                    norm_path, pattern
                ):
                    print(f"Excluding (path wildcard match '{exclude_pattern}'): {path_str}")
                    return True
            # Direct file pattern match (like *.md)
            elif fnmatch.fnmatch(filename, exclude_pattern):
                print(f"Excluding (filename pattern '{exclude_pattern}'): {path_str}")
                return True

    # Then check against gitignore patterns if available
    if gitignore_spec:
        # Get the path relative to the base directory
        rel_path = path.relative_to(LOCAL_PROJECT_DIR)
        rel_path_str = str(rel_path).replace("\\", "/")

        # Check if the path matches any gitignore pattern
        if gitignore_spec.match_file(rel_path_str):
            print(f"Excluding (gitignore match): {rel_path_str}")
            return True

    return False


def upload_directory(local_dir, remote_path=None, headers=HEADERS):
    """Upload all files in a directory recursively with resume capability."""
    print(f"📁 Uploading directory {local_dir} to remote path {remote_path}")
    
    # Load previous state if it exists
    previous_state = load_upload_state()
    uploaded_files = set(previous_state.get("uploaded_files", [])) if previous_state else set()
    failed_files = set(previous_state.get("failed_files", [])) if previous_state else set()
    
    # Collect all files to upload
    all_files = []
    excluded_count = 0
    
    for root, dirs, files in os.walk(local_dir):
        # Skip excluded directories - modify dirs in place to avoid walking
        dirs[:] = [d for d in dirs if not should_exclude(Path(root) / d)]

        for file in files:
            local_path = Path(root) / file

            # Skip excluded files
            if should_exclude(local_path):
                excluded_count += 1
                continue

            # Create the remote path
            if remote_path:
                # If remote_path is specified, use it as the base
                rel_path = local_path.relative_to(local_dir)
                file_remote_path = f"{remote_path}/{rel_path}"
            else:
                # Otherwise use the full path relative to LOCAL_PROJECT_DIR
                rel_path = local_path.relative_to(LOCAL_PROJECT_DIR)
                file_remote_path = f"/{rel_path}"

            # Convert Windows backslashes to forward slashes if needed
            file_remote_path = str(file_remote_path).replace("\\", "/")
            
            all_files.append((local_path, file_remote_path))
    
    total_files = len(all_files)
    success_count = len(uploaded_files)
    failed_count = len(failed_files)
    
    print(f"📊 Upload Summary:")
    print(f"   - Total files to process: {total_files}")
    print(f"   - Already uploaded: {success_count}")
    print(f"   - Previously failed: {failed_count}")
    print(f"   - Remaining: {total_files - success_count}")
    print(f"   - Excluded: {excluded_count}")
    
    if previous_state:
        response = input("Do you want to resume the previous upload? (y/n): ").lower().strip()
        if response != 'y':
            uploaded_files.clear()
            failed_files.clear()
            success_count = 0
            failed_count = 0
            print("🔄 Starting fresh upload...")
    
    # Upload remaining files
    for i, (local_path, file_remote_path) in enumerate(all_files, 1):
        # Skip files that were already successfully uploaded
        if file_remote_path in uploaded_files:
            continue
        
        # Retry failed files, but show a warning
        if file_remote_path in failed_files:
            print(f"🔄 Retrying previously failed file: {file_remote_path}")
            failed_files.discard(file_remote_path)
        
        progress = f"[{i}/{total_files}]"
        print(f"\n{progress} Processing: {file_remote_path}")
        
        # Upload the file
        if upload_file(local_path, file_remote_path, headers):
            uploaded_files.add(file_remote_path)
            success_count += 1
        else:
            failed_files.add(file_remote_path)
            failed_count += 1
            print(f"❌ Failed to upload {file_remote_path}")
        
        # Save state periodically (every 10 files) and after each upload
        if i % 10 == 0 or i == total_files:
            save_upload_state(uploaded_files, failed_files, total_files)
    
    # Final summary
    actual_success_count = len(uploaded_files)
    actual_failed_count = len(failed_files)
    
    print(f"\n📈 Final Upload Results:")
    print(f"   - Successfully uploaded: {actual_success_count}/{total_files}")
    print(f"   - Failed uploads: {actual_failed_count}")
    print(f"   - Excluded files: {excluded_count}")
    
    if actual_failed_count > 0:
        print(f"\n❌ Failed files:")
        for failed_file in sorted(failed_files):
            print(f"   - {failed_file}")
        print(f"\n💡 You can re-run the script to retry failed uploads.")
        return False
    else:
        print(f"✅ All files uploaded successfully!")
        clear_upload_state()
        return True


def get_existing_consoles():
    """Get a list of existing consoles."""
    print("Checking for existing consoles...")
    rate_limiter.wait_if_needed()
    response = make_request_with_retry(requests.get, CONSOLES_API_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)

    if response.status_code == HTTP_OK:
        consoles = response.json()
        print(f"Found {len(consoles)} existing consoles")
        return consoles
    else:
        print(f"Failed to get console list: {response.status_code} {response.text}")
        return []


def clean_up_consoles(max_to_keep=3):
    """Delete old consoles, keeping a few recent ones."""
    consoles = get_existing_consoles()

    if len(consoles) < max_to_keep:
        return True  # No need to clean up

    # Sort consoles by id (higher id = more recent)
    consoles.sort(key=lambda c: c.get("id", 0))

    # Delete older consoles, keeping the most recent ones
    consoles_to_delete = consoles[:-max_to_keep] if max_to_keep > 0 else consoles

    success = True
    for console in consoles_to_delete:
        console_id = console.get("id")
        print(f"Deleting old console {console_id}...")
        if not close_console(console_id):
            print(f"Failed to delete console {console_id}")
            success = False

    return success


def create_console():
    """Create a new console for running commands."""
    # First clean up existing consoles if needed
    clean_up_consoles()

    print("Creating new console...")
    rate_limiter.wait_if_needed()
    response = make_request_with_retry(
        requests.post,
        CONSOLES_API_URL,
        headers=HEADERS,
        json={"executable": "bash", "arguments": "", "working_directory": f"/home/{PA_USERNAME}"},
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == HTTP_CREATED:
        console_id = response.json()["id"]
        print(f"Console created with ID: {console_id}")
        return console_id
    else:
        print(f"Failed to create console: {response.status_code} {response.text}")

        # If we hit a limit, try cleaning up all consoles and try again
        if "limit" in response.text.lower():
            print("Hit console limit. Attempting to clean up all consoles and retry...")
            if clean_up_consoles(max_to_keep=0):  # Delete all consoles
                # Try creating a console again
                return create_console()

        return None


def run_command_in_console(console_id, command):
    """Run a command in the console and wait for it to complete."""
    input_url = f"{CONSOLES_API_URL}{console_id}/send_input/"
    output_url = f"{CONSOLES_API_URL}{console_id}/get_latest_output/"

    print(f"Running command: {command}")

    # Send the command
    rate_limiter.wait_if_needed()
    response = make_request_with_retry(
        requests.post, input_url, headers=HEADERS, json={"input": f"{command}\n"}, timeout=REQUEST_TIMEOUT
    )

    if response.status_code != HTTP_OK:
        print(f"Failed to send command: {response.status_code} {response.text}")
        return False, ""

    # Wait for command to complete (checking for prompt)
    output = ""
    attempts = 0
    max_attempts = 30  # Timeout after 30 attempts (5 minutes)

    # Wait a moment for the command to start
    time.sleep(2)

    while attempts < max_attempts:
        rate_limiter.wait_if_needed()
        output_response = make_request_with_retry(requests.get, output_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

        if output_response.status_code == HTTP_OK:
            new_output = output_response.json().get("output", "")
            output += new_output

            # Check if the command has completed (bash prompt reappeared)
            if "$" in new_output.splitlines()[-1:][0]:
                break

        else:
            print(f"Failed to get output: {output_response.status_code} {output_response.text}")
            return False, output

        attempts += 1
        time.sleep(10)  # Check every 10 seconds

    # Check if we timed out
    if attempts >= max_attempts:
        print("Command execution timed out.")
        return False, output

    # Check for error indicators in the output
    error_indicators = ["error:", "exception:", "failed", "traceback"]
    has_errors = any(indicator in output.lower() for indicator in error_indicators)

    if has_errors:
        print("Warning: Potential errors detected in command output.")
        print(output)
        return False, output

    return True, output


def install_requirements(console_id):
    """Install Python requirements in the virtual environment."""
    if not PA_VIRTUALENV_PATH:
        print("Skipping requirements installation (virtualenv path not set)")
        return True

    print(f"Installing requirements in {PA_VIRTUALENV_PATH}...")

    # First, create virtual environment if it doesn't exist
    create_venv_command = f"cd /home/{PA_USERNAME}/{PA_SOURCE_DIR} && python3 -m venv venv"
    success, output = run_command_in_console(console_id, create_venv_command)
    if not success:
        print("Warning: Failed to create virtual environment (may already exist)")

    # Activate virtualenv and install requirements
    command = f"source {PA_VIRTUALENV_PATH}/bin/activate && cd /home/{PA_USERNAME}/{PA_SOURCE_DIR} && pip install -r requirements.txt"
    success, output = run_command_in_console(console_id, command)

    if success:
        print("Requirements installed successfully.")
    else:
        print("Failed to install requirements.")

    return success


def run_migrations(console_id):
    """Run Flask database migrations."""
    if not PA_VIRTUALENV_PATH:
        print("Skipping migrations (virtualenv path not set)")
        return True

    print("Running Flask database migrations...")

    # Activate virtualenv and run Flask migrations
    # First initialize migrations if migrations folder doesn't exist
    init_command = f"source {PA_VIRTUALENV_PATH}/bin/activate && cd /home/{PA_USERNAME}/{PA_SOURCE_DIR} && python -c \"import os; from flask_migrate import init; init() if not os.path.exists('migrations') else print('Migrations already initialized')\""
    success, output = run_command_in_console(console_id, init_command)

    # Create migration if needed
    migrate_command = f"source {PA_VIRTUALENV_PATH}/bin/activate && cd /home/{PA_USERNAME}/{PA_SOURCE_DIR} && flask db migrate -m 'Auto migration'"
    success, output = run_command_in_console(console_id, migrate_command)

    # Apply migrations
    upgrade_command = f"source {PA_VIRTUALENV_PATH}/bin/activate && cd /home/{PA_USERNAME}/{PA_SOURCE_DIR} && flask db upgrade"
    success, output = run_command_in_console(console_id, upgrade_command)

    if success:
        print("Migrations applied successfully.")
    else:
        print("Failed to apply migrations.")

    return success


def close_console(console_id):
    """Close the console after use."""
    if not console_id:
        return False

    print(f"Closing console {console_id}...")
    rate_limiter.wait_if_needed()
    response = make_request_with_retry(
        requests.delete, f"{CONSOLES_API_URL}{console_id}/", headers=HEADERS, timeout=REQUEST_TIMEOUT
    )

    if response.status_code == HTTP_NO_CONTENT:
        print("Console closed successfully.")
        return True
    else:
        print(f"Failed to close console: {response.status_code} {response.text}")
        return False


def reload_webapp(headers=HEADERS):
    """Reload the web application to apply changes."""
    print(f"Reloading web application {PA_DOMAIN}...")
    rate_limiter.wait_if_needed()
    response = make_request_with_retry(requests.post, RELOAD_API_URL, headers=headers, timeout=REQUEST_TIMEOUT)

    if response.status_code == HTTP_OK:
        print("Web application reloaded successfully")
        return True
    else:
        print(f"Failed to reload web application: {response.status_code} {response.text}")
        return False


def upload_env_file(headers=HEADERS):
    """Upload .prod.env as .env to the server."""
    if not os.path.exists('.prod.env'):
        print("No .prod.env file found, skipping environment variables setup")
        return False
    
    print("Uploading .prod.env as .env...")
    remote_env_path = f"/home/{PA_USERNAME}/{PA_SOURCE_DIR}/.env"
    
    if upload_file('.prod.env', remote_env_path, headers):
        print("Environment file uploaded successfully")
        return True
    else:
        print("Failed to upload environment file")
        return False


def run_post_deployment_tasks(headers=HEADERS):
    """Run post-deployment tasks directly using a console."""
    print("\n=== Running post-deployment tasks ===")

    # Create a console to run commands
    console_id = create_console()
    if not console_id:
        print("Failed to create console for post-deployment tasks")
        return False

    success = True
    try:
        # Install requirements
        if not install_requirements(console_id):
            print("Warning: Requirements installation had issues")
            success = False

        # Run migrations
        if not run_migrations(console_id):
            print("Warning: Database migrations had issues")
            success = False

        # Note: Flask doesn't have collectstatic like Django
        print("Skipping static file collection (Flask doesn't require collectstatic)")

    finally:
        # Make sure we close the console even if there are errors
        close_console(console_id)

    if success:
        print("Post-deployment tasks completed successfully")
    else:
        print("Post-deployment tasks completed with warnings")

    return success


def collect_static(console_id):
    """Collect static files - Not needed for Flask applications."""
    print("Skipping static file collection (Flask doesn't require collectstatic)")
    return True


def test_exclusions():
    """Test the exclusion logic with a set of example paths to verify it works correctly."""
    print("\n=== Testing exclusion patterns ===")

    # Create a list of test paths that should be excluded
    test_exclude_paths = [
        LOCAL_PROJECT_DIR / "README.md",  # *.md pattern
        LOCAL_PROJECT_DIR / "docs" / "api.md",  # *.md pattern in subdirectory
        LOCAL_PROJECT_DIR / "tests" / "test_api.py",  # **/tests/* pattern
        LOCAL_PROJECT_DIR / "app" / "tests" / "config.py",  # **/tests/* pattern
        LOCAL_PROJECT_DIR / "test_utils.py",  # **/test_*.py pattern
        LOCAL_PROJECT_DIR / ".git" / "config",  # directory match
        LOCAL_PROJECT_DIR / "node_modules" / "package.json",  # directory match
        LOCAL_PROJECT_DIR / "ab_testing.db",  # *.db pattern
        LOCAL_PROJECT_DIR / "app.log",  # *.log pattern
    ]

    # Create a list of test paths that should be included
    test_include_paths = [
        LOCAL_PROJECT_DIR / "server.py",  # Main Flask app file
        LOCAL_PROJECT_DIR / "models.py",  # SQLAlchemy models
        LOCAL_PROJECT_DIR / "config.py",  # Configuration file
        LOCAL_PROJECT_DIR / "requirements.txt",  # Dependencies
        LOCAL_PROJECT_DIR / "services" / "claude_service.py",  # Service files
        LOCAL_PROJECT_DIR / "views" / "app_home.json",  # View templates
    ]

    # Test the paths that should be excluded
    print("\nPaths that should be excluded:")
    excluded_count = 0
    for path in test_exclude_paths:
        result = should_exclude(path)
        status = "✓ Excluded" if result else "✗ NOT excluded"
        print(f"{status}: {path}")
        if result:
            excluded_count += 1

    # Test the paths that should be included
    print("\nPaths that should be included:")
    included_count = 0
    for path in test_include_paths:
        result = not should_exclude(path)
        status = "✓ Included" if result else "✗ NOT included"
        print(f"{status}: {path}")
        if result:
            included_count += 1

    # Print the summary
    print(f"\nCorrectly excluded: {excluded_count}/{len(test_exclude_paths)}")
    print(f"Correctly included: {included_count}/{len(test_include_paths)}")

    # Return whether all tests passed
    return excluded_count == len(test_exclude_paths) and included_count == len(test_include_paths)


class RateLimiter:
    """Simple rate limiter to respect API limits."""
    
    def __init__(self, requests_per_minute=REQUESTS_PER_MINUTE):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute  # seconds between requests
        self.last_request_time = 0
    
    def wait_if_needed(self):
        """Wait if necessary to respect rate limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            wait_time = self.min_interval - time_since_last
            print(f"⏱️  Rate limiting: waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
        
        self.last_request_time = time.time()


# Global rate limiter instance
rate_limiter = RateLimiter()


def save_upload_state(uploaded_files, failed_files, total_files):
    """Save the current upload state to resume later."""
    try:
        import json
        state = {
            "uploaded_files": list(uploaded_files),
            "failed_files": list(failed_files), 
            "total_files": total_files,
            "timestamp": time.time()
        }
        with open(UPLOAD_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"💾 Saved upload state to {UPLOAD_STATE_FILE}")
    except Exception as e:
        print(f"⚠️  Failed to save upload state: {e}")


def load_upload_state():
    """Load previous upload state if it exists."""
    try:
        import json
        if os.path.exists(UPLOAD_STATE_FILE):
            with open(UPLOAD_STATE_FILE, "r") as f:
                state = json.load(f)
            print(f"📂 Loaded previous upload state from {UPLOAD_STATE_FILE}")
            print(f"   - {len(state.get('uploaded_files', []))} files already uploaded")
            print(f"   - {len(state.get('failed_files', []))} files previously failed")
            return state
    except Exception as e:
        print(f"⚠️  Failed to load upload state: {e}")
    return None


def clear_upload_state():
    """Clear the upload state file after successful deployment."""
    try:
        if os.path.exists(UPLOAD_STATE_FILE):
            os.remove(UPLOAD_STATE_FILE)
            print(f"🧹 Cleared upload state file")
    except Exception as e:
        print(f"⚠️  Failed to clear upload state: {e}")


def main():
    """Main deployment function."""
    validate_environment()

    # Check command line arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        
        if arg == "--test-only":
            test_exclusions()
            return
        elif arg == "--test":
            if not test_exclusions():
                print("Exclusion tests failed! Deployment aborted.")
                sys.exit(1)
        elif arg == "--resume":
            print("🔄 Resume mode: Will attempt to resume any previous interrupted deployment.")
        elif arg == "--retry-failed":
            print("🔄 Retry mode: Will retry only previously failed uploads.")
            # Load previous state and clear successful uploads, keeping only failed ones
            previous_state = load_upload_state()
            if previous_state:
                # Keep only failed files for retry
                failed_files = previous_state.get("failed_files", [])
                if failed_files:
                    print(f"Found {len(failed_files)} failed files to retry")
                    # Create a new state with only failed files
                    save_upload_state(set(), set(failed_files), len(failed_files))
                else:
                    print("No failed files found to retry")
                    return
            else:
                print("No previous deployment state found")
                return
        elif arg == "--clear-state":
            clear_upload_state()
            print("🧹 Cleared deployment state. Next run will start fresh.")
            return
        elif arg == "--help":
            print("PythonAnywhere Deployment Script")
            print("Usage:")
            print("  python deploy_to_pythonanywhere.py [options]")
            print("")
            print("Options:")
            print("  --test-only        Run exclusion tests only")
            print("  --test            Run exclusion tests before deployment") 
            print("  --resume          Resume interrupted deployment")
            print("  --retry-failed    Retry only previously failed uploads")
            print("  --clear-state     Clear deployment state and start fresh")
            print("  --help            Show this help message")
            print("")
            print("The script automatically handles:")
            print("  - Rate limiting (35 requests/minute)")
            print("  - Retry logic with exponential backoff")
            print("  - Resume capability for interrupted deployments")
            print("  - Progress tracking and state persistence")
            return

    print(f"🚀 Deploying Slack Bot to PythonAnywhere for user {PA_USERNAME}")
    print(f"🌐 Domain: {PA_DOMAIN}")
    print(f"🖥️  API Host: {PA_HOST}")
    print(f"⚡ Rate limit: {REQUESTS_PER_MINUTE} requests/minute")

    # Test the API connection before proceeding
    success, updated_headers = test_api_connection()
    if not success:
        print("API connection test failed. Please check your credentials and network connection.")
        sys.exit(1)

    # Use the validated headers for all subsequent requests
    headers = updated_headers

    # Upload the project directory
    if not upload_directory(LOCAL_PROJECT_DIR, f"/home/{PA_USERNAME}/{PA_SOURCE_DIR}", headers):
        print("❌ Some files failed to upload. You can re-run the script to retry.")
        print("💡 Use --retry-failed to retry only the failed files.")
        sys.exit(1)

    print("✅ All files uploaded successfully")

    # Upload .prod.env as .env file
    if not upload_env_file(headers):
        print("⚠️  Warning: Failed to upload environment file")

    # Run post-deployment tasks
    if not run_post_deployment_tasks(headers):
        print("⚠️  Warning: Post-deployment tasks had issues")

    # Reload the web application
    if not reload_webapp(headers):
        sys.exit(1)

    print("🎉 Deployment completed successfully!")
    print("🧹 Cleaning up deployment state...")
    clear_upload_state()


if __name__ == "__main__":
    main()
