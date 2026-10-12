"""Convert legacy PowerPoint files using a local LibreOffice installation."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .utils import has_zip_signature, validate_file_size


class PptConversionError(RuntimeError):
    pass


def _find_soffice() -> str:
    configured = os.getenv('LIBREOFFICE_PATH', '').strip().strip('"')
    if configured:
        if Path(configured).is_file():
            return configured
        raise PptConversionError('LIBREOFFICE_PATH does not point to a valid executable.')
    for executable in ('soffice', 'libreoffice'):
        found = shutil.which(executable)
        if found:
            return found
    for root in (os.getenv('ProgramFiles', r'C:\Program Files'),
                 os.getenv('ProgramFiles(x86)', r'C:\Program Files (x86)')):
        candidate = Path(root) / 'LibreOffice' / 'program' / 'soffice.exe'
        if candidate.is_file():
            return str(candidate)
    raise PptConversionError(
        'Legacy .ppt conversion is unavailable. Install LibreOffice on the backend '
        'computer, or upload a .pptx file instead.'
    )


def convert_ppt_to_pptx(data: bytes) -> bytes:
    validate_file_size(data)
    if not data.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        raise PptConversionError('The uploaded .ppt file is not a valid legacy Office container.')
    executable = _find_soffice()
    started = time.perf_counter()
    print('[PPT] Converting legacy presentation...', flush=True)
    with tempfile.TemporaryDirectory(prefix='aura-ppt-') as temporary:
        folder = Path(temporary)
        source = folder / 'presentation.ppt'
        output = folder / 'converted'
        output.mkdir()
        source.write_bytes(data)
        # An independent profile avoids conflicts with an open LibreOffice window.
        profile = (folder / 'profile').as_uri()
        command = [executable, f'-env:UserInstallation={profile}',
                   '--headless', '--nologo', '--nodefault', '--norestore',
                   '--convert-to', 'pptx:Impress MS PowerPoint 2007 XML',
                   '--outdir', str(output), str(source)]
        try:
            result = subprocess.run(command, capture_output=True, timeout=120,
                                    check=False, shell=False)
        except subprocess.TimeoutExpired as error:
            raise PptConversionError('PowerPoint conversion timed out after 120 seconds.') from error
        except OSError as error:
            raise PptConversionError('Could not start LibreOffice for PowerPoint conversion.') from error
        converted = output / 'presentation.pptx'
        if result.returncode != 0 or not converted.is_file():
            raise PptConversionError(
                'Could not convert this presentation. It may be damaged or password-protected.'
            )
        if converted.stat().st_size > 100 * 1024 * 1024:
            raise PptConversionError('Converted presentation exceeds the 100 MiB limit.')
        converted_data = converted.read_bytes()
        if not has_zip_signature(converted_data):
            raise PptConversionError('LibreOffice did not produce a valid PPTX file.')
    print(f'[PPT] Conversion completed in {time.perf_counter() - started:.1f} seconds.', flush=True)
    return converted_data
