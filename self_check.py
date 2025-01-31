#!/usr/bin/python3 -u


import sys
import json
from src.tools.self_check.diagnostic import Diagnostic

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 self_check.py <test_name> [config_file]")
        sys.exit(1)

    test_name = sys.argv[1]
    config_file = sys.argv[2] if len(sys.argv) > 2 else "config.json"  # Default file

    # Initialize diagnostic class with the config file
    diag = Diagnostic(config_file)

    # Run the selected test
    if test_name == "all":
        result = diag.run_all()
    elif hasattr(diag, test_name):  # Check if method exists
        method = getattr(diag, test_name)
        result = method() if callable(method) else None
    else:
        print(f"Error: Test '{test_name}' not found.")
        sys.exit(1)

    # Print JSON result so it can be captured remotely
    print(json.dumps(result, indent=4))

if __name__ == "__main__":
    main()
