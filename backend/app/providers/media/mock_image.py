from __future__ import annotations

from app.media.draw import placeholder_card
from app.providers.faults import faults
from app.providers.media.base import MediaResult
from app.schemas.media import ProviderMode


class MockImageProvider:
    """Deterministic, offline image generator. Produces a REAL PNG file that is
    clearly watermarked MOCK — never reported as a production generation."""

    name = "mock-image"
    mode = ProviderMode.MOCK

    def generate_image(self, *, prompt: str, negative_prompt: str, width: int, height: int,
                       out_path: str, seed: int | None = None) -> MediaResult:
        faults.maybe_raise("image", "media")
        subject = (prompt.split(",")[0] if prompt else "scene").strip()[:80]
        img = placeholder_card(
            width, height, title=subject or "scene",
            subtitle=prompt[:120], seed=f"{prompt}:{seed}", watermark="MOCK IMAGE",
        )
        img.save(out_path, "PNG")
        return MediaResult(
            path=out_path, mime_type="image/png", provider=self.name,
            provider_mode=self.mode, width=width, height=height, cost=0.0,
            meta={"prompt": prompt, "negative_prompt": negative_prompt},
        )
