
import os

import click

from .build import BertBuild

@click.command()
@click.argument('input', nargs=-1)
def cli(input):
    click.echo("hello world")
    for inp in input:
        if os.path.isdir(inp):
            inp = os.path.join(inp, "bert.yml")

        build = BertBuild(inp)
        click.echo(build)
