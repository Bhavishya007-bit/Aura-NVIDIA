import io

import av

from .audio import ingest_audio
from typing import cast

import av
from av.audio.frame import AudioFrame
from av.container.input import InputContainer

def ingest_video(
    data: bytes,
    filename: str,
) -> tuple[list[dict], list[str]]:
    """
    Extract audio from a video and transcribe it using
    the existing audio ingestion pipeline.
    """
    warnings: list[str] = []

    if not data:
        return [], ["Video file is empty."]

    try:
        # Open the video directly from memory.
        container = cast(
            InputContainer,
            av.open(io.BytesIO(data)),
)
        audio_streams = [
            stream
            for stream in container.streams
            if stream.type == "audio"
        ]

        if not audio_streams:
            container.close()
            return [], ["The video contains no audio stream."]

        audio_stream = audio_streams[0]
        audio_chunks = []

        # Decode audio frames and convert them to WAV.
        resampler = av.AudioResampler(
            format="s16",
            layout="mono",
            rate=16000,
        )

        output_buffer = io.BytesIO()
        output_container = av.open(
            output_buffer,
            mode="w",
            format="wav",
        )
        output_stream = output_container.add_stream(
            "pcm_s16le",
            rate=16000,
        )

        for frame in container.decode(audio_stream):
            audio_frame = cast(AudioFrame, frame)

            for resampled_frame in resampler.resample(audio_frame):
                for packet in output_stream.encode(resampled_frame):
                    output_container.mux(packet)

        # Flush the resampler.
        for resampled_frame in resampler.resample(None):
            for packet in output_stream.encode(resampled_frame):
                output_container.mux(packet)

        for packet in output_stream.encode(None):
            output_container.mux(packet)

        output_container.close()
        container.close()

        wav_data = output_buffer.getvalue()
        output_buffer.close()

        if not wav_data:
            return [], ["Could not extract audio from the video."]

        # Reuse the existing Whisper transcription pipeline.
        content_units, transcription_warnings = ingest_audio(
            data=wav_data,
            filename=filename,
        )

        warnings.extend(transcription_warnings)

        # Mark these units as originating from video.
        for unit in content_units:
            unit["source"]["file_type"] = "mp4"
            unit["source_location"]["kind"] = "video_segment"

        return content_units, warnings

    except Exception as error:
        return [], [f"Video processing failed: {error}"]
