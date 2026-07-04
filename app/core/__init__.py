"""
Meeting Intelligence - core package.

Typical usage:

    from core.pipeline import run_pipeline

    result = run_pipeline("meeting.mp4", language="english")
    print(result.summary)
"""

from app.core.pipeline import MeetingAnalysis, run_pipeline

__all__ = ["MeetingAnalysis", "run_pipeline"]
