"""Install the FOX kernel into Jupyter."""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def install_kernel(user=True, prefix=None):
    """Install the FOX kernelspec."""
    from jupyter_client.kernelspec import KernelSpecManager

    kernel_dir = Path(__file__).parent
    kernel_json = kernel_dir / 'kernel.json'

    # Create a temporary directory with the kernelspec
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / 'fox'
        dest.mkdir()
        shutil.copy(kernel_json, dest / 'kernel.json')

        ksm = KernelSpecManager()
        ksm.install_kernel_spec(
            str(dest), kernel_name='fox', user=user, prefix=prefix,
        )

    print('FOX kernel installed successfully.')
    print('Run "jupyter kernelspec list" to verify.')


def main():
    parser = argparse.ArgumentParser(description='Install the FOX Jupyter kernel')
    parser.add_argument('--user', action='store_true', default=True,
                        help='Install for the current user (default)')
    parser.add_argument('--sys-prefix', action='store_true',
                        help='Install into sys.prefix (for virtualenvs)')
    parser.add_argument('--prefix', type=str, default=None,
                        help='Install into a specific prefix')
    args = parser.parse_args()

    if args.sys_prefix:
        install_kernel(user=False, prefix=sys.prefix)
    elif args.prefix:
        install_kernel(user=False, prefix=args.prefix)
    else:
        install_kernel(user=args.user)


if __name__ == '__main__':
    main()
