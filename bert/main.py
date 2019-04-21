
import os
import sys

import click

from .build import BertBuild, BuildFailed

@click.command()
@click.option("--shell-fail/--no-shell-fail", help="Drop into shell when command fails")
@click.argument('input', nargs=-1)
def cli(input, shell_fail):
    if not input:
        input = ["."]

    for inp in input:
        if os.path.isdir(inp):
            inp = os.path.join(inp, "bert-build.yml")

        try:
            build = BertBuild(inp, shell_fail=shell_fail)
        except FileNotFoundError as fef:
            click.echo(str(fef), err=True)
            sys.exit(1)
        except BuildFailed as bf:
            click.echo(str(bf), err=True)
            sys.exit(1)

        try:
            build.build()
        except BuildFailed as bf:
            click.echo(str(bf), err=True)
            sys.exit(1)
