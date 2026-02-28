"""Jupyter kernel for the COSY INFINITY FOX language.

Persistent process model: a long-running cosy_jupyter binary maintains state
across cells. Each cell execution recompiles all cells but only executes new
code (compile-all-execute-new). CELEND intrinsic boundaries separate cells.
"""

import base64
import os
import re
import select
import signal
import subprocess
import tempfile
from pathlib import Path

from ipykernel.kernelbase import Kernel

from . import __version__
from .ps_convert import ps_to_png

_CELL_DONE = '<<<CELL_DONE>>>'
_CELL_ERROR = '<<<CELL_ERROR>>>'
_COMPILE_MARKER = '--- BEGINNING COMPILATION'
_EXEC_MARKER = '--- BEGINNING EXECUTION'
_ERROR_PATTERNS = [re.compile(r'###\s*ERROR'), re.compile(r'\$\$\$\s')]

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
        self._proc = None

    def _find_binary(self):
        """Find the cosy_jupyter binary."""
        for name in ('cosy_jupyter', 'cosy'):
            path = Path(self._cosy_dir) / name
            if path.exists() and os.access(path, os.X_OK):
                return path
        return None

    def _start_process(self):
        """Start or restart the COSY jupyter process."""
        self._kill_process()
        binary = self._find_binary()
        if binary is None:
            return False
        self._proc = subprocess.Popen(
            [str(binary), '-jupyter'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self._cosy_dir,
            bufsize=0,
        )
        return True

    def _kill_process(self):
        """Kill the COSY process if running."""
        if self._proc is not None:
            try:
                self._proc.kill()
                self._proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
            self._proc = None

    def _is_alive(self):
        """Check if the process is still running."""
        return self._proc is not None and self._proc.poll() is None

    def _read_until_delimiter(self):
        """Read stdout until <<<CELL_DONE>>> or <<<CELL_ERROR>>> or timeout.

        Returns (output_lines, delimiter_type) where delimiter_type is
        'done', 'error', or 'timeout'.
        """
        lines = []
        deadline = self._timeout
        fd = self._proc.stdout.fileno()

        buf = b''
        while True:
            ready, _, _ = select.select([fd], [], [], deadline)
            if not ready:
                return lines, 'timeout'

            chunk = os.read(fd, 8192)
            if not chunk:
                # Process died
                return lines, 'died'

            buf += chunk
            while b'\n' in buf:
                line_bytes, buf = buf.split(b'\n', 1)
                line = line_bytes.decode('utf-8', errors='replace').rstrip('\r')
                if line.strip() == _CELL_DONE:
                    return lines, 'done'
                if line.strip() == _CELL_ERROR:
                    return lines, 'error'
                lines.append(line)

    def _build_fox_source(self, cell_index):
        """Build concatenated .fox source for all cells up to cell_index.

        Structure:
            INCLUDE 'COSY' ;
            <cell 1 code>
            CELEND 0 ;
            <cell 2 code>
            CELEND 0 ;
            ...
            <cell N code>
            CELEND 0 ;
            END ;
        """
        parts = ["INCLUDE 'COSY' ;"]
        for idx in sorted(self._cells):
            if idx > cell_index:
                break
            parts.append(self._cells[idx])
            parts.append('CELEND 0 ;')
        parts.append('END ;')
        return '\n'.join(parts)

    def _filter_output(self, lines):
        """Remove compilation banners, keep only user-visible output."""
        result = []
        skip_banner = True
        for line in lines:
            if _COMPILE_MARKER in line or _EXEC_MARKER in line:
                skip_banner = False
                continue
            if skip_banner and line.strip().startswith('---'):
                continue
            if 'BIN FILE READ' in line:
                continue
            result.append(line)
        return result

    def _check_errors(self, lines):
        """Check for compilation or runtime errors in output lines."""
        for line in lines:
            for pattern in _ERROR_PATTERNS:
                if pattern.search(line):
                    return True
        return False

    def _handle_magic(self, code):
        """Handle magic commands. Returns (handled, response) tuple."""
        stripped = code.strip()
        if stripped == '%reset':
            self._cells.clear()
            self._kill_process()
            return True, 'Session reset. All cells cleared.'
        if stripped.startswith('%timeout'):
            parts = stripped.split()
            if len(parts) == 2:
                try:
                    self._timeout = int(parts[1])
                    return True, f'Timeout set to {self._timeout}s.'
                except ValueError:
                    return True, 'Usage: %timeout <seconds>'
            return True, f'Current timeout: {self._timeout}s. Usage: %timeout <seconds>'
        if stripped.startswith('%delete'):
            parts = stripped.split()
            if len(parts) == 2:
                try:
                    idx = int(parts[1])
                    if idx in self._cells:
                        del self._cells[idx]
                        return True, f'Deleted cell [{idx}].'
                    return True, f'No cell [{idx}] in history.'
                except ValueError:
                    return True, 'Usage: %delete <execution_count>'
            return True, f'Cells in history: {sorted(self._cells.keys())}. Usage: %delete <N>'
        if stripped.startswith('%cosy_dir'):
            parts = stripped.split(maxsplit=1)
            if len(parts) == 2:
                path = parts[1].strip()
                if os.path.isdir(path):
                    self._cosy_dir = path
                    self._kill_process()
                    return True, f'Working directory set to {self._cosy_dir}'
                return True, f'Directory not found: {path}'
            return True, f'Current directory: {self._cosy_dir}. Usage: %cosy_dir /path'
        return False, None

    def _snapshot_ps_files(self):
        ps_dir = Path(self._cosy_dir)
        return {
            p: p.stat().st_mtime
            for p in ps_dir.glob('*.ps')
            if p.is_file()
        }

    def _find_new_ps(self, before):
        ps_dir = Path(self._cosy_dir)
        new_files = []
        for p in sorted(ps_dir.glob('*.ps')):
            if not p.is_file():
                continue
            mtime = p.stat().st_mtime
            if p not in before or mtime > before[p]:
                new_files.append(p)
        return new_files

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

        # Skip empty cells
        if not code.strip():
            return {
                'status': 'ok', 'execution_count': self.execution_count,
                'payload': [], 'user_expressions': {},
            }

        # Store this cell
        self._cells[self.execution_count] = code

        # Start process if needed
        if not self._is_alive():
            if not self._start_process():
                if not silent:
                    self.send_response(self.iopub_socket, 'stream', {
                        'name': 'stderr',
                        'text': f'cosy_jupyter binary not found in {self._cosy_dir}\n'
                                f'Set COSY_DIR or use %cosy_dir\n',
                    })
                return {
                    'status': 'error', 'execution_count': self.execution_count,
                    'ename': 'FileNotFoundError', 'evalue': 'cosy_jupyter not found',
                    'traceback': [],
                }

        ps_before = self._snapshot_ps_files()

        # Build source with all cells concatenated
        source = self._build_fox_source(self.execution_count)

        # Write to temp file
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.fox', dir=self._cosy_dir, delete=False
        ) as f:
            f.write(source)
            temp_path = f.name

        try:
            # Send file path to the process
            self._proc.stdin.write((temp_path + '\n').encode())
            self._proc.stdin.flush()

            # Read output until delimiter
            raw_lines, status = self._read_until_delimiter()

            # Filter out compilation banners
            output_lines = self._filter_output(raw_lines)
            is_error = status == 'error' or self._check_errors(raw_lines)

            if status == 'timeout':
                self._kill_process()
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

            if status == 'died':
                self._proc = None
                if not silent:
                    output = '\n'.join(output_lines)
                    self.send_response(self.iopub_socket, 'stream', {
                        'name': 'stderr',
                        'text': f'COSY process died unexpectedly.\n{output}\n',
                    })
                return {
                    'status': 'error', 'execution_count': self.execution_count,
                    'ename': 'RuntimeError', 'evalue': 'Process died',
                    'traceback': [],
                }

            # The COSY process only executes NEW code (compile-all-execute-new),
            # so each cell path produces exactly one <<<CELL_DONE>>>.
            output = '\n'.join(output_lines).strip()

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

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def do_complete(self, code, cursor_pos):
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
        stripped = code.strip()
        if not stripped:
            return {'status': 'incomplete', 'indent': ''}
        if stripped.endswith(';'):
            return {'status': 'complete'}
        return {'status': 'incomplete', 'indent': '   '}

    def do_shutdown(self, restart):
        self._kill_process()
        return {'status': 'ok', 'restart': restart}
