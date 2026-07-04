"""
Pydantic schemas for the Meeting Intelligence API.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Language(str, Enum):
    english = "english"
    hinglish = "hinglish"


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SubmitResponse(BaseModel):
    job_id: str
    status: JobStatus


class StatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    error: str | None = None


class MeetingResult(BaseModel):
    meeting_id: str
    title: str
    transcript: str
    summary: str
    action_items: str
    key_decisions: str
    open_questions: str
    language: str
    warnings: list[str] = Field(default_factory=list)


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    error: str | None = None
    result: MeetingResult | None = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    job_id: str
    question: str
    answer: str
