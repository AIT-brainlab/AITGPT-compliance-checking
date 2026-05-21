import typer

cli = typer.Typer()

@cli.command()
def ollama_load(
    model_name: str = typer.Argument(..., help="Name of the model to load in ollama")
    ):
    """
    Load ollama model using cli command: ollama load <model_name>
    """
    pass

@cli.command()
def ollama_list():
    """
    List model already load in ollama using cli command: ollama list
    """
    pass

@cli.command()
def ollama_host():
    """
    Print ollama host using cli command: $OLLAMA_HOST
    """
    pass

@cli.command()
def ollama_chat(
    model_name: str = typer.Argument(..., help="Name of the model to chat with")
    ):
    """
    Chat with ollama model interactively.
    """
    pass