# foxkernel Roadmap

## UX Improvements

### Near-term

| # | Item | Impact | Effort | Description |
|---|------|--------|--------|-------------|
| 1 | Cell ID tracking | High | Medium | Use Jupyter protocol 5.5 `cellId` field to key `_cells` by notebook cell ID instead of `execution_count`. Re-running a cell replaces the old version automatically — no `%delete` needed. |
| 2 | README update | High | Low | Update from v0.1.0 concatenate-and-run description to v0.3.0 persistent process model with incremental compilation. New examples, `cosy_jupyter` binary, `%delete`, interactive cell-by-cell workflow. |
| 3 | Kernel interrupt | High | Low | Implement `do_interrupt()`: send `SIGINT` to the COSY process via `os.kill(self._proc.pid, signal.SIGINT)`. Currently the only escape from long-running computation is timeout. |
| 4 | `%who` / `%cells` magics | Medium | Low | `%cells`: show cell history (execution count + first line preview). `%who`: list declared variables by scanning VARIABLE declarations in stored cells. |
| 5 | Better `is_complete` heuristic | Medium | Low | Track block nesting (PROCEDURE/ENDPROCEDURE, IF/ENDIF, LOOP/ENDLOOP) for smarter multi-line input handling in console frontend. |
| 6 | `do_inspect` (Shift-Tab help) | Medium | Low | Static dict of docstrings for FOX builtins. Show brief description and argument signature on Shift-Tab. |
| 7 | Dynamic tab completion | Medium | Medium | After each execution, parse stored cells for VARIABLE, PROCEDURE, FUNCTION declarations. Add those names to the completion list alongside static keywords. |
| 8 | Richer error display | Medium | Medium | Use Jupyter's structured error format with ANSI coloring. Parse COSY error output to extract the offending line and highlight it in context. |
| 9 | Multi-page PS plot handling | Medium | Medium | COSY's `PP` command generates multi-page PostScript. Split into per-page images using Ghostscript `-dFirstPage`/`-dLastPage`. |
| 10 | SVG plot output | Low | Low | Vector graphics instead of rasterized PNG. Ghostscript can output SVG directly. Crisper, scalable plots. |
| 11 | `%lis` magic | Low | Low | Show the COSY compilation listing for debugging. |
| 12 | `%config` magic | Low | Low | Sugar for `CONFIG_SET 'KEY' VALUE ;`, auto-injected before cell code. |

## Architecture

| # | Item | Description |
|---|------|-------------|
| 13 | Incremental compilation | Compile only the new cell, O(1) per cell instead of O(N). Implemented in v0.3.0. |
| 14 | Julia/Mathematica DA integration | Process-based IPC for licensed COSY users. See design notes below. |

## Interpreter Modernization (foxy.f)

COSY INFINITY's runtime is a single-pass compiler (CODCOM) emitting threaded
bytecode (NCOD) executed by a 353-label computed-GOTO virtual machine (CODEXE),
all in Fortran 77. The entire system spans ~37k lines across foxy.f (7,237),
dafox.f (20,857), foxfit.f (1,995), and foxgraf.f (6,759).

**Why modern Fortran, not F77?** The claim that F77 is faster is a myth from
the 1990s. Modern compilers (gfortran, ifort, ifx) use the same optimization
backend for F77 and F90+. SELECT CASE compiles to the same jump table as
computed GOTO. INTENT declarations and modules actually *help* optimization by
providing aliasing and interface information. The performance-critical code is
DA polynomial arithmetic in dafox.f inner loops — identical in any Fortran
standard. The real reason COSY stayed F77 is the cost and risk of rewriting
37k lines of working code, not performance.

**Approach: Hybrid (rewrite parser/executor in F90+, keep dafox.f as-is).**
Direct `CALL` to existing dafox.f subroutines — no FFI, no wrapper overhead,
single binary. dafox.f, foxfit.f, foxgraf.f remain untouched F77; only the
compiler and VM are modernized.

### Tier 1 — Improve cell mode (weeks, F77)

Incremental improvements to the existing CODEXE, no architectural changes.
Best immediate bang-for-buck for Jupyter.

| # | Item | Description |
|---|------|-------------|
| 18 | Error recovery in CODEXE | Catch runtime errors (array bounds, division by zero) without crashing the process. Add `SIGNAL`/`SIGFPE` handler to return control to CELLCK with error status instead of SIGBUS/SIGFPE death. |
| 19 | Variable introspection | `%who` magic queries ISYM/CSYM/NTYP to list declared variables with types and sizes. `%whos` adds values for scalars. Requires a new intrinsic procedure (CELVAR) that walks the symbol table. |
| 20 | Statement-level error reporting | On compilation error, emit the source line number and offending token from CODCOM state (TEFIL, INLINE) instead of just "### ERROR". |

### Tier 2 — Rewrite CODCOM in modern Fortran (1–2 months)

Replace the single-pass compiler with a proper recursive-descent parser in
F90+. Still emits NCOD bytecode for CODEXE execution. Practical win for
Jupyter UX: meaningful error messages with line/column, better diagnostics.

| # | Item | Description |
|---|------|-------------|
| 21 | F90+ recursive-descent parser | Replace CODCOM's character-by-character scanner and CSYN-table-driven compilation with a standard recursive-descent parser using F90 modules, derived types for tokens, and SELECT CASE. |
| 22 | Structured error messages | Parser errors include source line, column, context window, and suggestion. Replaces "### ERROR" / "$$$ " format. |
| 23 | ARICOM replacement | Replace the shunting-yard expression compiler with Pratt parsing. Cleaner operator precedence handling, better error recovery for malformed expressions. |
| 24 | Source-level debugging info | Emit line-number metadata in NCOD so runtime errors can report the source location, not just "instruction at IC=N". |

### Tier 2.5 — Modernize foxy.f to F2003+ (2–4 weeks)

Straightforward syntactic upgrade of the existing foxy.f — no architectural
changes, no new parser, no AST. Same algorithms, same NCOD, same dispatch.
Purpose: eliminate legacy constructs, enable compiler diagnostics, establish
a clean baseline for benchmarking against F77 and for the Tier 3 work.

Synergistic with Tiers 2–3: modernized code is easier to refactor into
modules, and the benchmark data validates (or refutes) performance claims.

| # | Item | Description |
|---|------|-------------|
| 25 | Computed GOTO → SELECT CASE | Replace the 353-label `GOTO (1,2,...,353), IGOTO` dispatch in CODEXE and all other computed GOTOs with `SELECT CASE`. Identical machine code, but readable, and enables compiler warnings for missing cases. |
| 26 | COMMON → modules | Migrate the unnamed COMMON block (CC, NC, NTYP, NBEG, NEND, NMAX) and all 21 named COMMON blocks (/DACOM/, /TMCOM/, /CODE/, etc.) to F90 modules with explicit `USE`. Enables INTENT checking and interprocedural optimization. |
| 27 | Fixed-form → free-form | Convert fixed-form (columns 1–6 + 72-char limit) to free-form `.f90`. Eliminates continuation-column errors and enables modern editor support. Mechanical transformation (tools: `f2f`, `findent`, or sed). |
| 28 | Implicit none | Add `IMPLICIT NONE` throughout. Fix the hundreds of implicitly-typed variables this will expose. Catches latent bugs (typos creating new variables). |
| 29 | F77→F2003 constructs | `EQUIVALENCE` → proper type handling, `GOTO` spaghetti → `DO`/`EXIT`/`CYCLE`, `SAVE`+`DATA` in subroutines → module variables, `CHARACTER*N` → `CHARACTER(LEN=N)`. |
| 30 | Benchmark: F2003 vs F77 | Identical test programs (DA polynomial multiplication, map composition, full COSYFFAG lattice tracking) run on both versions. Compare wall time, memory, and compiler optimization reports (`-fopt-info`, `-qopt-report`). Publish results. |

### Tier 3 — AST interpreter in modern Fortran (3–6 months)

Full interpreter: parse FOX source to an AST (F2003 derived types with
polymorphism), walk the AST directly, call dafox.f for DA operations. No NCOD
compilation step. Enables error recovery, introspection, and step-debugging.

| # | Item | Description |
|---|------|-------------|
| 31 | AST representation | F2003 derived types with `CLASS` polymorphism for AST nodes: expressions, statements, blocks, procedures. Allocatable child arrays for variable-arity nodes. |
| 32 | Tree-walking executor | Recursive AST evaluator. Each node type has an `execute` method. Variable storage migrates from COMMON arrays to a proper scope-chain with F90 allocatable arrays. dafox.f calls unchanged. |
| 33 | Interactive REPL mode | Parse and execute one statement at a time. Full introspection: inspect any variable, step through code, set breakpoints on procedures. Ideal backend for Jupyter. |
| 34 | Backward compatibility | Run existing .fox programs identically. Validate against COSY's test suite and known COSYFFAG lattice results (closed orbits, tunes). |
| 35 | Benchmark: AST interpreter vs NCOD VM | Compare Tier 3 tree-walking interpreter against Tier 2.5 modernized NCOD VM. Quantify the interpretation overhead vs compilation+dispatch. If significant, consider a JIT path (Tier 4). |

### Tier 4 — FOX compiler with native executable generation (6–12 months)

Compile FOX programs to native executables rather than interpreting them.
Two sub-approaches, not mutually exclusive.

| # | Item | Description |
|---|------|-------------|
| 36 | FOX → Fortran transpiler | Translate FOX source to equivalent F2003 code that calls dafox.f directly. Compile with gfortran/ifort to produce a standalone `.exe`. Simplest path: the AST from Tier 3 is emitted as Fortran instead of being walked. Eliminates all interpreter overhead. |
| 37 | FOX → LLVM IR compiler | Emit LLVM IR from the FOX AST, link against dafox.f (as bitcode or object). Enables full LLVM optimization pipeline (-O2/-O3), auto-vectorization of DA inner loops, and cross-platform native binaries. Higher effort but maximum performance. |
| 38 | Standalone .exe packaging | Compile a FOX program + dafox.f + foxfit.f + foxgraf.f into a single self-contained binary with no runtime dependency on COSY. Useful for deployment, distribution, and embedding in larger systems. |

## DA Research

| # | Item | Description |
|---|------|-------------|
| 15 | Generalized DA beyond Taylor | COSY uses Taylor-like DA (truncated power series). Research and implement more general DA forms — Laurent series, Puiseux series, asymptotic expansions, or DA over non-Archimedean fields. Could be an extension to COSY itself or a separate codebase (existing open-source C++ DA library like DACE, or a new Julia package). |
| 16 | Full-featured Julia DA package | A production-quality Julia package implementing DA at COSY's level and beyond: Taylor DA, map composition/inversion, normal forms, verified computation (Taylor models), plus extensions (generalized DA from item 15, GPU acceleration, automatic parallelism). Native Julia with operator overloading and ecosystem integration (DifferentialEquations.jl, Optimization.jl). |
| 17 | Orbital dynamics and spacecraft control with DA | Research DA applications in orbit propagation with uncertainty quantification, conjunction analysis, low-thrust trajectory optimization, autonomous GN&C. Use Julia (with native DA package, item 16) or COSY. Survey existing DA work in astrodynamics (Politecnico di Milano / ESA groups using DACE, JPL's DA-based navigation). Target: DA for orbital dynamics research grant application. |

---

## Julia / Mathematica DA Integration Design

### Goal

Let licensed COSY users call COSY's full DA engine (not just TPSA — includes differentiation, integration, map composition, normal forms, all 350+ beam physics procedures) from Julia or Mathematica.

### Approach: Process-Based IPC

```
Julia/Mathematica  ←→  [stdin/stdout pipe]  ←→  cosy_jupyter -jupyter
```

Reuses the persistent-process infrastructure from foxkernel. The same `cosy_jupyter` binary serves both Jupyter notebooks and programmatic Julia/Mathematica clients.

**Why process-based over shared library:**
- No Fortran 77 COMMON block thread-safety issues
- No need to recompile COSY as a shared library
- Process isolation (crash safety)
- Works with unmodified COSY binary
- Already proven by glyfada's `PersistentCosyEvaluator`

The shared-library approach (C wrapper via `ISO_C_BINDING`, Julia `ccall`, Mathematica LibraryLink) is the long-term path for performance-critical use but requires migrating COMMON blocks to Fortran 2003 modules.

### Protocol

Extend the existing `<<<CELL_DONE>>>` / `<<<CELL_ERROR>>>` protocol with structured data exchange. The Julia/Mathematica client generates FOX code, sends it as a cell, reads the output. Identical to glyfada's pattern.

### Julia Package Sketch: `COSYLink.jl`

```julia
module COSYLink

struct CosyProcess
    proc::Base.Process
    stdin::IO
    stdout::IO
end

function start(; cosy_dir::String, timeout::Int=300)
    # Launch cosy_jupyter -jupyter, return CosyProcess
end

function eval_cell(cp::CosyProcess, fox_code::String)
    # Write fox code to temp file, send FULL:<path> on stdin
    # Read stdout until <<<CELL_DONE>>> or <<<CELL_ERROR>>>
end

function eval_da(cp::CosyProcess; expr::String, order::Int, nvars::Int)
    # Generate FOX code that evaluates a DA expression and prints coefficients
    # Parse output into a Julia array of DA coefficients
end

end
```

### Mathematica Package

Two approaches:
1. **Simple**: `RunProcess` / `StartProcess` with stdin/stdout pipes.
2. **WSTP**: Native Mathematica protocol for bidirectional async communication.

Start with approach 1, evolve to WSTP if latency matters.

### Relation to Roadmap Items 15-16

COSYLink.jl provides full COSY functionality via IPC today, while the native Julia DA package (item 16) provides performance and ecosystem integration long-term. The two are complementary.

---

## GPU Acceleration

Existing GPU plumbing: `fortran/gpu_blas.c` (cuBLAS via `dlopen`) and
`fortran/gpu_bicgstab.f90` (GPU-accelerated BiCGSTAB) in COSYFFAG_dev.

| # | Item | Speedup | Effort | Description |
|---|------|---------|--------|-------------|
| 39 | ES lens G-matrix assembly | 50–200x | Days | GPU kernel for elliptic integral K(m) evaluation + cuBLAS for the O(n²) influence matrix assembly. Currently NumPy/SciPy on CPU. Embarrassingly parallel — one thread per (i,j) pair. |
| 40 | ES lens dense solve | 10–50x | Days | Replace `numpy.linalg.inv` with cuSOLVER (LU factorization + triangular solve) for the 6,000×6,000 BEM system. Drop-in via CuPy or direct cuSOLVER bindings. |
| 41 | FFAG BEM N-matrix assembly | 10–50x | Weeks | GPU volume-integral evaluation for the O(N²) BEM interaction matrix (rectangular, hexahedral, oriented elements with 2×2×2 Gauss quadrature). Currently OpenMP on CPU. Custom CUDA kernels for each element type. |

---

## Publication TODOs

- [ ] Upload `fox-listings` package to CTAN (https://ctan.org/upload) — ZIP at `latex/` or `~/foxkernel/fox-listings.zip`
- [ ] Publish IntelliJ FOX plugin to JetBrains Marketplace — requires JetBrains account, plugin signing certificate, and marketplace upload token (see `intellij-fox-plugin/gradle.properties` for placeholders)
