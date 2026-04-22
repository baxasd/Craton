import zmq
import configparser
import os
from rich.console import Console
from rich.prompt import Prompt
import time

def run():
    console = Console()

    console.print("\n[bold]Craton Suite Setup & Keygen[/bold]\n")

    studio_pass = Prompt.ask("New Password")

    with console.status("[dim]Generating cryptographic keys and building configuration...[/dim]", spinner="dots"):
        server_public, server_secret = zmq.curve_keypair()
        client_public, client_secret = zmq.curve_keypair()

        config = configparser.ConfigParser(interpolation=None)
        settings_file = 'settings.ini'

        defaults = {
            'Hardware': {'radar_cfg_file': 'src/radar/config.cfg', 'cli_port': 'auto', 'data_port': 'auto'},
            'Network': {'zmq_radar_port': '5555', 'zmq_camera_port': '5556'},
            'Recording': {'chunk_size': '50'},
            'Viewer': {'default_ip': '127.0.0.1', 'max_range_m': '5.0', 'cmap': 'inferno', 'low_pct': '40.0', 'high_pct': '99.5', 'smooth_grid_size': '250'},
            'Camera': {'width': '640', 'height': '480', 'fps': '30', 'model_complexity': '1', 'jpeg_quality': '80', 'auto_exposure': 'False', 'exposure': '450'}
        }

        config.read_dict(defaults)

        if os.path.exists(settings_file):
            config.read(settings_file)

        if 'Security' not in config:
            config.add_section('Security')
            
        config['Security']['server_public'] = server_public.decode('ascii')
        config['Security']['server_secret'] = server_secret.decode('ascii')
        config['Security']['client_public'] = client_public.decode('ascii')
        config['Security']['client_secret'] = client_secret.decode('ascii')
        config['Security']['studio_password'] = studio_pass

        with open(settings_file, 'w') as f:
            config.write(f)
        
        time.sleep(3)

    console.print(f"[green]✔[/green] [dim]Configuration saved to: {settings_file}[/dim]\n")

if __name__ == "__main__":
    run()
    Console().input("[dim]Press Enter to exit...[/dim]")