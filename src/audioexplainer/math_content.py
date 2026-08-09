import re
import html

try:
    import latex2mathml.converter
    HAS_LATEX2MATHML = True
except ImportError:
    HAS_LATEX2MATHML = False

MATH_PATTERN = re.compile(
    r'(?P<fenced>```.*?```)|'
    r'(?P<inline>`[^`\n]+`)|'
    r'(?P<escape>\\\$)|'
    r'(?P<block_dollar>\$\$.*?\$\$)|'
    r'(?P<block_bracket>\\\[.*?\\\])|'
    r'(?P<inline_dollar>(?<!\\)\$(?!\s)[^$]*?(?<!\s)(?<!\\)\$)|'
    r'(?P<inline_paren>\\\(.*?\\\))',
    re.DOTALL
)


def _tex_argument(text: str, start: int) -> tuple[str, int] | None:
    r"""Return one TeX argument and the position after it.

    Supports balanced braced groups, control sequences, and TeX's compact
    single-character arguments (for example ``\frac1\sigma``).
    """
    pos = start
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text):
        return None
    if text[pos] == "{":
        depth = 1
        end = pos + 1
        while end < len(text) and depth:
            if text[end] == "{" and (end == 0 or text[end - 1] != "\\"):
                depth += 1
            elif text[end] == "}" and (end == 0 or text[end - 1] != "\\"):
                depth -= 1
            end += 1
        if depth:
            return None
        return text[pos + 1:end - 1], end
    if text[pos] == "\\":
        match = re.match(r"\\[a-zA-Z]+|\\.", text[pos:])
        if not match:
            return None
        return match.group(0), pos + len(match.group(0))
    return text[pos], pos + 1


def _replace_tex_fractions(text: str, over: str) -> str:
    """Replace fractions from right to left, including mixed argument forms."""
    while True:
        start = text.rfind(r"\frac")
        if start < 0:
            return text
        numerator = _tex_argument(text, start + len(r"\frac"))
        if numerator is None:
            return text[:start] + " " + text[start + len(r"\frac"):]
        denominator = _tex_argument(text, numerator[1])
        if denominator is None:
            return text[:start] + numerator[0] + text[numerator[1]:]
        replacement = f" {numerator[0]} {over} {denominator[0]} "
        text = text[:start] + replacement + text[denominator[1]:]

def render_mathml(latex_str: str, display: bool = False) -> str:
    if HAS_LATEX2MATHML:
        try:
            return latex2mathml.converter.convert(latex_str, display="block" if display else "inline")
        except Exception:
            pass
    escaped = html.escape(latex_str)
    return f'<math><semantics><annotation encoding="application/x-tex">{escaped}</annotation></semantics></math>'

def verbalize(latex: str, lang: str = "en") -> str:
    if lang.startswith("es"):
        plus, minus, equals = " más ", " menos ", " igual a "
        over = " sobre "
        sqrt = "raíz cuadrada de "
        squared = " al cuadrado"
        cubed = " al cubo"
        to_power = " a la potencia de "
        sum_from = r"suma desde \1 hasta \2"
        int_from = r"integral desde \1 hasta \2"
        lim_as = r"límite cuando \1 tiende a \2"
        sum_of = "suma de "
        int_of = "integral de "
        lim_of = "límite de "
        sub = " sub "
        greek_map = {
            "alpha": "alfa", "beta": "beta", "gamma": "gamma", "delta": "delta",
            "epsilon": "épsilon", "zeta": "zeta", "eta": "eta", "theta": "theta",
            "iota": "iota", "kappa": "kappa", "lambda": "lambda", "mu": "mu",
            "nu": "nu", "xi": "xi", "pi": "pi", "rho": "rho", "sigma": "sigma",
            "tau": "tau", "upsilon": "ípsilon", "phi": "phi", "chi": "chi",
            "psi": "psi", "omega": "omega",
            "infty": "infinito", "to": "tiende a", "rightarrow": "tiende a"
        }
    else:
        plus, minus, equals = " plus ", " minus ", " equals "
        over = " over "
        sqrt = "square root of "
        squared = " squared"
        cubed = " cubed"
        to_power = " to the power of "
        sum_from = r"sum from \1 to \2"
        int_from = r"integral from \1 to \2"
        lim_as = r"limit as \1 approaches \2"
        sum_of = "sum of "
        int_of = "integral of "
        lim_of = "limit of "
        sub = " sub "
        greek_map = {
            "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
            "epsilon": "epsilon", "zeta": "zeta", "eta": "eta", "theta": "theta",
            "iota": "iota", "kappa": "kappa", "lambda": "lambda", "mu": "mu",
            "nu": "nu", "xi": "xi", "pi": "pi", "rho": "rho", "sigma": "sigma",
            "tau": "tau", "upsilon": "upsilon", "phi": "phi", "chi": "chi",
            "psi": "psi", "omega": "omega", "infty": "infinity",
            "to": "approaches", "rightarrow": "approaches"
        }

    text = latex
    # Presentation-only LaTeX must never leak into the spoken caption.  Remove
    # spacing before expanding \text{}, otherwise ``\quad\text{sujeto}``
    # becomes the unrecognizable control sequence ``\quadsujeto``.
    text = re.sub(r'\\(?:qquad|quad|left|right|displaystyle)(?![a-zA-Z])', ' ', text)
    text = re.sub(r'\\[,;:!]', ' ', text)
    text = re.sub(r'\\text{([^}]+)}', r' \1 ', text)
    text = re.sub(r'\\(?:begin|end){[^}]+}', ' ', text)
    text = text.replace(r'\\', '; ')
    text = text.replace(r'\{', ' ').replace(r'\}', ' ')

    accent_word = "barra" if lang.startswith("es") else "bar"
    text = re.sub(r'\\(?:bar|overline)\s*{([^{}]+)}', rf' \1 {accent_word} ', text)
    text = re.sub(r'\\(?:bar|overline)\s*(\\[a-zA-Z]+|[a-zA-Z0-9])', rf' \1 {accent_word} ', text)
    text = re.sub(
        r'\\mathcal\s*{?([a-zA-Z])}?',
        (rf' \1 caligráfica ' if lang.startswith("es") else rf' calligraphic \1 '),
        text,
    )

    operator_words = {
        r'\equiv': " equivale a " if lang.startswith("es") else " is equivalent to ",
        r'\neq': " distinto de " if lang.startswith("es") else " not equal to ",
        r'\geq': " mayor o igual que " if lang.startswith("es") else " greater than or equal to ",
        r'\ge': " mayor o igual que " if lang.startswith("es") else " greater than or equal to ",
        r'\leq': " menor o igual que " if lang.startswith("es") else " less than or equal to ",
        r'\le': " menor o igual que " if lang.startswith("es") else " less than or equal to ",
    }
    for command, spoken_operator in operator_words.items():
        text = text.replace(command, spoken_operator)
    if lang.startswith("es"):
        text = text.replace('>', ' mayor que ').replace('<', ' menor que ')
        text = re.sub(
            r'\\min_\{([^{}]+)\}',
            r' mínimo sobre el conjunto donde \1 ',
            text,
        )
    else:
        text = text.replace('>', ' greater than ').replace('<', ' less than ')
        text = re.sub(
            r'\\min_\{([^{}]+)\}',
            r' minimum over the set where \1 ',
            text,
        )

    def replace_bounds(m):
        op = m.group(1)
        sub_v = m.group(2) or m.group(3)
        sup_v = m.group(4) or m.group(5)
        fmt = sum_from if op == "sum" else int_from
        return " " + fmt.replace(r"\1", sub_v).replace(r"\2", sup_v) + " "

    text = re.sub(r'\\(sum|int)_(?:\{([^\}]+)\}|([a-zA-Z0-9=]+))\^(?:\{([^\}]+)\}|(\\[a-zA-Z]+|[a-zA-Z0-9]))', replace_bounds, text)

    def replace_lim(m):
        var = m.group(1)
        target = m.group(2)
        return " " + lim_as.replace(r"\1", var).replace(r"\2", target) + " "

    text = re.sub(r'\\lim_\{([^}]+?)\s*\\(?:to|rightarrow)\s*([^}]+)\}', replace_lim, text)
    text = re.sub(r'\\lim_([a-zA-Z0-9]+)\\to([a-zA-Z0-9]+|\\infty)', replace_lim, text)

    text = _replace_tex_fractions(text, over)
    if lang.startswith("es"):
        text = text.replace('/', over)
    text = text.replace('+', plus).replace('-', minus).replace('=', equals)
    text = text.replace('^2', squared).replace('^3', cubed)
    text = re.sub(r'\^(\\[a-zA-Z]+)', rf'{to_power} \1 ', text)
    text = re.sub(r'\^([a-zA-Z0-9])', rf'{to_power} \1 ', text)
    text = re.sub(r'\^{([^{}]+)}', rf'{to_power} \1 ', text)
    text = re.sub(r'\\sqrt{([^{}]+)}', rf'{sqrt} \1', text)
    text = re.sub(r'_\{([^{}]+)\}', rf'{sub}\1 ', text)
    text = re.sub(r'_([a-zA-Z0-9])', rf'{sub}\1 ', text)

    text = text.replace(r'\sum', sum_of).replace(r'\int', int_of).replace(r'\lim', lim_of)

    def macro_replace(m):
        cmd = m.group(1)
        lower_cmd = cmd.lower()
        if lower_cmd in greek_map:
            return " " + greek_map[lower_cmd] + " "
        known_words = {
            "partial": "derivada parcial de" if lang.startswith("es") else "partial derivative of",
            "ln": "logaritmo natural de" if lang.startswith("es") else "natural log of",
            "min": "mínimo" if lang.startswith("es") else "minimum",
            "ell": "ele" if lang.startswith("es") else "ell",
        }
        if lower_cmd in known_words:
            return " " + known_words[lower_cmd] + " "
        # Unknown commands are formatting instructions more often than
        # semantic tokens. Dropping them is safer than exposing raw LaTeX in
        # the player or sending command names to text-to-speech.
        return " "

    text = re.sub(r'\\([a-zA-Z]+)', macro_replace, text)
    text = text.replace('{', ' ').replace('}', ' ').replace('_', ' ').replace('&', ' ')
    text = text.replace('\\', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def prepare_content(text: str, lang: str = "en") -> dict:
    formulas = []

    def replacer(match):
        if match.group('fenced') or match.group('inline') or match.group('escape'):
            return match.group(0)

        inner = ""
        display = False
        original = match.group(0)

        if match.group('block_dollar'):
            inner = original[2:-2]
            display = True
        elif match.group('block_bracket'):
            inner = original[2:-2]
            display = True
        elif match.group('inline_dollar'):
            inner = original[1:-1]
            display = False
        elif match.group('inline_paren'):
            inner = original[2:-2]
            display = False
        else:
            return original

        mathml = render_mathml(inner, display=display)
        spoken = verbalize(inner, lang)
        marker = f"94778{len(formulas)}94778"
        formulas.append({
            "marker": marker,
            "original": original,
            "mathml": mathml,
            "spoken": spoken,
            "display": display,
        })
        return marker

    marked_text = MATH_PATTERN.sub(replacer, text)

    spoken_text = marked_text
    for f in formulas:
        spoken_text = spoken_text.replace(f["marker"], f["spoken"])

    return {
        "marked_text": marked_text,
        "spoken_text": spoken_text,
        "formulas": formulas
    }
