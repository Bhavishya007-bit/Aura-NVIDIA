"""Authenticated original-file navigation for source citations."""
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import FileResponse, Response

from backend.auth_db import get_auth_connection
from backend.auth_routes import get_current_student
from backend.ingestion.ppt_convert import _find_soffice, PptConversionError
from backend.image_processing import image_png

router = APIRouter(prefix="/study/sources", tags=["Source viewer"])
PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_ROOT = PROJECT_ROOT / "backend" / "uploads"
CACHE_ROOT = PROJECT_ROOT / "backend" / ".local_storage" / "source_previews"
conversion_lock = threading.Lock()
MAX_BYTES = 100 * 1024 * 1024
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def owned_original(source_id: int, student_id: int) -> dict:
    connection = get_auth_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT s.source_name,s.source_type,s.file_path FROM sources s
                JOIN courses c ON c.course_id=s.course_id WHERE s.source_id=%s
                AND s.owner_student_id=%s AND c.owner_student_id=%s""",
                (source_id, student_id, student_id),
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(404, "Source not found.")
    if not row[2]:
        raise HTTPException(404, "The original file is unavailable. The extracted excerpt is still available.")
    path = Path(row[2])
    path = (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    if not path.is_relative_to(UPLOAD_ROOT.resolve()) or not path.is_file():
        raise HTTPException(404, "The original uploaded file is unavailable on this backend.")
    if path.stat().st_size > MAX_BYTES:
        raise HTTPException(413, "The original file exceeds the viewer's 100 MiB limit.")
    return {"id": source_id, "student_id": student_id, "title": row[0], "path": path}


def source_kind(source: dict) -> str:
    suffix = source["path"].suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png"}:
        return "image"
    if suffix == ".pdf":
        return "pdf_page"
    if suffix in {".ppt", ".pptx"}:
        return "slide"
    if suffix == ".mp4":
        return "video_timestamp"
    if suffix in AUDIO_SUFFIXES:
        return "audio_timestamp"
    return "download"


def presentation_pdf(source: dict) -> Path:
    data = source["path"].read_bytes()
    key = hashlib.sha256(data).hexdigest()
    folder = CACHE_ROOT / str(source["student_id"]) / str(source["id"]) / key
    destination = folder / "slides.pdf"
    with conversion_lock:
        if destination.is_file():
            return destination
        try:
            executable = _find_soffice()
        except PptConversionError as error:
            raise HTTPException(503, "Install LibreOffice on the backend to open PPT/PPTX slide previews.") from error
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="slides-", dir=CACHE_ROOT) as directory:
            temporary = Path(directory)
            original = temporary / ("slides" + source["path"].suffix.lower())
            original.write_bytes(data)
            output = temporary / "converted"
            output.mkdir()
            # Include hidden slides: omitting them would shift citation numbering.
            export = 'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'
            command = [executable, f'-env:UserInstallation={(temporary / "profile").as_uri()}',
                       "--headless", "--nologo", "--nodefault", "--norestore",
                       "--convert-to", export, "--outdir", str(output), str(original)]
            try:
                result = subprocess.run(command, capture_output=True, timeout=120, shell=False, check=False)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise HTTPException(503, "Slide preview conversion failed or timed out. Your original and excerpt are preserved.") from error
            converted = output / "slides.pdf"
            if result.returncode != 0 or not converted.is_file() or converted.stat().st_size > MAX_BYTES:
                raise HTTPException(422, "This presentation could not be rendered. It may be damaged or protected.")
            folder.mkdir(parents=True, exist_ok=True)
            staged = folder / (uuid4().hex + ".partial")
            shutil.copyfile(converted, staged)
            os.replace(staged, destination)
    return destination


def run_pdf(mode: str, filename: Path, position: int = 1) -> bytes:
    command = [sys.executable, "-m", "backend.source_render", mode, str(filename), str(position)]
    try:
        result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, timeout=45, shell=False, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HTTPException(503, "The source preview could not be rendered. Please retry.") from error
    if result.returncode:
        try:
            code = json.loads(result.stderr).get("error")
        except (ValueError, TypeError):
            code = None
        if code == "out_of_range":
            raise HTTPException(404, "The cited page or slide is outside this source.")
        raise HTTPException(422, "The source cannot be rendered. It may be protected or damaged.")
    return result.stdout


def pdf_for(source: dict) -> Path:
    kind = source_kind(source)
    if kind == "pdf_page":
        return source["path"]
    if kind == "slide":
        return presentation_pdf(source)
    raise HTTPException(422, "This material has no page or slide preview.")


@router.get("/{source_id}/viewer")
def viewer_info(source_id: int, student=Depends(get_current_student)) -> dict:
    source = owned_original(source_id, student["student_id"])
    kind = source_kind(source)
    count = None
    if kind == "image":
        count = 1
    if kind in {"pdf_page", "slide"}:
        count = json.loads(run_pdf("info", pdf_for(source)))["page_count"]
    return {"source_id": source_id, "title": source["title"], "kind": kind, "page_count": count}


@router.get("/{source_id}/preview")
def preview(source_id: int, position: int = Query(default=1, ge=1), student=Depends(get_current_student)):
    source = owned_original(source_id, student["student_id"])
    if source_kind(source) == "image":
        if position != 1: raise HTTPException(404, "This material contains one original image.")
        try: data = image_png(source["path"].read_bytes())
        except ValueError as error: raise HTTPException(422,str(error)) from error
        return Response(data,media_type="image/png",headers={"Cache-Control":"no-store"})
    return Response(run_pdf("png", pdf_for(source), position), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/{source_id}/media")
def media(source_id: int, student=Depends(get_current_student)):
    source = owned_original(source_id, student["student_id"])
    if source_kind(source) not in {"video_timestamp", "audio_timestamp"}:
        raise HTTPException(422, "This source is not an audio or video file.")
    return FileResponse(source["path"], media_type=mimetypes.guess_type(str(source["path"]))[0] or "application/octet-stream",
                        content_disposition_type="inline", headers={"Cache-Control": "no-store"})


@router.get("/{source_id}/original")
def original(source_id: int, student=Depends(get_current_student)):
    source = owned_original(source_id, student["student_id"])
    name = Path(str(source["title"]).replace("\\", "/")).name
    return FileResponse(source["path"], filename=name, headers={"Cache-Control": "no-store"})
