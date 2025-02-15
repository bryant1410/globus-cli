from __future__ import annotations

import typing as t

import click

from globus_cli.types import DATA_CONTAINER_T

F = t.TypeVar("F", bound=t.Callable)


def str2bool(v: str) -> bool | None:
    v = v.lower()
    if v in ("y", "yes", "t", "true", "on", "1"):
        return True
    elif v in ("n", "no", "f", "false", "off", "0"):
        return False
    else:
        return None


def unquote_cmdprompt_single_quotes(arg: str) -> str:
    """
    remove leading and trailing single quotes from a string when
    there is a leading and trailing single quote

    per the name of this function, it is meant to provide compatibility
    with cmdprompt which interprets inputs like

        $ mycmd 'foo'

    as including the single quote chars and passes "'foo'" to our
    commands
    """
    if len(arg) >= 2 and arg[0] == "'" and arg[-1] == "'":
        return arg[1:-1]
    return arg


def fold_decorators(f: F, decorators: list[t.Callable[[F], F]]) -> F:
    for deco in decorators:
        f = deco(f)
    return f


def get_current_option_help(
    *, filter_names: t.Iterable[str] | None = None
) -> list[str]:
    ctx = click.get_current_context()
    cmd = ctx.command
    opts = [x for x in cmd.params if isinstance(x, click.Option)]
    if filter_names is not None:
        opts = [o for o in opts if o.name is not None and o.name in filter_names]
    return [o.get_error_hint(ctx) for o in opts]


def supported_parameters(c: t.Callable) -> list[str]:
    import inspect

    sig = inspect.signature(c)
    return list(sig.parameters.keys())


def format_list_of_words(first: str, *rest: str) -> str:
    if not rest:
        return first
    if len(rest) == 1:
        return f"{first} and {rest[0]}"
    return ", ".join([first] + list(rest[:-1])) + f", and {rest[-1]}"


def format_plural_str(
    formatstr: str, pluralizable: dict[str, str], use_plural: bool
) -> str:
    """
    Format text with singular or plural forms of words. Use the singular forms as
    keys in the format string.

    Usage:

    >>> command_list = [...]
    >>> fmtstr = "you need to run {this} {command}:"
    >>> print(
    ...     format_plural_str(
    ...         fmtstr,
    ...         {"this": "these", "command": "commands"},
    ...         len(command_list) == 1
    ...     )
    ... )
    >>> print("  " + "\n  ".join(command_list))
    """
    argdict = {
        singular: plural if use_plural else singular
        for singular, plural in pluralizable.items()
    }
    return formatstr.format(**argdict)


class CLIStubResponse:
    """
    A stub response class to make arbitrary data accessible in a way similar to a
    GlobusHTTPResponse object.
    """

    def __init__(self, data: DATA_CONTAINER_T) -> None:
        self.data = data

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def __getitem__(self, key: str) -> t.Any:
        return self.data[key]


# wrap to add a `has_next()` method and `limit` param to a naive iterator
class PagingWrapper:
    def __init__(
        self,
        iterator: t.Iterator[t.Any],
        limit: int | None = None,
        json_conversion_key: str | None = None,
    ) -> None:
        self.iterator = iterator
        self.next = None
        self.limit = limit
        self.json_conversion_key = json_conversion_key
        self._step()

    def _step(self) -> None:
        try:
            self.next = next(self.iterator)
        except StopIteration:
            self.next = None

    def has_next(self) -> bool:
        return self.next is not None

    def __iter__(self) -> t.Iterator[t.Any]:
        yielded = 0
        while self.has_next() and (self.limit is None or yielded < self.limit):
            cur = self.next
            self._step()
            yield cur
            yielded += 1

    @property
    def json_converter(
        self,
    ) -> t.Callable[[t.Iterator[t.Any]], dict[str, list[t.Any]]]:
        if self.json_conversion_key is None:
            raise NotImplementedError("does not support json_converter")
        key: str = self.json_conversion_key

        def converter(it: t.Iterator[t.Any]) -> dict[str, list[t.Any]]:
            return {key: list(it)}

        return converter


def shlex_process_stream(
    process_command: click.Command, stream: t.TextIO, name: str
) -> None:
    """
    Use shlex to process stdin line-by-line.
    Also prints help text.

    Requires that @process_command be a Click command object, used for
    processing single lines of input. helptext is prepended to the standard
    message printed to interactive sessions.
    """
    import shlex

    # use readlines() rather than implicit file read line looping to force
    # python to properly capture EOF (otherwise, EOF acts as a flush and
    # things get weird)
    for lineno, line in enumerate(stream.readlines()):
        # get the argument vector:
        # do a shlex split to handle quoted paths with spaces in them
        # also lets us have comments with #
        argv = shlex.split(line, comments=True)
        if argv:
            try:
                with process_command.make_context(f"<process {name}>", argv) as ctx:
                    process_command.invoke(ctx)
            except click.ClickException as error:
                click.echo(
                    f"error encountered processing '{name}' in "
                    f"{stream.name} at line {lineno}:",
                    err=True,
                )
                click.echo(
                    click.style(f"  {error.format_message()}", fg="yellow"), err=True
                )
                click.get_current_context().exit(2)


class CLIAuthRequirementsError(Exception):
    """
    A class for internally generated auth requirements
    """

    def __init__(
        self, message: str, *, required_scopes: list[str] | None = None
    ) -> None:
        self.message = message
        self.required_scopes = required_scopes
