"""
Config manager for itsubdl.
Handles reading/writing config.toml from user's app data directory.
"""
import os
import re
from pathlib import Path

import toml
from platformdirs import user_config_dir
from rich.console import Console

console = Console(color_system="truecolor")

CONFIG_DIR = Path(user_config_dir(".itsubdl"))
CONFIG_FILE = CONFIG_DIR / "config.toml"


def ensure_config_exists() -> dict:
    """
    Ensure config.toml exists in the user's app data directory.
    If it doesn't exist, prompt the user to enter their TMDB API key and storage directory.
    Returns the config dictionary.
    """
    if CONFIG_FILE.exists():
        return load_config()

    # Config doesn't exist, prompt user for input
    console.print("[yellow]Config not found. Let's set up your configuration.[/yellow]\n")

    tmdb_api_key = console.input("[cyan]Enter your TMDB API key:[/cyan] ").strip()
    if not tmdb_api_key:
        console.print("[red]Error: TMDB API key cannot be empty.[/red]")
        raise ValueError("TMDB API key is required")

    output_dir = console.input("[cyan]Enter your subtitle output directory:[/cyan] ").strip()
    if not output_dir:
        console.print("[red]Error: Output directory cannot be empty.[/red]")
        raise ValueError("Output directory is required")

    # Expand any environment variables or user home directory
    output_dir = os.path.expandvars(output_dir)
    output_dir = os.path.expanduser(output_dir)
    # Normalize to a forward-slash path so TOML doesn't interpret
    # single backslashes as escape sequences on Windows.
    try:
        output_dir = str(Path(output_dir).as_posix())
    except Exception:
        # fallback to replacing backslashes if Path.as_posix() fails
        output_dir = output_dir.replace('\\', '/')

    # Create the config dictionary
    config = {
        "tmdb": {
            "api_key": tmdb_api_key,
        },
        "output": {
            "directory": output_dir,
        }
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        toml.dump(config, f)

    console.print(f"[green]Config saved to {CONFIG_FILE}[/green]\n")
    return config


def load_config() -> dict:
    """
    Load config from config.toml.
    Returns the config dictionary.
    """
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_FILE}")

    # Read the file contents first so we can attempt a lightweight
    # recovery if TOML parsing fails due to windows backslashes in
    # path strings (reserved escape sequences like \U).
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        return toml.loads(content)
    except Exception as err:
        # If parsing failed due to reserved escape sequences, try to
        # convert backslashes inside quoted strings to forward slashes
        # and retry. This fixes malformed files written with single
        # backslashes on Windows.
        try:
            fixed = re.sub(r'"([A-Za-z]:\\[^"\n]*)"',
                           lambda m: '"' + m.group(1).replace('\\', '/') + '"',
                           content)
            config = toml.loads(fixed)
            # Persist the fixed content back to the config file so
            # subsequent runs don't hit the same error.
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(fixed)
            return config
        except Exception:
            # Re-raise the original error with context if we cannot fix
            raise


def get_tmdb_api_key() -> str:
    """Get the TMDB API key from config."""
    config = ensure_config_exists()
    return config.get("tmdb", {}).get("api_key", "")


def get_output_directory() -> str:
    """Get the output directory from config."""
    config = ensure_config_exists()
    return config.get("output", {}).get("directory", "")


def update_tmdb_api_key(new_api_key: str) -> None:
    """Update the TMDB API key in config."""
    if not new_api_key or not new_api_key.strip():
        raise ValueError("TMDB API key cannot be empty")

    try:
        config = load_config()
    except FileNotFoundError:
        config = {
            "tmdb": {"api_key": new_api_key.strip()},
            "output": {"directory": ""},
        }
    else:
        if "tmdb" not in config:
            config["tmdb"] = {}
        config["tmdb"]["api_key"] = new_api_key.strip()

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        toml.dump(config, f)

    console.print(f"[green]TMDB API key updated successfully[/green]")


def update_output_directory(new_output_dir: str) -> None:
    """Update the output directory in config."""
    if not new_output_dir or not new_output_dir.strip():
        raise ValueError("Output directory cannot be empty")

    new_output_dir = os.path.expandvars(new_output_dir)
    new_output_dir = os.path.expanduser(new_output_dir)
    # Normalize to forward-slashes to avoid TOML escape issues on Windows
    try:
        new_output_dir = str(Path(new_output_dir).as_posix())
    except Exception:
        new_output_dir = new_output_dir.replace('\\', '/')

    try:
        config = load_config()
    except FileNotFoundError:
        config = {
            "tmdb": {"api_key": ""},
            "output": {"directory": new_output_dir},
        }
    else:
        if "output" not in config:
            config["output"] = {}
        config["output"]["directory"] = new_output_dir

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        toml.dump(config, f)

    console.print(f"[green]Output directory updated to: {new_output_dir}[/green]")
