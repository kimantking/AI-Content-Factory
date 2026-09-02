from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.schemas.media import ProviderMode


class MediaResult(BaseModel):
    path: str
    mime_type: str
    provider: str
    provider_mode: ProviderMode
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    cost: float = 0.0
    meta: dict = {}


class StockItem(BaseModel):
    path: str
    title: str
    provider: str
    provider_mode: ProviderMode
    semantic_relevance_score: float = 0.0
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    cost: float = 0.0


@runtime_checkable
class ImageProvider(Protocol):
    name: str
    mode: ProviderMode

    def generate_image(self, *, prompt: str, negative_prompt: str, width: int, height: int,
                       out_path: str, seed: int | None = None) -> MediaResult: ...


@runtime_checkable
class VideoProvider(Protocol):
    name: str
    mode: ProviderMode

    def generate_video(self, *, prompt: str, reference_image: str | None, duration: float,
                       width: int, height: int, camera_motion: str, out_path: str) -> MediaResult: ...


@runtime_checkable
class TTSProvider(Protocol):
    name: str
    mode: ProviderMode

    def synthesize(self, *, text: str, voice_id: str, language: str, speed: float,
                   emotion: str, style: str, out_path: str) -> MediaResult: ...


@runtime_checkable
class StockProvider(Protocol):
    name: str
    mode: ProviderMode

    def search(self, *, query: str, width: int, height: int, want_video: bool,
               out_path: str) -> StockItem: ...


@runtime_checkable
class MusicProvider(Protocol):
    name: str
    mode: ProviderMode

    def get_track(self, *, mood: str, duration: float, out_path: str) -> MediaResult: ...


@runtime_checkable
class StorageProvider(Protocol):
    def path_for(self, *parts: str) -> str: ...
    def campaign_dir(self, campaign_id: str, *parts: str) -> str: ...
    def output_dir(self, campaign_id: str, *parts: str) -> str: ...
