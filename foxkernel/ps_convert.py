"""PostScript to PNG conversion using Ghostscript."""

import subprocess
from pathlib import Path


def ps_to_png(ps_path, png_path=None, resolution=150):
    """Convert a PostScript file to PNG via ghostscript.

    Returns the path to the PNG file, or None on failure.
    """
    ps_path = Path(ps_path)
    if png_path is None:
        png_path = ps_path.with_suffix('.png')
    else:
        png_path = Path(png_path)

    try:
        subprocess.run(
            ['gs', '-dBATCH', '-dNOPAUSE', '-dSAFER',
             '-sDEVICE=pngalpha', f'-r{resolution}',
             f'-sOutputFile={png_path}', str(ps_path)],
            capture_output=True, timeout=30, check=True,
        )
        return png_path
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
