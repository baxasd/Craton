import time                          # Used for sleep() during config sending and close()
import logging                       
import serial                        # pyserial: talks to the radar over USB-UART
from serial.tools import list_ports  # Used by find_ti_ports() to scan connected USB devices

from rad_parse import RadarConfig, parse_standard_frame

log = logging.getLogger("RadarHardware")

# 8-byte sync word that starts every TI radar packet. 
# It translates to: 0x0102030405060708 (Little-Endian)
_MAGIC  = b"\x02\x01\x04\x03\x06\x05\x08\x07"   

_TI_VID = 0x0451  # TI's universal USB Vendor ID


class RadarSensor:
    """
    Hardware driver for the Texas Instruments mmWave Radar.
    Owns the two serial COM ports (CLI and DATA), sends the config to the hardware,
    and provides read_raw_frame() which returns one complete binary packet or None.
    """

    def __init__(self, cli_port: str, data_port: str, config_file: str):
        self.config = RadarConfig(config_file)   # Fails fast if the .cfg file is corrupted

        self._cli_port_name  = cli_port    # e.g. "COM3" or "/dev/ttyACM0" (Commands)
        self._data_port_name = data_port   # e.g. "COM4" or "/dev/ttyACM1" (High-speed data)

        self._cli  = None   
        self._data = None   

        self._buffer = bytearray()   # Accumulation buffer for partial USB chunks

    # ── 1. Connection & Flashing ──────────────────────────────────────────────

    def connect_and_configure(self):
        """Opens the physical USB ports and flashes the .cfg file to the radar's DSP."""
        
        # Open the CLI port at 115200 baud (Standard speed for text commands)
        self._cli = serial.Serial(self._cli_port_name, 115200, timeout=0.6)

        # Open the DATA port at 921600 baud (High speed for raw binary matrices)
        self._data = serial.Serial(self._data_port_name, 921600, timeout=1.0)

        # Clear any stale bytes sitting in the DATA port's output buffer from a previous session
        self._data.reset_output_buffer()

        self._send_cfg()

    def _send_cfg(self):
        """Sends the configuration commands line by line."""
        with open(self.config.file_path) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("%")]

        for line in lines:
            # Send the command as an ASCII string with a newline terminator
            self._cli.write((line + "\n").encode())   

            if line.startswith("sensorStop"):
                time.sleep(0.1)                  # Give the DSP time to halt transmission
                self._cli.reset_input_buffer()   # Discard response bytes
                continue                         

            if line.startswith("sensorStart"):
                time.sleep(0.05)                 # Brief pause after boot before reading data
                self._cli.reset_input_buffer()
                continue                         

            # For every other command, wait for the DSP to respond with "Done" before sending the next one
            self._read_until_done()

        self._cli.reset_input_buffer()   

    def _read_until_done(self, timeout: float = 0.3):
        """Polls the CLI port until the radar acknowledges the command with 'Done'."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self._cli.readline().decode(errors="ignore").strip()
            if "Done" in line:
                return   
            if "Error" in line or "Ignored" in line:
                log.warning(f"CFG response: {line}")   
                return

    # ── 2. Frame Extraction ──────────────────────────────────────────────────

    def read_raw_frame(self) -> bytes | None:
        """
        Drains the serial buffer into self._buffer, then extracts one complete
        binary frame. Returns the frame bytes if ready, otherwise None.
        Because USB data arrives in chunks, the main loop calls this continuously.
        """
        in_waiting = self._data.in_waiting   

        if in_waiting > 0:
            # Fast path: grab everything that has arrived without blocking
            self._buffer.extend(self._data.read(in_waiting))
        else:
            # Slow path: blocking read of up to 4096 bytes
            chunk = self._data.read(4096)
            if not chunk:
                return None   
            self._buffer.extend(chunk)

        # ── Desync Recovery ──
        # If a corrupt length value slipped through, the buffer can grow infinitely.
        # At 15 FPS, a normal frame is ~4 KB. Anything over 16 KB is definitely stuck.
        if len(self._buffer) > 16384:
            log.warning("Oversized buffer — flushing to next magic word.")
            # Search from offset 1 so we don't re-find the corrupted sync word at the start
            idx = self._buffer.find(_MAGIC, 1)
            if idx != -1:
                self._buffer = self._buffer[idx:]   
            else:
                # OPTIMIZATION: Overwrite with a brand new array to guarantee memory clearance
                self._buffer = bytearray()   
            return None

        # ── Sync Word Search ──
        idx = self._buffer.find(_MAGIC)   

        if idx == -1:
            # No sync word in the buffer yet. Keep the last 7 bytes because the
            # 8-byte sync word might be split exactly in half across two USB reads.
            if len(self._buffer) > 7:
                self._buffer = self._buffer[-7:]
            return None

        if idx > 0:
            # Drop garbage bytes that arrived before the sync word
            self._buffer = self._buffer[idx:]

        # ── Frame Length Check ──
        if len(self._buffer) < 40:
            return None   # Not enough bytes to read the header yet

        # Bytes 12-15 of the packet header hold the total frame length (Little-Endian uint32)
        frame_len = int.from_bytes(self._buffer[12:16], byteorder="little")

        # Sanity check: Reject impossible sizes (Min = Header size, Max = 16 KB)
        if not (16 <= frame_len <= 16384):
            # False positive sync word — skip past it
            self._buffer = self._buffer[8:]
            return None

        if len(self._buffer) < frame_len:
            return None   # Frame hasn't fully arrived yet

        # ── Extract the complete frame ──
        frame_data   = bytes(self._buffer[:frame_len])   
        self._buffer = self._buffer[frame_len:]          
        return frame_data

    def get_next_frame(self) -> dict | None:
        """Convenience wrapper. Combines read_raw_frame() + parse_standard_frame()."""
        raw = self.read_raw_frame()
        return parse_standard_frame(raw) if raw else None

    # ── 3. Hardware Shutdown ─────────────────────────────────────────────────

    def close(self):
        """Safely shuts down the laser so it doesn't overheat or lock the COM port."""
        if self._cli and self._cli.is_open:
            try:
                self._cli.write(b"sensorStop\n")
                time.sleep(0.1)   
            except Exception as e:
                log.error(f"Failed to send sensorStop: {e}")

        # Release the ports back to the Operating System
        for port in (self._cli, self._data):
            if port and port.is_open:
                port.close()

    # ── 4. USB Auto-Detection ────────────────────────────────────────────────

    @staticmethod
    def find_ti_ports() -> tuple[str | None, str | None]:
        """
        Scans all connected USB serial ports to find the Radar.
        Strategy: Match on string descriptions first, fallback to Vendor ID.
        """
        cli = data = None

        for p in list_ports.comports():
            desc      = p.description or ""
            vid_match = getattr(p, "vid", None) == _TI_VID   

            if "Application/User UART" in desc or "Enhanced COM Port" in desc:
                # Standard ID for the Command Port
                cli = p.device

            elif "Auxiliary Data Port" in desc or "Standard COM Port" in desc:
                # Standard ID for the High-Speed Port
                data = p.device

            elif vid_match:
                # If description strings are missing (common on Linux/Mac), assign by arrival order
                if cli is None:
                    cli = p.device
                elif data is None:
                    data = p.device

        return cli, data