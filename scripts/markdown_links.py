"""Extract local Markdown destinations without resolving or fetching them."""

from urllib.parse import unquote, urlsplit

try:
    from markdown_it import MarkdownIt
    from markdown_it.parser_block import ParserBlock
    from markdown_it.parser_inline import ParserInline
except ModuleNotFoundError as error:
    if error.name != "markdown_it":
        raise
    raise SystemExit(
        "missing verification dependency: markdown-it-py; install with this interpreter: "
        "python -m pip install --require-hashes -r requirements-links.lock"
    ) from None

MAX_NESTING = 64


def _check_level(level):
    if level >= MAX_NESTING:
        raise ValueError("markdown_nesting_limit")


class _StrictBlock(ParserBlock):
    def tokenize(self, state, startLine, endLine):
        # Upstream would silently discard the remaining block at this limit.
        _check_level(state.level)
        return super().tokenize(state, startLine, endLine)


class _StrictInline(ParserInline):
    def __init__(self):
        super().__init__()
        self.parse_depth = 0

    def parse(self, src, md, env, tokens):
        # Image labels create fresh inline states, resetting state.level.
        _check_level(self.parse_depth)
        self.parse_depth += 1
        try:
            return super().parse(src, md, env, tokens)
        finally:
            self.parse_depth -= 1

    def tokenize(self, state):
        _check_level(state.level)
        return super().tokenize(state)

    def skipToken(self, state):
        # Upstream's validation-mode fallback can omit a valid nested link.
        _check_level(state.level)
        return super().skipToken(state)


def local_destinations(text):
    """Yield decoded paths in document order, excluding schemes and authorities.

    Parse CommonMark links/images, including references; code and raw HTML are
    not link nodes. Queries/fragments are not filesystem paths. Decode entities
    before URL splitting (in the parser) and percent escapes afterward, once each.
    Excessive nesting raises instead of producing a silently incomplete scan.
    """
    parser = MarkdownIt("commonmark", {"maxNesting": MAX_NESTING})
    parser.block = _StrictBlock()
    parser.inline = _StrictInline()
    pending = list(reversed(parser.parse(text)))
    while pending:
        node = pending.pop()
        destination = None
        if node.type == "link_open":
            destination = node.attrGet("href")
        elif node.type == "image":
            destination = node.attrGet("src")
        if destination is not None:
            url = urlsplit(destination)
            if not url.scheme and not url.netloc and url.path:
                yield unquote(url.path, errors="strict")
        if node.children:
            pending.extend(reversed(node.children))
