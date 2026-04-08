import multiprocessing
import uvicorn
import webview
import threading
from api import app
from rich.console import Console

console = Console()

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="critical")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    console.print("[bold cyan]Starting JobMan AI Tracker GUI...[/bold cyan]")
    console.print("[dim]Booting local web server on port 8000...[/dim]")
    
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    
    console.print("[bold green]Spawning Chromium Webview Panel...[/bold green]")
    webview.create_window(
        "JobMan - The Digital Architect", 
        "http://127.0.0.1:8000", 
        width=1320, 
        height=850,
        background_color='#131313'
    )
    webview.start(private_mode=False)
