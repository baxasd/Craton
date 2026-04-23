import zmq
import configparser
import os
import logging
import socket

log = logging.getLogger("ConfigManager")

def get_local_ip():
    """Returns the local IP address of the machine."""
    try:
        # Create a dummy socket to find the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        # Doesn't even have to be reachable
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def ensure_config(settings_path='settings.ini'):
    """Checks if settings.ini exists. If not, generates it with keys and defaults."""
    if os.path.exists(settings_path):
        return

    # Generate Curve25519 keys for silent setup
    server_public, server_secret = zmq.curve_keypair()
    client_public, client_secret = zmq.curve_keypair()

    config = configparser.ConfigParser(interpolation=None)
    
    defaults = {
        'Hardware': {
            'radar_cfg_file': 'src/radar/config.cfg', 
            'cli_port': 'auto', 
            'data_port': 'auto'
        },
        'Network': {
            'zmq_radar_port': '5555', 
            'zmq_camera_port': '5556', 
            'zmq_key_port': '5554'
        },
        'Recording': {
            'chunk_size': '50'
        },
        'Viewer': {
            'default_ip': '127.0.0.1', 
            'max_range_m': '5.0', 
            'cmap': 'inferno', 
            'low_pct': '40.0', 
            'high_pct': '99.5', 
            'smooth_grid_size': '250'
        },
        'Camera': {
            'width': '640', 
            'height': '480', 
            'fps': '30', 
            'model_complexity': '1', 
            'jpeg_quality': '80', 
            'auto_exposure': 'False', 
            'exposure': '450'
        },
        'Security': {
            'server_public': server_public.decode('ascii'),
            'server_secret': server_secret.decode('ascii'),
            'client_public': client_public.decode('ascii'),
            'client_secret': client_secret.decode('ascii'),
            'studio_password': 'admin' # Default password for first run
        }
    }

    config.read_dict(defaults)

    try:
        with open(settings_path, 'w') as f:
            config.write(f)
        print(f"AUTO-CONFIG: Generated new {settings_path} with security keys.")
    except Exception as e:
        log.error(f"Failed to auto-generate config: {e}")
