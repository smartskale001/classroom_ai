import base64

import httpx

from app.core.config import Settings


async def generate_illustration_png_b64(settings: Settings, *, prompt: str, style_suffix: str) -> tuple[str, str]:
    """Use local AUTOMATIC1111 / SD WebUI txt2img endpoint (free, open-source, local GPU)."""
    url = settings.sd_webui_url.rstrip("/") + "/sdapi/v1/txt2img"
    payload = {
        "prompt": f"{prompt}. Style: {style_suffix}",
        "negative_prompt": "low quality, blurry, watermark, text overlay",
        "steps": 28,
        "cfg_scale": 7,
        "width": 1024,
        "height": 1024,
        "sampler_name": "DPM++ 2M Karras",
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        raise ValueError(
            "Open-source image stack requires a local SD WebUI server at "
            f"{settings.sd_webui_url}. Start AUTOMATIC1111 and try again. ({e!s})"
        ) from e

    images = data.get("images") or []
    if not images:
        raise RuntimeError("SD WebUI returned no images.")

    raw = images[0]
    # Some servers may include a data URL; normalize to base64 payload only.
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    # Validate base64 shape
    base64.b64decode(raw, validate=False)
    return raw, "image/png"
