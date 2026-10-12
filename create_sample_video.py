
import asyncio
from pathlib import Path

import edge_tts
from moviepy import AudioFileClip, ColorClip

OUTPUT_DIR = Path("test_assets")
OUTPUT_DIR.mkdir(exist_ok=True)

AUDIO_PATH = OUTPUT_DIR / "sample.mp3"
VIDEO_PATH = OUTPUT_DIR / "sample.mp4"

TEXT = (
    "Hello, welcome to Aura. "
    "This is a test video for audio transcription. "
    "The system should extract this speech and generate timestamps."
)


async def generate_audio():
    communicate = edge_tts.Communicate(
        TEXT,
        voice="en-US-AriaNeural",
    )
    await communicate.save(str(AUDIO_PATH))


def main():
    asyncio.run(generate_audio())

    audio = AudioFileClip(str(AUDIO_PATH))
    video = ColorClip(
        size=(640, 360),
        color=(30, 50, 80),
        duration=audio.duration,
    )
    video = video.with_audio(audio)

    video.write_videofile(
        str(VIDEO_PATH),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

    video.close()
    audio.close()

    print(f"Sample video created: {VIDEO_PATH}")


if __name__ == "__main__":
    main()
