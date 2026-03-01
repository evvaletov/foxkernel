#!/usr/bin/env python3
"""End-to-end test for the foxkernel using jupyter_client.KernelManager."""

import os
import sys
import time

import jupyter_client

COSY_DIR = os.environ.get('COSY_DIR', os.path.expanduser('~/COSY/COSYFFAG_dev'))
TIMEOUT = 60  # seconds per cell


def execute_cell(kc, code, cell_num):
    """Execute a cell and return (output_text, status)."""
    msg_id = kc.execute(code)

    outputs = []
    status = None

    deadline = time.time() + TIMEOUT
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return '\n'.join(outputs), 'timeout'

        try:
            msg = kc.get_iopub_msg(timeout=remaining)
        except Exception:
            break

        msg_type = msg['header']['msg_type']
        parent_id = msg['parent_header'].get('msg_id', '')

        if parent_id != msg_id:
            continue

        if msg_type == 'stream':
            text = msg['content'].get('text', '')
            outputs.append(text.rstrip('\n'))

        elif msg_type == 'error':
            tb = msg['content'].get('traceback', [])
            outputs.append('\n'.join(tb))

        elif msg_type == 'status':
            if msg['content'].get('execution_state') == 'idle':
                break

    # Get the execute_reply
    try:
        reply = kc.get_shell_msg(timeout=10)
        status = reply['content']['status']
    except Exception as e:
        status = f'error (no reply: {e})'

    return '\n'.join(outputs), status


def main():
    print(f"COSY_DIR = {COSY_DIR}")
    print(f"cosy_jupyter exists: {os.path.exists(os.path.join(COSY_DIR, 'cosy_jupyter'))}")
    print()

    # Set COSY_DIR in environment for the kernel
    os.environ['COSY_DIR'] = COSY_DIR

    km = jupyter_client.KernelManager(kernel_name='fox')
    km.start_kernel(env={**os.environ, 'COSY_DIR': COSY_DIR})

    kc = km.client()
    kc.start_channels()

    # Wait for kernel ready
    try:
        kc.wait_for_ready(timeout=30)
        print("Kernel ready.\n")
    except RuntimeError as e:
        print(f"Kernel failed to start: {e}")
        km.shutdown_kernel(now=True)
        sys.exit(1)

    cells = [
        {
            'code': "VARIABLE X 1 ;\nX := 42 ;\nWRITE 6 'X=' X ;",
            'verify': '42',
            'desc': 'Simple assignment and write (X=42)',
        },
        {
            'code': "VARIABLE Y 1 ;\nY := X + 100 ;\nWRITE 6 'Y=' Y ;",
            'verify': '142',
            'desc': 'Cross-cell variable reference (Y=X+100=142)',
        },
        {
            'code': "VARIABLE Z 1 ;\nZ := SQRT(2) ;\nWRITE 6 'SQRT2=' Z ;",
            'verify': '1.414',
            'desc': 'Built-in function call (SQRT(2))',
        },
        {
            'code': (
                "PROCEDURE DOUBLE X RES ;\n"
                "   RES := X * 2 ;\n"
                "ENDPROCEDURE ;\n"
                "VARIABLE A 1 ;\n"
                "A := 7 ;\n"
                "DOUBLE A A ;\n"
                "WRITE 6 'A*2=' A ;"
            ),
            'verify': '14',
            'desc': 'Procedure definition and call (DOUBLE 7 = 14)',
        },
    ]

    all_passed = True
    for i, cell in enumerate(cells, 1):
        print(f"--- Cell {i}: {cell['desc']} ---")
        print(f"Code:\n{cell['code']}\n")

        output, status = execute_cell(kc, cell['code'], i)

        print(f"Status: {status}")
        print(f"Output:\n{output}\n")

        if cell['verify'] in output:
            print(f"PASS: Output contains '{cell['verify']}'\n")
        else:
            print(f"FAIL: Expected '{cell['verify']}' in output\n")
            all_passed = False

    # Shutdown
    print("--- Shutting down kernel ---")
    kc.stop_channels()
    km.shutdown_kernel(now=True)

    if all_passed:
        print("\nAll cells PASSED.")
    else:
        print("\nSome cells FAILED.")
        sys.exit(1)


if __name__ == '__main__':
    main()
