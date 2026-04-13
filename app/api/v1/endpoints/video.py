from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core.config import get_settings
from app.schemas.video import VideoErrorPublic, VideoJobCreateRequest, VideoJobPublic
from app.services import video_openai, video_opensource

router = APIRouter()


def _to_public(v) -> VideoJobPublic:
    err = getattr(v, "error", None)
    error_public = None
    if err is not None:
        if isinstance(err, dict):
            error_public = VideoErrorPublic(code=err.get("code"), message=err.get("message"))
        else:
            error_public = VideoErrorPublic(
                code=getattr(err, "code", None),
                message=getattr(err, "message", None),
            )
    return VideoJobPublic(
        id=v.id,
        status=v.status,
        progress=getattr(v, "progress", None),
        model=getattr(v, "model", None),
        seconds=str(v.seconds) if getattr(v, "seconds", None) is not None else None,
        size=str(v.size) if getattr(v, "size", None) is not None else None,
        error=error_public,
    )


@router.post("/jobs", response_model=VideoJobPublic)
async def create_job(body: VideoJobCreateRequest) -> VideoJobPublic:
    settings = get_settings()
    stack = (body.stack or "openai").lower().strip()
    try:
        if stack == "opensource":
            target = body.chain_target_seconds if body.chain_target_seconds else int(body.seconds)
            preset = body.opensource_animation or "classic"
            v = await video_opensource.create_job(
                body.prompt.strip(), target, animation_preset=preset
            )
        elif body.chain_target_seconds is not None and body.chain_target_seconds >= 18:
            v = await video_openai.create_chained_video_job(
                settings,
                prompt=body.prompt.strip(),
                model=body.model,
                size=body.size,
                input_reference_image_url=body.input_reference_image_url,
                chain_target_seconds=body.chain_target_seconds,
            )
        else:
            v = await video_openai.create_video_job(
                settings,
                prompt=body.prompt.strip(),
                model=body.model,
                seconds=body.seconds,
                size=body.size,
                input_reference_image_url=body.input_reference_image_url,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Video API error: {e!s}") from e
    return _to_public(v)


@router.get("/jobs/{video_id}", response_model=VideoJobPublic)
async def get_job(video_id: str) -> VideoJobPublic:
    settings = get_settings()
    try:
        if video_id.startswith("osvid_"):
            v = await video_opensource.get_job(video_id)
        else:
            v = await video_openai.retrieve_video(settings, video_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Video API error: {e!s}") from e
    return _to_public(v)


@router.get("/jobs/{video_id}/file")
async def download_job_file(video_id: str):
    settings = get_settings()
    try:
        if video_id.startswith("osvid_"):
            data = await video_opensource.get_video_bytes(video_id)
            return Response(content=data, media_type="video/mp4")

        v = await video_openai.retrieve_video(settings, video_id)
        if v.status != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"Video not ready (status={v.status}). Poll GET /jobs/{video_id} first.",
            )
        data = await video_openai.download_video_bytes(settings, video_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e

    return Response(content=data, media_type="video/mp4")
