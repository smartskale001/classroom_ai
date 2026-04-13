from openai import AsyncOpenAI

from app.core.config import Settings


async def generate_illustration_png_b64(
    settings: Settings,
    *,
    prompt: str,
    style_suffix: str,
) -> tuple[str, str]:
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        raise ValueError("OPENAI_API_KEY is required for illustration generation.")
    client = AsyncOpenAI(api_key=settings.openai_api_key.strip())
    full_prompt = f"{prompt.strip()}\n\nStyle: {style_suffix.strip()}"

    result = await client.images.generate(
        model="dall-e-3",
        prompt=full_prompt[:4000],
        size="1024x1024",
        quality="standard",
        n=1,
        response_format="b64_json",
    )
    if not result.data or not result.data[0].b64_json:
        raise RuntimeError("Image API returned no image data.")
    return result.data[0].b64_json, "image/png"
