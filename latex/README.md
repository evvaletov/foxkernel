# fox-listings — LaTeX listings language definition for COSYScript (COSY INFINITY)

A LaTeX package providing `listings` language support for
COSYScript, the programming language of the COSY INFINITY beam
physics and differential algebra framework.  COSYScript source
files use the `.fox` extension and the language is often called
"FOX" informally; this package uses `FOX` as the `listings`
language identifier.

## Features

- Complete keyword coverage: control flow, intrinsic functions,
  DA procedures, beam physics commands, graphics, constants
- Case-insensitive matching (FOX is case-insensitive)
- Nested `{...}` comment support
- Single-quoted string literals
- Two predefined styles: `FOXcolor` (screen) and `FOXmono` (print)
- Six keyword groups with independent styling

## Usage

```latex
\usepackage{fox-listings}

\begin{lstlisting}[style=FOXcolor]
INCLUDE 'COSY' ;
VARIABLE X 1 ;
X := SIN(0.5) ;
WRITE 6 X ;
END ;
\end{lstlisting}
```

Or with just the language (bring your own style):

```latex
\begin{lstlisting}[language=FOX]
...
\end{lstlisting}
```

## Requirements

- `listings` package
- `xcolor` package (loaded automatically)

## License

This material is subject to the LaTeX Project Public License 1.3c.
See https://www.latex-project.org/lppl/lppl-1-3c/

## Author

Eremey Valetov — https://github.com/evvaletov

## Links

- COSY INFINITY: https://bt.pa.msu.edu/index_cosy.htm
- foxkernel (Jupyter kernel for FOX): https://github.com/evvaletov/foxkernel
- cosy-vim (Vim/Neovim syntax): https://github.com/evvaletov/cosy-vim
