# PythonAnywhere Deployment Guide

This guide explains how to deploy your Flask Slack bot to PythonAnywhere using the updated deployment script.

## Prerequisites

1. A PythonAnywhere account
2. A domain/webapp configured on PythonAnywhere
3. API token from your PythonAnywhere account

## Environment Configuration

Create a `.env` file in your project root with the following variables:

```bash
# PythonAnywhere Deployment Configuration
PA_API_TOKEN=your_pythonanywhere_api_token
PA_USERNAME=your_pythonanywhere_username
PA_DOMAIN=your_domain.pythonanywhere.com

# Flask Configuration
FLASK_ENV=production
SECRET_KEY=your_secret_key_here

# Slack Bot Configuration
CHACHIBT_APP_BOT_AUTH_TOKEN=xoxb-your-slack-bot-token

# Database Configuration (for production on PythonAnywhere)
MYSQL_HOST=your_mysql_host
MYSQL_USER=your_mysql_username
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=your_database_name

# Optional: Anthropic API (if using Claude)
ANTHROPIC_API_KEY=your_anthropic_api_key
```

## Getting Your PythonAnywhere API Token

1. Log in to your PythonAnywhere account
2. Go to your Account page
3. Click on the "API Token" tab
4. Generate or copy your token

## Key Changes Made to the Deployment Script

The script has been updated to work with your Flask Slack bot project:

### Path Structure
- **Before**: Expected Django project with `backend` subdirectory
- **After**: Deploys from current directory to `slack_bot` directory on PythonAnywhere

### Database Migrations
- **Before**: Used Django's `manage.py migrate`
- **After**: Uses Flask-Migrate with `flask db migrate` and `flask db upgrade`

### Static Files
- **Before**: Ran Django's `collectstatic`
- **After**: Skipped (Flask doesn't require collectstatic)

### File Exclusions
- Added exclusions for: `*.log`, `*.db`, `.venv`, `.DS_Store`
- Maintains existing exclusions for tests, cache files, etc.

## Deployment Steps

1. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

2. **Test the Deployment Script** (optional):
   ```bash
   python deploy_to_pythonanywhere.py --test
   ```

3. **Run Full Deployment**:
   ```bash
   python deploy_to_pythonanywhere.py
   ```

## What the Script Does

1. **Validates Environment**: Checks all required variables are set
2. **Tests API Connection**: Verifies your token and credentials
3. **Uploads Files**: Deploys your code to `/home/{username}/slack_bot/`
4. **Creates Virtual Environment**: Sets up Python environment on PythonAnywhere
5. **Installs Dependencies**: Runs `pip install -r requirements.txt`
6. **Runs Migrations**: Initializes and applies Flask database migrations
7. **Reloads Webapp**: Restarts your web application

## File Structure on PythonAnywhere

Your files will be deployed to:
```
/home/{your_username}/slack_bot/
├── server.py
├── models.py
├── config.py
├── requirements.txt
├── services/
├── views/
├── migrations/
└── venv/
```

## Database Configuration

The script supports both:
- **Development**: SQLite database (local)
- **Production**: MySQL database (PythonAnywhere)

Your `config.py` automatically selects the appropriate database based on environment variables.

## Troubleshooting

### Common Issues

1. **API Token Issues**:
   - Ensure token is correct and not expired
   - Check you're using the right host (www vs eu)
   - Verify token format (should not include "Token " prefix)

2. **Migration Errors**:
   - Migrations folder might not exist initially (script handles this)
   - Database permissions issues (check MySQL credentials)

3. **File Upload Issues**:
   - Check file size limits
   - Verify path permissions
   - Review excluded files list

### Debug Mode

Run with `--test` flag to validate exclusion patterns:
```bash
python deploy_to_pythonanywhere.py --test
```

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- Rotate your API tokens regularly
- Use strong passwords for database credentials
- Consider using environment variables instead of `.env` in production 