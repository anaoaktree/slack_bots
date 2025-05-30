#!/usr/bin/env python3
"""
Script to reload the PythonAnywhere web app to pick up new code changes.
"""

import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('../.env')

def reload_webapp():
    """Reload the web app via PythonAnywhere API."""
    try:
        username = os.getenv('PA_USERNAME', 'chachibt')
        api_token = os.getenv('PA_API_TOKEN')
        domain_name = os.getenv('PA_DOMAIN', 'chachibt.pythonanywhere.com')
        host = os.getenv('PA_HOST', 'www.pythonanywhere.com')
        
        if not api_token:
            print("❌ PA_API_TOKEN not found in environment variables")
            print("💡 You can manually reload via the PythonAnywhere Web tab instead")
            return False
        
        print(f"🔄 Reloading web app: {domain_name}")
        
        response = requests.post(
            f'https://{host}/api/v0/user/{username}/webapps/{domain_name}/reload/',
            headers={'Authorization': f'Token {api_token}'}
        )
        
        if response.status_code == 200:
            print('✅ Web app reloaded successfully!')
            print('🎉 Your new view files should now be active')
            return True
        else:
            print(f'❌ Reload failed with status {response.status_code}: {response.content}')
            print("💡 Try manually reloading via the PythonAnywhere Web tab")
            return False
            
    except Exception as e:
        print(f'❌ Error reloading web app: {e}')
        print("💡 Try manually reloading via the PythonAnywhere Web tab")
        return False

if __name__ == "__main__":
    print("=== PythonAnywhere Web App Reloader ===")
    reload_webapp()