"""Reel quality measurements on real ffmpeg files: voice-to-video sync lag, black frames, loudness, section frames."""

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from socialauto.reel.checklist import frame_problem
from socialauto.video import ffmpeg, quality

pytestmark = pytest.mark.render
VOICE = Path(__file__).resolve().parent / "fixtures" / "sample_voice_short.wav"


def run(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)], check=True)


def test_sync_lag_measures_a_shift(tmp_path):
    late = tmp_path / "late.wav"
    run("-i", VOICE, "-af", "adelay=500:all=1", late)
    assert abs(quality.sync_lag(quality.decode_mono(VOICE), quality.decode_mono(VOICE))) <= 0.02
    assert quality.sync_lag(quality.decode_mono(VOICE), quality.decode_mono(late)) == pytest.approx(0.5, abs=0.05)


def test_black_frames_and_loudness(tmp_path):
    black = tmp_path / "black.mp4"
    run("-f", "lavfi", "-i", "color=c=black:s=320x568:d=2", "-i", VOICE, "-shortest", "-c:v", "libx264", "-c:a", "aac", black)
    assert ffmpeg.black_segments(black)
    quiet = tmp_path / "quiet.wav"
    run("-i", VOICE, "-af", "volume=-30dB", quiet)
    assert ffmpeg.loudness(quiet)["lufs"] < -35


def test_section_frame_check(tmp_path):
    good, black, flat = tmp_path / "g.jpg", tmp_path / "b.jpg", tmp_path / "f.jpg"
    img = Image.effect_noise((270, 480), 80).convert("RGB")
    img.save(good)
    Image.new("RGB", (270, 480), (0, 0, 0)).save(black)
    Image.new("RGB", (270, 480), (120, 120, 120)).save(flat)
    assert frame_problem(good) is None and frame_problem(black) == "qora kadr" and "bo'sh" in frame_problem(flat)
