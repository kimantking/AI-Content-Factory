"""Real FFmpeg, synthetic provider clip: not a paid Google verification."""
from app.agents.media_runner import run_media_pipeline
from app.db.base import session_scope
from app.db.models import Asset
from app.media.ffmpeg import probe, run_ffmpeg
from app.providers.media.base import MediaResult
from app.schemas.media import ProviderMode, VisualType


def test_video_clip_reaches_final_render(ready_campaign, monkeypatch):
    from app.agents import media_nodes as nodes

    original = nodes.plan_visuals
    calls = []

    def plan(*args, **kwargs):
        choices = original(*args, **kwargs)
        choices[0].visual_type = VisualType.AI_VIDEO
        return choices

    class ClipProvider:
        def generate_video(self, **kwargs):
            calls.append(kwargs)
            run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15",
                        "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", kwargs["out_path"]])
            return MediaResult(path=kwargs["out_path"], mime_type="video/mp4",
                               provider="synthetic-test-video", provider_mode=ProviderMode.MOCK)

    monkeypatch.setattr(nodes, "plan_visuals", plan)
    monkeypatch.setattr(nodes, "get_video_provider", lambda: ClipProvider())
    state = run_media_pipeline(ready_campaign, ["youtube_shorts"])
    assert len(calls) == 1
    assert state["scenes"][0]["video_path"]
    info = probe(state["render_path"])
    assert info["has_video"] and info["has_audio"]
    assert info["width"] == 1080 and info["height"] == 1920
    with session_scope() as db:
        assert db.query(Asset).filter_by(campaign_id=ready_campaign, asset_type="video").count() == 1
    # Retry uses the persisted clip, no second provider request.
    nodes.gen_videos_node(state)
    assert len(calls) == 1
