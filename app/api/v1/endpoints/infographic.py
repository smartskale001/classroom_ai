from fastapi import APIRouter, HTTPException

from app.schemas.infographic import InfographicRequest, InfographicResponse
from app.schemas.language import normalize_output_language
from app.services import infographic as infographic_service

router = APIRouter()


@router.post("/generate", response_model=InfographicResponse)
async def generate_infographic(body: InfographicRequest) -> InfographicResponse:
    stack = (body.stack or "openai").lower().strip()
    lang = normalize_output_language(body.output_language)

    try:
        b64, mime, prompt_used = await infographic_service.generate_infographic(
            topic=body.topic.strip(),
            context_text=body.context_text,
            output_language=lang,
            stack=stack,
            style=body.style,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Infographic generation failed: {e!s}") from e

    return InfographicResponse(image_base64=b64, mime_type=mime, image_prompt_used=prompt_used)
