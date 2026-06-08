import asyncio
import base64
import logging

import httpx
from openai import APITimeoutError, APIConnectionError, AsyncOpenAI, AuthenticationError, BadRequestError, RateLimitError

from app.core.config import Settings

logger = logging.getLogger(__name__)


async def generate_illustration_png_b64(
    settings: Settings,
    *,
    prompt: str,
    style_suffix: str,
) -> tuple[str, str]:
    """Generate an illustration with the configured OpenAI image model and return base64 PNG data.

    The image model is read from `settings.image_generation_model` (defaults to "gpt-image-2").
    """
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        raise ValueError(
            "OPENAI_API_KEY is missing. Add it to .env file to use OpenAI for image generation."
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key.strip())
    model = settings.image_generation_model
    full_prompt = f"{prompt.strip()}\n\nStyle: {style_suffix.strip()}"
    full_prompt = full_prompt[:4000]

    last_error: Exception | None = None
    for attempt in range(1, settings.image_generation_retries + 1):
        try:
            logger.info(
                f"Image generation attempt {attempt}/{settings.image_generation_retries} using model={model}"
            )
            result = await client.images.generate(
                model=model,
                prompt=full_prompt,
                size="1024x1024",
                quality=settings.image_generation_quality,
                n=1,
            )
            if not result.data:
                raise RuntimeError(f"Model {model} returned no image data.")

            item = result.data[0]
            if getattr(item, "b64_json", None):
                logger.info(f"{model} succeeded on attempt {attempt}")
                return item.b64_json, "image/png"

            if getattr(item, "url", None):
                async with httpx.AsyncClient(timeout=60.0) as client_http:
                    image_res = await client_http.get(item.url)
                    image_res.raise_for_status()
                encoded = base64.b64encode(image_res.content).decode("ascii")
                logger.info(f"{model} succeeded on attempt {attempt} via URL response")
                return encoded, "image/png"

            raise RuntimeError(f"{model} returned no usable image payload.")
        except AuthenticationError as e:
            last_error = e
            logger.error(f"{model} authentication failed: {e!s}")
            raise RuntimeError("OpenAI authentication failed. Check OPENAI_API_KEY.") from e
        except RateLimitError as e:
            last_error = e
            logger.warning(f"{model} rate limited: {e!s}")
            raise RuntimeError("OpenAI rate limit/quota reached. Check billing or try again later.") from e
        except APITimeoutError as e:
            last_error = e
            logger.warning(f"{model} timed out: {e!s}")
            if attempt < settings.image_generation_retries:
                delay = settings.image_generation_retry_delay * (2 ** (attempt - 1))
                logger.info(f"Waiting {delay:.1f}s before retry...")
                await asyncio.sleep(delay)
            else:
                raise RuntimeError("OpenAI request timed out.") from e
        except APIConnectionError as e:
            last_error = e
            logger.error(f"{model} connection failed: {e!s}")
            raise RuntimeError(
                "OpenAI connection failed. Check network access, proxy/firewall settings, or OpenAI service availability."
            ) from e
        except BadRequestError as e:
            last_error = e
            logger.error(f"{model} bad request: {e!s}")
            raise RuntimeError(f"OpenAI rejected the image request: {e!s}") from e
        except Exception as e:
            last_error = e
            logger.warning(f"{model} attempt {attempt} failed: {e!s}")
            if attempt < settings.image_generation_retries:
                delay = settings.image_generation_retry_delay * (2 ** (attempt - 1))
                logger.info(f"Waiting {delay:.1f}s before retry...")
                await asyncio.sleep(delay)

    error_msg = f"Image generation failed after {settings.image_generation_retries} attempts: {last_error!s}"
    logger.error(error_msg)
    raise RuntimeError(error_msg) from last_error
