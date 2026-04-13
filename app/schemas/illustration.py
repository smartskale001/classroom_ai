from pydantic import BaseModel, Field


class IllustrationRequest(BaseModel):
    prompt: str = Field(..., min_length=4, max_length=3900)
    stack: str = Field(default="openai", description="openai | opensource")
    style: str = Field(
        default="clean educational textbook illustration, simple flat colors, no text in image",
        description="Appended to the model prompt for safety and look.",
    )


class IllustrationResponse(BaseModel):
    image_base64: str
    mime_type: str = "image/png"
