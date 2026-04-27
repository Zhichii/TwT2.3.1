import rich
from rich.text import Text as T
from rich.console import Console
from translations import translate as t

console = Console(highlight=False)

def error(content : str = "", exception : Exception | None = None):
    console.print(T(t("error"), style="bold red") + T(content, style="red not bold"))
    if exception is not None:
        console.print(T(str(exception), style="italic red"))

def whisper(content : str = ""):
    console.print(T(content, style="italic #808080")+T(t("whisper"), style="italic #808080"))

def hint(content : str = ""):
    console.print(T(content, style="italic #808080"))

