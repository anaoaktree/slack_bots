# PythonAnywhere Deploy 🚀

A modern Python library and CLI tool for deploying web applications to PythonAnywhere with ease. Supports Flask, Django, FastAPI, and static sites with automatic framework detection and intelligent deployment workflows.

## ✨ Features

- 🔍 **Automatic Framework Detection** - Detects Flask, Django, FastAPI, and static sites
- ⚙️ **Flexible Configuration** - YAML config files, environment variables, or CLI options
- 📁 **Smart File Handling** - Respects .gitignore and excludes unnecessary files
- 🗃️ **Database Migrations** - Framework-specific migration support
- 🔄 **Automatic Reloading** - Reloads webapps after deployment
- 🎨 **Beautiful CLI** - Rich terminal UI with progress indicators
- 🛡️ **Error Handling** - Comprehensive validation and error reporting

## 📦 Installation

```bash
pip install pythonanywhere-deploy
```

## 🚀 Quick Start

### 1. Initialize Configuration

```bash
pa-deploy init
```

This creates a `pythonanywhere.yml` configuration file in your project.

### 2. Configure Your Credentials

Edit the generated configuration file or set environment variables:

```yaml
# pythonanywhere.yml
pythonanywhere:
  api_token: "your_api_token"
  username: "your_username" 
  domain: "your_username.pythonanywhere.com"
```

Or use environment variables:
```bash
export PA_API_TOKEN="your_api_token"
export PA_USERNAME="your_username"
export PA_DOMAIN="your_username.pythonanywhere.com"
```

### 3. Deploy Your Project

```bash
pa-deploy deploy
```

## 🎯 Usage Examples

### CLI Usage

```bash
# Deploy with default configuration
pa-deploy deploy

# Deploy with custom config file
pa-deploy deploy --config my-config.yml

# Deploy with CLI overrides
pa-deploy deploy --username myuser --domain myapp.pythonanywhere.com

# Dry run to see what would be deployed
pa-deploy deploy --dry-run

# Skip migrations and requirements
pa-deploy deploy --no-migrations --no-requirements

# Check configuration and test API
pa-deploy check

# Detect framework in current directory
pa-deploy detect
```

### Python API Usage

```python
from pythonanywhere_deploy import PythonAnywhereDeployer, DeploymentConfig

# Create configuration
config = DeploymentConfig(
    api_token="your_token",
    username="your_username",
    domain="your_app.pythonanywhere.com",
    project_dir="/path/to/project"
)

# Deploy
deployer = PythonAnywhereDeployer(config)
result = deployer.deploy()

if result["success"]:
    print("🎉 Deployment successful!")
else:
    print("❌ Deployment failed:", result["errors"])
```

## ⚙️ Configuration

### Configuration File (pythonanywhere.yml)

```yaml
pythonanywhere:
  # Required
  api_token: "your_api_token"
  username: "your_username"
  domain: "yourapp.pythonanywhere.com"
  
  # Optional
  host: "www.pythonanywhere.com"  # or "eu.pythonanywhere.com"
  remote_dir: "my_app"            # defaults to project name
  framework: "flask"              # override auto-detection
  requirements_file: "requirements.txt"
  
  # Deployment options
  run_migrations: true
  install_requirements: true
  reload_webapp: true
  
  # Custom exclusions (beyond .gitignore)
  exclude_patterns:
    - "*.tmp"
    - "local_settings.py"
    - "development.db"
```

### Environment Variables

```bash
PA_API_TOKEN=your_api_token
PA_USERNAME=your_username
PA_DOMAIN=yourapp.pythonanywhere.com
PA_HOST=www.pythonanywhere.com
```

### Configuration Priority

1. CLI options (highest priority)
2. YAML configuration file
3. Environment variables (lowest priority)

## 🔧 Framework Support

### Flask
- ✅ Auto-detection via imports and Flask-specific files
- ✅ Flask-Migrate database migrations
- ✅ Virtual environment setup

### Django
- ✅ Auto-detection via `manage.py` and settings
- ✅ `makemigrations` and `migrate` commands
- ✅ `collectstatic` for static files

### FastAPI
- ✅ Auto-detection via imports
- ✅ Alembic migrations (if present)
- ✅ Virtual environment setup

### Static Sites
- ✅ Auto-detection via HTML files
- ✅ Direct file deployment
- ✅ No backend processing required

### Generic Python
- ✅ Fallback for any Python project
- ✅ Basic file deployment
- ✅ Requirements installation

## 📁 File Handling

The library intelligently handles file exclusions:

### Default Exclusions
- `.git`, `.github/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`
- `venv/`, `.venv/`, `env/`
- `node_modules/`
- `*.log`, `*.db` (local databases)
- `*.md` (documentation)
- `**/tests/*`, `**/test_*.py`

### Custom Exclusions
- Respects `.gitignore` patterns
- Additional patterns via configuration
- Override exclusions with configuration

## 🛠️ Advanced Usage

### Custom Framework Handler

```python
from pythonanywhere_deploy.frameworks import FrameworkHandler

class MyFrameworkHandler(FrameworkHandler):
    @property
    def name(self):
        return "myframework"
    
    def detect(self, project_dir):
        return (project_dir / "myframework.py").exists()
    
    def get_migration_commands(self, console_id, config):
        return ["my-migrate-command"]
    
    def get_post_deployment_commands(self, console_id, config):
        return ["my-post-deploy-command"]

# Register your handler
from pythonanywhere_deploy.frameworks import FRAMEWORK_HANDLERS
FRAMEWORK_HANDLERS.insert(0, MyFrameworkHandler())
```

### Programmatic Deployment

```python
from pathlib import Path
from pythonanywhere_deploy import load_config, PythonAnywhereDeployer

# Load config with overrides
config = load_config(
    config_file=Path("custom-config.yml"),
    username="override_user",
    run_migrations=False
)

# Create and configure deployer
deployer = PythonAnywhereDeployer(config)

# Test connection first
success, message = deployer.test_api_connection()
if not success:
    print(f"Connection failed: {message}")
    exit(1)

# Run deployment
result = deployer.deploy()

# Handle results
for step, info in result["steps"].items():
    status = "✅" if info["success"] else "❌"
    print(f"{status} {step}: {info.get('message', '')}")
```

## 🐛 Troubleshooting

### Common Issues

1. **API Authentication Errors**
   ```bash
   # Check your token
   pa-deploy check
   
   # Verify token format (should not include "Token " prefix)
   export PA_API_TOKEN="abc123def456"  # ✅ Correct
   export PA_API_TOKEN="Token abc123def456"  # ❌ Wrong
   ```

2. **File Upload Issues**
   ```bash
   # Check what files would be uploaded
   pa-deploy deploy --dry-run
   
   # Test with verbose output
   pa-deploy deploy --verbose
   ```

3. **Migration Failures**
   ```bash
   # Skip migrations if problematic
   pa-deploy deploy --no-migrations
   
   # Check framework detection
   pa-deploy detect
   ```

### Debug Mode

```bash
# Verbose output
pa-deploy deploy --verbose

# Dry run to test
pa-deploy deploy --dry-run

# Check configuration
pa-deploy check
```

## 🔍 Log Debugging Tools

This project includes comprehensive debugging tools to help troubleshoot your deployed Flask app on PythonAnywhere.

### Quick Start

```bash
cd scripts
python debug.py  # Interactive menu launcher
```

### Available Tools

- **`get_latest_logs.py`** - Download current logs with analysis
- **`get_logs_by_date.py`** - Get historical logs by date
- **`troubleshoot.py`** - Interactive problem-solving guide
- **`log_utils.py`** - Core utilities for log management

### Common Debugging Commands

```bash
# Quick health check
python get_latest_logs.py

# Emergency debugging (when app is down)
python troubleshoot.py  # Choose option 8

# Check specific log types
python get_latest_logs.py error
python get_latest_logs.py access

# Historical investigation
python get_logs_by_date.py yesterday
python get_logs_by_date.py 7  # 7 days ago
```

### What You Get

- 📊 **HTTP status code analysis** (2xx success, 5xx errors)
- ⚠️ **Error detection and counting** from application logs
- 📁 **Automatic local file saving** with timestamps
- 🔍 **Smart pattern recognition** for common issues
- 📈 **Interactive troubleshooting guides** for different scenarios

See `scripts/README.md` for detailed usage instructions.

## 🤝 Contributing

Contributions are welcome! Please feel free to:

1. Report bugs and request features via GitHub Issues
2. Submit pull requests for improvements
3. Add support for new frameworks
4. Improve documentation

### Development Setup

```bash
git clone https://github.com/yourusername/pythonanywhere-deploy
cd pythonanywhere-deploy
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest
```

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built using the [PythonAnywhere API](https://help.pythonanywhere.com/pages/API/)
- CLI powered by [Click](https://click.palletsprojects.com/) and [Rich](https://rich.readthedocs.io/)
- Framework detection inspired by various deployment tools

---

**Made with ❤️ for the Python community**