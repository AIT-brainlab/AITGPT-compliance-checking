import os
import requests
import typer

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

cli = typer.Typer()


@cli.command()
def load(
    model_name: str = typer.Argument(OLLAMA_MODEL, help="Name of the model to load in ollama")
):
    """
    Load ollama model using cli command via REST API: ollama load <model_name>
    """
    typer.echo(f"Pulling {model_name} from {OLLAMA_HOST}...")
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/pull",
            json={"name": model_name, "stream": False},
            timeout=600,
        )
        response.raise_for_status()
        typer.echo(response.json().get("status", "done"))
    except requests.RequestException as e:
        typer.echo(f"Error pulling model: {e}", err=True)
        raise typer.Exit(1)


@cli.command()
def list():
    """
    List model already load in ollama using cli command via REST API: ollama list.
    """
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=30)
        response.raise_for_status()
        models = response.json().get("models", [])
        if not models:
            typer.echo("No models found.")
            return

        typer.echo(f"{'NAME':<25} {'ID':<15} {'SIZE':<10} {'MODIFIED'}")

        for m in models:
            name = m.get("name", "")
            model_id = m.get("digest", "")[:12]
            size_bytes = m.get("size", 0)
            size_str = f"{size_bytes / 1e9:.1f} GB"
            modified = m.get("modified_at", "")[:10]  # just the date portion

            typer.echo(f"{name:<25} {model_id:<15} {size_str:<10} {modified}")

    except requests.RequestException as e:
        typer.echo(f"Error listing models: {e}", err=True)
        raise typer.Exit(1)


@cli.command()
def host():
    """
    Print ollama host using cli command: $OLLAMA_HOST
    """
    typer.echo(OLLAMA_HOST)


@cli.command()
def chat(
    model_name: str = typer.Argument(..., help="Name of the model to chat with")
):
    """
    Chat with ollama model interactively.
    """
    typer.echo(f"Chatting with {model_name} at {OLLAMA_HOST}. Type 'exit' or Ctrl+C to quit.\n")
    messages: list[dict[str, str]] = []
    while True:
        try:
            user_input = typer.prompt("You")
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nGoodbye!")
            break
        if user_input.strip().lower() in ("exit", "quit"):
            break
        messages.append({"role": "user", "content": user_input})
        try:
            response = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={"model": model_name, "messages": messages, "stream": False},
                timeout=120,
            )
            response.raise_for_status()
            assistant_content = response.json()["message"]["content"]
            messages.append({"role": "assistant", "content": assistant_content})
            typer.echo(f"\nAssistant: {assistant_content}\n")
        except requests.RequestException as e:
            typer.echo(f"Error contacting Ollama: {e}", err=True)
            raise typer.Exit(1)

@cli.command()
def delete(
    model_name: str = typer.Argument(..., help="Name of the model to delete from ollama")
):
    """
    Delete ollama model already load in ollama via REST API: ollama delete <model_name>.
    """
    typer.echo(f"Deleting {model_name} from {OLLAMA_HOST}...")
    try:
        response = requests.delete(
            f"{OLLAMA_HOST}/api/delete",
            json={"name": model_name},
            timeout=30,
        )
        response.raise_for_status()
        typer.echo(f"Deleted model {model_name} successfully.")
    except requests.RequestException as e:
        typer.echo(f"Error deleting model: {e}", err=True)
        raise typer.Exit(1)