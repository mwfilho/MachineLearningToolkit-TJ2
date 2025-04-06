import os
import sys
import json
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import app from app.py
try:
    from app import app
    HAS_APP = True
    logger.info("Successfully imported Flask app from app.py")
except ImportError as e:
    HAS_APP = False
    logger.error(f"Failed to import Flask app: {str(e)}")
    # This will help debugging when dependencies are missing

def get_system_info():
    """Get basic system information"""
    return {
        "python_version": sys.version,
        "python_path": sys.executable,
        "current_directory": os.getcwd(),
        "timestamp": datetime.now().isoformat(),
        "platform": sys.platform,
        "modules_available": list(sys.modules.keys())[:20],  # First 20 modules
        "environment_variables": dict(os.environ)
    }

def check_modules():
    """Check if important modules are available"""
    modules_to_check = [
        "flask", "pypdf2", "gunicorn", "sqlalchemy",
        "tqdm", "werkzeug", "jinja2", "json"
    ]
    
    results = {}
    for module in modules_to_check:
        try:
            __import__(module)
            results[module] = "Available"
        except ImportError:
            results[module] = "Not available"
    
    return results

if __name__ == '__main__':
    print("PJE Document Merger - System Check")
    print("-" * 50)
    
    # Get system information
    system_info = get_system_info()
    print(f"Python Version: {system_info['python_version']}")
    print(f"Python Path: {system_info['python_path']}")
    print(f"Current Directory: {system_info['current_directory']}")
    print(f"Platform: {system_info['platform']}")
    print(f"Timestamp: {system_info['timestamp']}")
    
    print("\nModule Availability:")
    module_results = check_modules()
    for module, status in module_results.items():
        print(f"  - {module}: {status}")
    
    print("\nPython Path:")
    for path in sys.path:
        print(f"  - {path}")
    
    # Write detailed information to a JSON file for debugging
    with open('system_check.json', 'w') as f:
        json.dump({
            "system_info": system_info,
            "module_check": module_results
        }, f, indent=2, default=str)
    
    print("\nDetailed information has been written to system_check.json")