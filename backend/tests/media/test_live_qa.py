from app.media import media_qa


def test_live_video_without_audio_fails(_base_settings, monkeypatch, tmp_path):
    _base_settings.mock_mode = False
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 2048)
    monkeypatch.setattr(media_qa, "probe", lambda _: {
        "duration": 6, "width": 1080, "height": 1920, "fps": 30,
        "has_video": True, "has_audio": False})
    monkeypatch.setattr(media_qa, "detect_black", lambda _: [])
    monkeypatch.setattr(media_qa, "detect_silence", lambda _: [])
    result = media_qa.check_render(str(video), expect_duration=6, expect_w=1080,
                                   expect_h=1920, expect_fps=30, scene_count=1,
                                   subtitle_coverage=1)
    assert not result.passed
