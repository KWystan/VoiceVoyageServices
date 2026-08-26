import os
import sys

# Find repo root and execute run_services.py
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)

from run_services import main

if __name__ == "__main__":
    main()
