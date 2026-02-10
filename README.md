# FOX Kernel for Jupyter

A Jupyter kernel for the [COSY INFINITY](https://bt.pa.msu.edu/index_cosy.htm) FOX programming language.

## Features

- **Concatenate-and-run execution:** All notebook code cells are concatenated into a single `.fox` file and executed via `./cosy`. Users write complete FOX programs across cells.
- **Output parsing:** Strips the COSY startup banner, returns user-visible output. Detects compilation (`### ERROR`) and runtime (`QUIT AT`) errors.
- **PostScript plot rendering:** Automatically detects new `.ps` files generated during execution and converts them to inline PNG images via Ghostscript.
- **Tab completion:** FOX keywords and builtins.
- **FOX Pygments lexer:** Registered as a Pygments entry point for syntax highlighting in Jupyter, Sphinx, and other tools.

## Magic Commands

| Command | Description |
|---------|-------------|
| `%reset` | Clear cell history |
| `%timeout N` | Set execution timeout to N seconds (default: 300) |
| `%cosy_dir /path` | Set working directory for COSY execution |

## Installation

```bash
pip install foxkernel
foxkernel-install --user
```

Or from source:

```bash
git clone https://github.com/evvaletov/foxkernel.git
cd foxkernel
pip install -e .
foxkernel-install --user
```

Verify installation:

```bash
jupyter kernelspec list
```

## Requirements

- Python 3.8+
- `jupyter_client`, `ipykernel` (installed automatically)
- A COSY INFINITY binary (`./cosy`) in the working directory or specified via `COSY_DIR`
- Ghostscript (`gs`) for PostScript plot rendering (optional)

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `COSY_DIR` | Current directory | Directory containing the `cosy` binary |
| `COSY_TIMEOUT` | 300 | Execution timeout in seconds |

## Usage

1. Start Jupyter: `jupyter notebook` or `jupyter lab`
2. Create a new notebook and select the **FOX (COSY INFINITY)** kernel
3. Write FOX code across cells — each cell execution concatenates all cells and runs them

### Example

**Cell 1:**
```fox
INCLUDE 'COSY' ;

PROCEDURE RUN ;
   DEF ;
   OV 3 3 0 ;
```

**Cell 2:**
```fox
   VARIABLE X 1 ;
   X := SIN(PI/4) ;
   WRITE 6 'sin(pi/4) = '&S(X) ;
ENDPROCEDURE ;
RUN ; END ;
```

## License

MIT
