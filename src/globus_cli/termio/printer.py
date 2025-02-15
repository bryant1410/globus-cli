from __future__ import annotations

import enum
import json
import textwrap

import click
import globus_sdk

from globus_cli.utils import CLIStubResponse

from .awscli_text import unix_display
from .context import (
    get_jmespath_expression,
    outformat_is_json,
    outformat_is_text,
    outformat_is_unix,
)
from .field import Field
from .server_timing import maybe_show_server_timing


class TextMode(enum.Enum):
    silent = enum.auto()
    json = enum.auto()
    text_table = enum.auto()
    text_record = enum.auto()
    text_record_list = enum.auto()
    text_raw = enum.auto()
    text_custom = enum.auto()


def _jmespath_preprocess(res):
    jmespath_expr = get_jmespath_expression()

    if isinstance(res, (CLIStubResponse, globus_sdk.GlobusHTTPResponse)):
        res = res.data

    if not isinstance(res, str):
        if jmespath_expr is not None:
            res = jmespath_expr.search(res)

    return res


def print_json_response(res, *, sort_keys=True):
    res = _jmespath_preprocess(res)
    res = json.dumps(res, indent=2, separators=(",", ": "), sort_keys=sort_keys)
    click.echo(res)


def print_unix_response(res):
    res = _jmespath_preprocess(res)
    try:
        unix_display(res)
    # Attr errors indicate that we got data which cannot be unix formatted
    # likely a scalar + non-scalar in an array, though there may be other cases
    # print good error and exit(2) (Count this as UsageError!)
    except AttributeError:
        click.echo(
            "UNIX formatting of output failed."
            "\n  "
            "This usually means that data has a structure which cannot be "
            "handled by the UNIX formatter."
            "\n  "
            "To avoid this error in the future, ensure that you query the "
            'exact properties you want from output data with "--jmespath"',
            err=True,
        )
        click.get_current_context().exit(2)


def _colon_display(data, fields):
    maxlen = max(len(f.name) for f in fields) + 2
    indent = " " * maxlen
    wrapper = textwrap.TextWrapper(initial_indent=indent, subsequent_indent=indent)
    for field in fields:
        # str in case the result is `None`
        value = str(field(data))

        # 88 char wrap based on the same rationale that `black` and `flake8-bugbear`
        # use 88 chars (or if there's a newline)
        # only wrap if it's enabled and detected
        shouldwrap = field.wrap_enabled and (len(value) + maxlen > 88 or "\n" in value)
        if shouldwrap:
            # TextWrapper will discard existing whitespace, including newlines
            # so split, wrap each resulting line, then rejoin
            lines = value.split("\n")
            lines = [wrapper.fill(x) for x in lines]
            if len(lines) > 5:  # truncate here, max 5 lines
                lines = lines[:5] + [indent + "..."]
            # lstrip to remove indent on the first line, since it will be indented by
            # the format string below
            value = "\n".join(lines).lstrip()

        click.echo("{}{}".format((field.name + ":").ljust(maxlen), value))


def print_table(iterable, fields, print_headers=True):
    # the iterable may not be safe to walk multiple times, so we must walk it
    # only once -- however, to let us write things naturally, convert it to a
    # list and we can assume it is safe to walk repeatedly
    iterable = list(iterable)

    # extract headers and keys as separate lists
    headers = [f.name for f in fields]

    # use the iterable to find the max width of an element for each column
    # use a special function to handle empty iterable
    def get_max_colwidth(f):
        def _safelen(x):
            try:
                return len(x)
            except TypeError:
                return len(str(x))

        lengths = [_safelen(f(i)) for i in iterable]
        if not lengths:
            return 0
        else:
            return max(lengths)

    widths = [get_max_colwidth(f) for f in fields]
    # handle the case in which the column header is the widest thing
    widths = [max(w, len(h)) for w, h in zip(widths, headers)]

    def none_to_null(val):
        if val is None:
            return "NULL"
        return val

    def format_line(inputs):
        out = ""
        last_offset = 3
        for w, h, x in zip(widths, headers, inputs):
            out += str(x).ljust(w)
            if h:
                out += " | "
                last_offset = 3
            else:
                last_offset = 0
        return out[:-last_offset]

    # print headers
    if print_headers:
        click.echo(format_line(headers))
        click.echo(
            format_line(["-" * w if h else " " * w for w, h in zip(widths, headers)])
        )

    # print the rows of data
    for i in iterable:
        click.echo(format_line([none_to_null(f(i)) for f in fields]))


def display(
    response_data,
    *,
    simple_text=None,
    text_preamble=None,
    text_epilog=None,
    text_mode=TextMode.text_table,
    json_converter=None,
    fields: list[Field] | None = None,
    response_key=None,
    sort_json_keys=True,
):
    """
    A generic output printer. Consumes the following pieces of data:

    ``response_data`` is a dict, list (if the ``text_mode`` is
    ``TextMode.text_record_list``), or GlobusHTTPResponse object.
    It contains either an API response or synthesized data for printing.

    ``simple_text`` is a text override -- normal printing is skipped and this
    string is printed instead (text output only)
    ``text_preamble`` is text which prints before normal printing (text output
    only)
    ``text_epilog`` is text which prints after normal printing (text output
    only)
    ``text_mode`` is a TextMode OR a callable which takes ``response_data`` and prints
    output. Note that when a callable is given, it does the actual printing

    ``json_converter`` is a callable that does preprocessing of JSON output. It
    must take ``response_data`` and produce another dict or dict-like object
    (json/unix output only)

    ``fields`` is an iterable of fields. They may be expressed as Field
    objects, (fieldname, key_string) tuples, or (fieldname, key_func) tuples.

    ``response_key`` is a key into the data to print. When used with table
    printing, it must get an iterable out, and when used with raw printing, it
    gets a string. Necessary for certain formats like text table (text output
    only)

    ``sort_json_keys`` is a flag that will cause JSON keys to be sorted or unsorted.
    It is only used when the output format is JSON.
    """

    if isinstance(response_data, globus_sdk.GlobusHTTPResponse):
        maybe_show_server_timing(response_data)

    def _assert_fields():
        if fields is None:
            raise ValueError(
                "Internal Error! Output format requires fields; none given. "
                "You can workaround this error by using `--format JSON`"
            )

    def _print_as_json(*, sort_keys=True):
        print_json_response(
            json_converter(response_data) if json_converter else response_data,
            sort_keys=sort_keys,
        )

    def _print_as_unix():
        print_unix_response(
            json_converter(response_data) if json_converter else response_data
        )

    def _print_as_text():
        # if we're given simple text, print that and exit
        if simple_text is not None:
            click.echo(simple_text)
            return

        # if there's a preamble, print it beofre any other text
        if text_preamble is not None:
            click.echo(text_preamble)

        # If there's a response key, either key into the response data or apply it as a
        # callable to extract from the response data
        if response_key is None:
            data = response_data
        elif callable(response_key):
            data = response_key(response_data)
        else:
            data = response_data[response_key]

        #  do the various kinds of printing
        if text_mode == TextMode.text_table:
            _assert_fields()
            print_table(data, fields)
        elif text_mode == TextMode.text_record:
            _assert_fields()
            _colon_display(data, fields)
        elif text_mode == TextMode.text_record_list:
            _assert_fields()
            if not isinstance(data, list):
                raise ValueError("only lists can be output in text record list format")
            first = True
            for record in data:
                # add empty line between records after the first
                if not first:
                    click.echo()
                first = False
                _colon_display(record, fields)
        elif text_mode == TextMode.text_raw:
            click.echo(data)
        elif text_mode == TextMode.text_custom:
            # _custom_text_formatter is set along with FORMAT_TEXT_CUSTOM
            assert _custom_text_formatter
            _custom_text_formatter(data)

        # if there's an epilog, print it after any text
        if text_epilog is not None:
            click.echo(text_epilog)

    if isinstance(text_mode, TextMode):
        _custom_text_formatter = None
    else:
        _custom_text_formatter = text_mode
        text_mode = TextMode.text_custom

    if outformat_is_json() or (outformat_is_text() and text_mode == TextMode.json):
        _print_as_json(sort_keys=sort_json_keys)
    elif outformat_is_unix():
        _print_as_unix()
    else:
        # silent does nothing
        if text_mode == TextMode.silent:
            return
        _print_as_text()
