import os
import sys
import webbrowser
from threading import Timer
import streamlit.web.cli as stcli
from rich.console import Console
import time
from src.utils.config import ensure_config
from src.utils.theme import SETTINGS_PATH

# Ensure config exists before launching
ensure_config(SETTINGS_PATH)

# Rich Console
console = Console()

def open_browser():
    """Waits for the server to spin up, then opens the browser."""
    webbrowser.open("http://localhost:8501")

if __name__ == "__main__":
    
    if getattr(sys, 'frozen', False):
        application_path = sys._MEIPASS
        os.chdir(application_path)

    console.print(f"\n[bold]Craton Studio[/bold]")
    with console.status("[dim]Launching Craton Studio server...[/dim]", spinner="dots"):
        
        # Run Streamlit with custom arguments
        sys.argv = [
            "streamlit", 
            "run", 
            "src/studio/router.py", 
            "--global.developmentMode=false", 
            "--logger.level=error"
        ]        
        time.sleep(2)
    console.print("[green]✔[/green] [dim]Server active[/dim]\n")

    # Schedule the browser to open
    Timer(2.5, open_browser).start()
                
    # Boot the Streamlit server
    sys.exit(stcli.main())