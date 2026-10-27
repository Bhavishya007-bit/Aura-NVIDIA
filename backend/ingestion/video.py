"""Timestamped speech and bounded visual sampling; originals remain unchanged."""
import io
import os
import av
from .audio import ingest_audio
from .image import ingest_image
from .utils import generate_unit_id
from backend.preparation_progress import report, preparation_progress


def ingest_video(data: bytes, filename: str) -> tuple[list[dict], list[str]]:
    if not data:
        return [], ['Video file is empty.']
    units, warnings = [], []
    # PyAV can decode the audio track directly: no second WAV in memory.
    try:
        with av.open(io.BytesIO(data)) as container:
            has_audio = any(s.type == 'audio' for s in container.streams)
            duration = float(container.duration or 0) / av.time_base
        if has_audio:
            speech, speech_warnings = ingest_audio(data, filename)
            for unit in speech:
                unit['source']['file_type'] = 'mp4'
                unit['source_location']['kind'] = 'video_segment'
            units.extend(speech)
            warnings.extend(speech_warnings)
        else:
            warnings.append('No audio track: preparation uses sampled visual frames only.')
    except Exception as error:
        return [], [f'Video decoding failed: {type(error).__name__}. Check that the file is a playable MP4.']
    # Sample across the entire duration, rather than decoding every frame.
    # A maximum of eight model calls bounds CPU and memory use. Explicitly
    # disclose sampling; this does not establish motion between frames.
    try:
        with av.open(io.BytesIO(data)) as container:
            streams = [s for s in container.streams if s.type == 'video']
            if not streams:
                warnings.append('No video stream was found.')
                return units, warnings
            stream = streams[0]
            if duration <= 0 and stream.duration is not None:
                duration = float(stream.duration * stream.time_base)
            # Even a ten-second clip needs a middle/end frame: its first frame
            # may be a black screen or title rather than the subject.
            count = min(8, max(3 if duration > 0 else 1, int(duration // 30) + 1))
            targets = [i * max(0, duration - 0.1) / max(1, count - 1) for i in range(count)]
            seen = set()
            report('reading_video_frames', 0, count)
            for index, target in enumerate(targets):
                container.seek(int(target * av.time_base), backward=True)
                selected = None
                for frame in container.decode(stream):
                    if frame.time is not None and frame.time >= target:
                        selected = frame
                        break
                if selected is None:
                    continue
                seconds = float(selected.time or 0)
                if round(seconds, 2) in seen:
                    continue
                seen.add(round(seconds, 2))
                buffer = io.BytesIO()
                selected.to_image().save(buffer, format='PNG')
                # Nested image OCR/vision must not replace video-wide progress.
                with preparation_progress(None):
                    extracted, frame_warnings = ingest_image(buffer.getvalue(), f'{filename}-frame-{index}.png')
                warnings.extend(f'Frame {seconds:.1f}s: {w}' for w in frame_warnings)
                for unit in extracted:
                    unit['unit_id'] = generate_unit_id(filename, 'video_frame', f'{seconds:.3f}-{unit["extraction_status"]}')
                    unit['source'] = {'filename': filename, 'file_type': 'mp4'}
                    unit['source_location'] = {**unit['source_location'], 'kind': 'video_segment',
                        'start_seconds': seconds, 'end_seconds': seconds, 'sampled_frame': True}
                    unit['source_location'].pop('page_number', None)
                    unit['text'] = f'Sampled video frame at {seconds:.1f}s; a still image does not establish motion:\n' + unit['text']
                    units.append(unit)
                report('reading_video_frames', index + 1, count)
            warnings.append(f'Visual content was sampled at {len(seen)} timestamps, not every frame. Speech is transcribed separately when available.')
    except Exception as error:
        warnings.append(f'Visual frame extraction failed ({type(error).__name__}); any extracted speech is preserved.')
    return units, list(dict.fromkeys(warnings))

