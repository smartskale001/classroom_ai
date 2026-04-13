from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.illustration import IllustrationRequest, IllustrationResponse
from app.services import illustration_openai, illustration_opensource

router = APIRouter()


@router.post("", response_model=IllustrationResponse)
async def create_illustration(body: IllustrationRequest) -> IllustrationResponse:
    settings = get_settings()
    stack = (body.stack or "openai").lower().strip()
    try:
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
