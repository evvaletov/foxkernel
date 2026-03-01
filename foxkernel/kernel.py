"""Jupyter kernel for the COSY INFINITY FOX language.

Persistent process model: a long-running cosy_jupyter binary maintains state
across cells. Supports two compilation modes:

  FULL — recompile all cells from scratch (O(N) per cell)
  INCR — compile only the new cell, appending to existing state (O(1) per cell)

Incremental mode is used automatically when possible, with transparent
fallback to full compilation on errors, deletions, or process restarts.
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
        self._cells = {}        # cell_key → code
        self._cell_order = []   # insertion-ordered list of cell_keys
        self._cosy_dir = os.environ.get('COSY_DIR', os.getcwd())
        self._timeout = int(os.environ.get('COSY_TIMEOUT', '300'))
        self._proc = None
        self._incr_ok = False

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
        self._incr_ok = False
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
        self._incr_ok = False

    def _send_interrupt_children(self):
        """Forward interrupt to the COSY subprocess."""
        if self._is_alive():
            self._proc.send_signal(signal.SIGINT)
        else:
            super()._send_interrupt_children()

    def _cell_key(self):
        """Get a stable key for the current cell.

        Uses Jupyter 5.5 cellId if available, falls back to execution_count.
        """
        try:
            parent = self.get_parent()
            cell_id = parent.get('content', {}).get('cellId')
            if cell_id:
                return cell_id
        except (AttributeError, TypeError):
            pass
        return self.execution_count

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
            try:
                ready, _, _ = select.select([fd], [], [], deadline)
            except (KeyboardInterrupt, InterruptedError):
                if self._is_alive():
                    self._proc.send_signal(signal.SIGINT)
                return lines, 'interrupted'
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

    def _build_fox_source(self, current_key):
        """Build concatenated .fox source for all cells up to current_key.

        Structure:
            INCLUDE 'COSY' ;
            <cell 1 code>
            CELEND 0 ;
            ...
            <cell N code>
            CELEND 0 ;
            END ;
        """
        parts = ["INCLUDE 'COSY' ;"]
        for key in self._cell_order:
            if key in self._cells:
                parts.append(self._cells[key])
                parts.append('CELEND 0 ;')
            if key == current_key:
                break
        parts.append('END ;')
        return '\n'.join(parts)

    def _build_incr_source(self, current_key):
        """Build source for incremental compilation (new cell only).

        No INCLUDE or BEGIN — the compiler state is restored by CELLCK
        to "inside BEGIN", so this code compiles as a continuation.
        """
        code = self._cells[current_key]
        return f'{code}\nCELEND 0 ;\nEND ;'

    def _use_incremental(self):
        """Decide whether to use incremental compilation."""
        return self._incr_ok and self._is_alive()

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
            self._cell_order.clear()
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
                    if 1 <= idx <= len(self._cell_order):
                        key = self._cell_order.pop(idx - 1)
                        del self._cells[key]
                        self._incr_ok = False
                        return True, f'Deleted cell {idx}.'
                    return True, f'No cell at position {idx}.'
                except ValueError:
                    return True, 'Usage: %delete <position>'
            return True, (f'{len(self._cell_order)} cells in history. '
                          f'Use %cells to list. Usage: %delete <N>')
        if stripped == '%cells':
            if not self._cell_order:
                return True, 'No cells in history.'
            lines = []
            for i, key in enumerate(self._cell_order):
                if key in self._cells:
                    preview = self._cells[key].split('\n', 1)[0][:60]
                    lines.append(f'  {i + 1}: {preview}')
            return True, '\n'.join(lines)
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

        # Store this cell (cell ID tracking)
        key = self._cell_key()
        is_new = key not in self._cells
        if not is_new:
            old_code = self._cells[key]
            self._cells[key] = code
            if old_code != code:
                self._kill_process()
            self._incr_ok = False
        else:
            self._cells[key] = code
            self._cell_order.append(key)

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

        # Choose compilation mode
        use_incr = is_new and self._use_incremental()
        if use_incr:
            source = self._build_incr_source(key)
            prefix = 'INCR:'
        else:
            source = self._build_fox_source(key)
            prefix = 'FULL:'

        # Write to temp file
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.fox', dir=self._cosy_dir, delete=False
        ) as f:
            f.write(source)
            temp_path = f.name

        try:
            # Send file path with protocol prefix
            self._proc.stdin.write((prefix + temp_path + '\n').encode())
            self._proc.stdin.flush()

            # Read output until delimiter
            raw_lines, status = self._read_until_delimiter()

            # Filter out compilation banners
            output_lines = self._filter_output(raw_lines)
            is_error = status == 'error' or self._check_errors(raw_lines)

            if status == 'interrupted':
                self._incr_ok = False
                if not silent:
                    self.send_response(self.iopub_socket, 'stream', {
                        'name': 'stderr',
                        'text': 'Execution interrupted.\n',
                    })
                return {
                    'status': 'abort', 'execution_count': self.execution_count,
                }

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
                self._incr_ok = False
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

            if is_error:
                self._incr_ok = False
            else:
                self._incr_ok = True

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
