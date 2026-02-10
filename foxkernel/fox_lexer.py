"""Pygments lexer for the FOX language (COSY INFINITY)."""

from pygments.lexer import RegexLexer, bygroups, include
from pygments.token import (
    Comment, Keyword, Name, Number, Operator, Punctuation, String, Text,
)


class FoxLexer(RegexLexer):
    name = 'FOX'
    aliases = ['fox', 'cosy']
    filenames = ['*.fox']
    mimetypes = ['text/x-fox']

    tokens = {
        'root': [
            # Comments: { ... } (nestable, but Pygments regex can't do true
            # nesting -- treat { ... } as single-level; good enough for highlighting)
            (r'\{[^}]*\}', Comment),

            # Strings: single-quoted
            (r"'[^']*'", String.Single),

            # Statement terminator
            (r';', Punctuation),

            # Assignment operator
            (r':=', Operator),

            # Operators
            (r'[#|%&+\-*/^<>=]', Operator),

            # Keywords -- control flow
            (r'\b(PROCEDURE|ENDPROCEDURE|FUNCTION|ENDFUNCTION'
             r'|IF|ELSEIF|ENDIF|LOOP|ENDLOOP|WHILE|ENDWHILE'
             r'|BEGIN|END|INCLUDE|SAVE|QUIT'
             r'|VARIABLE|FIT|ENDFIT|PURE|ENDPURE)\b', Keyword),

            # Builtins -- I/O, math, DA, CONFIG
            (r'\b(WRITE|READ|OPENF|CLOSEF'
             r'|ABS|INT|SQRT|SIN|COS|TAN|ATAN|ATAN2|LOG|EXP|MOD'
             r'|CONS|DA|LO|NOT|OR|TYPE|LENGTH'
             r'|DAPEE|DAPEP|VELSET|VELGET|DER|INTEG|DAPRI|DAPRV'
             r'|CONFIG_SET|CONFIG_SET_ECHO|CONFIG_Q|IN_CONFIG|CONFIG'
             r'|DEF|OV|CR|UM|AM|PM|SM|ER|CE|RE|SET|MSC)\b',
             Name.Builtin),

            # Numbers: float and integer
            (r'[+-]?\d+\.\d*([eEdD][+-]?\d+)?', Number.Float),
            (r'[+-]?\d+[eEdD][+-]?\d+', Number.Float),
            (r'[+-]?\d+', Number.Integer),

            # Identifiers
            (r'[A-Za-z_]\w*', Name),

            # Parentheses, brackets, dots
            (r'[(),\[\].]', Punctuation),

            # Whitespace
            (r'\s+', Text),
        ],
    }
