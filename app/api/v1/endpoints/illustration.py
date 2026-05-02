import base64

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.illustration import IllustrationRequest, IllustrationResponse
from app.services import illustration_openai, illustration_opensource
from app.services.pexels_stock import fetch_landscape_photo_bytes

router = APIRouter()


@router.post("", response_model=IllustrationResponse)
async def create_illustration(body: IllustrationRequest) -> IllustrationResponse:
    settings = get_settings()
    stack = (body.stack or "openai").lower().strip()
    try:
        if body.source == "pexels":
            key = (settings.pexels_api_key or "").strip()
            if not key:
                raise ValueError("PEXELS_API_KEY is required for Pexels stock photos. Add it to your .env file.")
            out = await fetch_landscape_photo_bytes(key, body.prompt)
            if not out:
                raise ValueError(
                    "No stock photo matched this prompt. Try simpler keywords (e.g. solar system, plant cell)."
                )
            raw, mime, _attr = out
            b64 = base64.b64encode(raw).decode("ascii")
            return IllustrationResponse(image_base64=b64, mime_type=mime)
        if stack == "opensource":
            b64, mime = await illustration_opensource.generate_illustration_png_b64(
                settings,
                prompt=body.prompt,
                style_suffix=body.style,
            )
        else:
            b64, mime = await illustration_openai.generate_illustration_png_b64(
                settings,
                prompt=body.prompt,
                style_suffix=body.style,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Image generation failed: {e!s}") from e
    return IllustrationResponse(image_base64=b64, mime_type=mime)
