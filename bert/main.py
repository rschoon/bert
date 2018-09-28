
import os

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

        build = BertBuild(inp, shell_fail=shell_fail)
        try:
            build.build()
        except BuildFailed as bf:
            click.echo("Failed({})".format(bf), err=True)
