
import os

import click

from .build import BertBuild, BuildFailed

@click.command()
@click.argument('input', nargs=-1)
def cli(input):
    if not input:
        input = ["."]

    for inp in input:
        if os.path.isdir(inp):
            inp = os.path.join(inp, "bert-build.yml")

        build = BertBuild(inp)
        try:
            build.build()
        except BuildFailed as bf:
            click.echo("Failed({})".format(bf), err=True)
