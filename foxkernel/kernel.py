"""Jupyter kernel for the COSY INFINITY FOX language.

Concatenate-and-run model: all code cells are concatenated into a single .fox
file and executed via ./cosy. Users write complete FOX programs across cells.
"""

import base64
import os
import re
import subprocess
import tempfile
from pathlib import Path

from ipykernel.kernelbase import Kernel

from . import __version__
from .ps_convert import ps_to_png

# Lines before this marker are the COSY startup banner
_EXEC_MARKER = '--- BEGINNING EXECUTION'
_ERROR_PATTERNS = [re.compile(r'###\s*ERROR'), re.compile(r'QUIT AT')]

FOX_KEYWORDS = [
    'PROCEDURE', 'ENDPROCEDURE', 'FUNCTION', 'ENDFUNCTION',
    'IF', 'ELSEIF', 'ENDIF', 'LOOP', 'ENDLOOP', 'WHILE', 'ENDWHILE',
    'BEGIN', 'END', 'INCLUDE', 'SAVE', 'QUIT', 'VARIABLE',
    'FIT', 'ENDFIT', 'PURE', 'ENDPURE',
    'WRITE', 'READ', 'OPENF', 'CLOSEF',
    'ABS', 'INT', 'SQRT', 'SIN', 'COS', 'TAN', 'ATAN', 'ATAN2',
    'LOG', 'EXP', 'MOD', 'CONS', 'DA', 'LO', 'NOT', 'OR',
    'TYPE', 'LENGTH', 'DAPEE', 'DAPEP', 'VELSET', 'VELGET',
    'DER', 'INTEG', 'DAPRI', 'DAPRV',
    'CONFIG_SET', 'CONFIG_SET_ECHO', 'CONFIG_Q', 'IN_CONFIG', 'CONFIG',
    'DEF', 'OV', 'CR', 'UM', 'AM', 'PM', 'SM', 'ER', 'CE', 'RE', 'SET', 'MSC',
]


class FoxKernel(Kernel):
    implementation = 'foxkernel'
    implementation_version = __version__
    language = 'fox'
    language_version = '10.2'
    language_info = {
        'name': 'fox',
        'mimetype': 'text/x-fox',
        'file_extension': '.fox',
    }
    banner = 'FOX (COSY INFINITY) Kernel'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._cells = {}
        self._cosy_dir = os.environ.get('COSY_DIR', os.getcwd())
        self._timeout = int(os.environ.get('COSY_TIMEOUT', '300'))

    def _handle_magic(self, code):
        """Handle magic commands. Returns (handled, response) tuple."""
        stripped = code.strip()
        if stripped == '%reset':
            self._cells.clear()
            return True, 'Cell history cleared.'
        if stripped.startswith('%timeout'):
            parts = stripped.split()
            if len(parts) == 2:
                try:
                    self._timeout = int(parts[1])
                    return True, f'Timeout set to {self._timeout}s.'
                except ValueError:
                    return True, 'Usage: %timeout <seconds>'
            return True, f'Current timeout: {self._timeout}s. Usage: %timeout <seconds>'
        if stripped.startswith('%cosy_dir'):
            parts = stripped.split(maxsplit=1)
            if len(parts) == 2:
                path = parts[1].strip()
                if os.path.isdir(path):
                    self._cosy_dir = path
                    return True, f'Working directory set to {self._cosy_dir}'
                return True, f'Directory not found: {path}'
            return True, f'Current directory: {self._cosy_dir}. Usage: %cosy_dir /path'
        return False, None

    def _snapshot_ps_files(self):
        """Record current .ps files and their modification times."""
        ps_dir = Path(self._cosy_dir)
        return {
            p: p.stat().st_mtime
            for p in ps_dir.glob('*.ps')
            if p.is_file()
        }

    def _find_new_ps(self, before):
        """Find .ps files that are new or modified since the snapshot."""
        ps_dir = Path(self._cosy_dir)
        new_files = []
        for p in sorted(ps_dir.glob('*.ps')):
            if not p.is_file():
                continue
            mtime = p.stat().st_mtime
            if p not in before or mtime > before[p]:
                new_files.append(p)
        return new_files

    def _parse_output(self, stdout):
        """Strip the COSY banner, return user-visible output."""
        lines = stdout.split('\n')
        # Find the execution marker
        start = 0
        for i, line in enumerate(lines):
            if _EXEC_MARKER in line:
                start = i + 1
                break
        return '\n'.join(lines[start:]).strip()

    def _check_errors(self, output):
        """Check for compilation or runtime errors in output."""
        for pattern in _ERROR_PATTERNS:
            if pattern.search(output):
                return True
        return False

    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        # Handle magic commands
        handled, response = self._handle_magic(code)
        if handled:
            if not silent and response:
                self.send_response(self.iopub_socket, 'stream',
                                   {'name': 'stdout', 'text': response + '\n'})
            return {
                'status': 'ok', 'execution_count': self.execution_count,
                'payload': [], 'user_expressions': {},
            }

        # Store this cell
        self._cells[self.execution_count] = code

        # Concatenate all cells in execution order
        full_code = '\n'.join(
            self._cells[k] for k in sorted(self._cells)
        )

        # Write to temp file and execute
        cosy_bin = Path(self._cosy_dir) / 'cosy'
        if not cosy_bin.exists():
            if not silent:
                self.send_response(self.iopub_socket, 'stream', {
                    'name': 'stderr',
                    'text': f'COSY binary not found at {cosy_bin}\n'
                            f'Set COSY_DIR environment variable or use %cosy_dir\n',
                })
            return {
                'status': 'error', 'execution_count': self.execution_count,
                'ename': 'FileNotFoundError', 'evalue': 'cosy binary not found',
                'traceback': [],
            }

        ps_before = self._snapshot_ps_files()

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.fox', dir=self._cosy_dir, delete=False
        ) as f:
            f.write(full_code)
            temp_path = f.name

        try:
            result = subprocess.run(
                [str(cosy_bin), temp_path],
                capture_output=True, text=True,
                cwd=self._cosy_dir, timeout=self._timeout,
            )
            output = self._parse_output(result.stdout)
            is_error = self._check_errors(output) or result.returncode != 0

            if result.stderr.strip():
                output = output + '\n' + result.stderr.strip() if output else result.stderr.strip()

            if not silent and output:
                self.send_response(self.iopub_socket, 'stream', {
                    'name': 'stderr' if is_error else 'stdout',
                    'text': output + '\n',
                })

            # Check for new PostScript plots
            if not silent:
                for ps_file in self._find_new_ps(ps_before):
                    png_path = ps_to_png(ps_file)
                    if png_path and png_path.exists():
                        with open(png_path, 'rb') as img:
                            data = base64.b64encode(img.read()).decode('ascii')
                        self.send_response(self.iopub_socket, 'display_data', {
                            'data': {'image/png': data},
                            'metadata': {'image/png': {'width': 600}},
                        })
                        png_path.unlink(missing_ok=True)

            if is_error:
                return {
                    'status': 'error', 'execution_count': self.execution_count,
                    'ename': 'FOXError', 'evalue': 'Compilation or runtime error',
                    'traceback': output.split('\n') if output else [],
                }
            return {
                'status': 'ok', 'execution_count': self.execution_count,
                'payload': [], 'user_expressions': {},
            }

        except subprocess.TimeoutExpired:
            if not silent:
                self.send_response(self.iopub_socket, 'stream', {
                    'name': 'stderr',
                    'text': f'Execution timed out after {self._timeout}s. '
                            f'Use %timeout to increase.\n',
                })
            return {
                'status': 'error', 'execution_count': self.execution_count,
                'ename': 'TimeoutError', 'evalue': f'Timed out after {self._timeout}s',
                'traceback': [],
            }
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def do_complete(self, code, cursor_pos):
        # Extract the token being typed
        text_to_cursor = code[:cursor_pos]
        match = re.search(r'([A-Za-z_]\w*)$', text_to_cursor)
        if not match:
            return {'matches': [], 'cursor_start': cursor_pos,
                    'cursor_end': cursor_pos, 'status': 'ok'}

        token = match.group(1).upper()
        start = cursor_pos - len(token)
        matches = [kw for kw in FOX_KEYWORDS if kw.startswith(token)]
        return {
            'matches': matches, 'cursor_start': start,
            'cursor_end': cursor_pos, 'status': 'ok',
        }

    def do_is_complete(self, code):
        # Simple heuristic: count semicolons vs statements
        stripped = code.strip()
        if not stripped:
            return {'status': 'incomplete', 'indent': ''}
        if stripped.endswith(';'):
            return {'status': 'complete'}
        return {'status': 'incomplete', 'indent': '   '}
