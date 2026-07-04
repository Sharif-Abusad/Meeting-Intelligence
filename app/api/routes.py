"""
Meeting Intelligence API routes.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi import status as http_status

from app.core.config import settings
from app.core.exceptions import MeetingIntelligenceError
from app.services.rag_engine import (
    ask_question, 
    load_rag_chain
)
from app.api.job_store import job_store
from app.api.schemas import (
    AskRequest,
    AskResponse,
    JobResponse,
    JobStatus,
    Language,
    MeetingResult,
    StatusResponse,
    SubmitResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/meetings", tags=["meetings"])

_UPLOAD_DIR = settings.download_dir / "_api_uploads"

_ALLOWED_AUDIO_SUFFIXES = {
    ".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm", ".ogg", ".flac", ".aac",
}
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


@router.post("", response_model=SubmitResponse, status_code=http_status.HTTP_202_ACCEPTED)
async def submit_meeting(
    youtube_url: str | None = Form(default=None),
    language: Language = Form(default=Language.english),
    chunk_minutes: int | None = Form(default=None),
    build_index: bool = Form(default=True),
    file: UploadFile | None = File(default=None),
) -> SubmitResponse:
    """
    Submit a meeting for processing - either a YouTube URL or an
    uploaded audio/video file. Returns immediately with a `job_id`;
    poll `GET /api/meetings/{job_id}` for progress and the result.
    """
    if not youtube_url and not file:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Provide either 'youtube_url' or an uploaded 'file'.",
        )

    if youtube_url and file:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Provide only one of 'youtube_url' or 'file', not both.",
        )

    if youtube_url:
        source = youtube_url
    else:
        source = str(await _save_upload(file))

    job = job_store.submit(
        source=source,
        language=language.value,
        chunk_minutes=chunk_minutes,
        build_index=build_index,
    )
    return SubmitResponse(job_id=job.job_id, status=job.status)


@router.get("/{job_id}/status", response_model=StatusResponse)
async def get_status(job_id: str) -> StatusResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return StatusResponse(job_id=job.job_id, status=job.status, error=job.error)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    result = MeetingResult(**job.result.to_dict()) if job.result else None
    return JobResponse(job_id=job.job_id, status=job.status, error=job.error, result=result)


@router.post("/{job_id}/ask", response_model=AskResponse)
async def ask(job_id: str, body: AskRequest) -> AskResponse:
    """
    Ask a follow-up question against a completed meeting's transcript.
    Requires the job to have finished with `build_index=True`.
    """
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    if job.status != JobStatus.completed or job.result is None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' is not completed yet (status: {job.status}).",
        )

    try:
        chain = load_rag_chain(meeting_id=job.result.meeting_id)
        answer = ask_question(chain, body.question)
    except MeetingIntelligenceError as exc:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return AskResponse(job_id=job_id, question=body.question, answer=answer)


async def _save_upload(file: UploadFile) -> Path:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_AUDIO_SUFFIXES:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(_ALLOWED_AUDIO_SUFFIXES)}",
        )

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = _UPLOAD_DIR / f"{uuid.uuid4().hex[:12]}{suffix}"

    size = 0
    try:
        with open(destination, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File exceeds the 500 MB upload limit.",
                    )
                out_file.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {exc}") from exc
    finally:
        await file.close()

    return destination
