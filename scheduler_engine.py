"""
Compatibility shim for the legacy Streamlit prototype (COURSE_SCHEDULER.py).
The planning engine now lives in backend/engine.py and is shared with the
FastAPI web application.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from engine import *  # noqa: E402,F401,F403
