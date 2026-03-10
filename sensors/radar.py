import time                          # for sleep() during config sending and close()
import logging                       # for warning/error messages without crashing
import serial                        # pyserial — talks to the radar over USB-UART
from serial.tools import list_ports  # used by find_ti_ports() to scan connected USB devices

from core.radar.base import RadarConfig, parse_standard_frame   # our merged config + parser module

log = logging.getLogger(__name__)   # module-level logger, name = "sensor"

_MAGIC  = b"\x02\x01\x04\x03\x06\x05\x08\x07"   # 8-byte sync word that starts every radar packet
_TI_VID = 0x0451                                  # TI's USB Vendor ID — used to identify the device


class RadarSensor:
    """
    Owns the two serial ports (CLI and DATA), sends the config to the hardware,
    and provides read_raw_frame() which returns one complete binary packet or None.
    """

    def __init__(self, cli_port: str, data_port: str, config_file: str):
        self.config = RadarConfig(config_file)   # parse the .cfg file immediately — fails fast if the file is bad

        self._cli_port_name  = cli_port    # e.g. "/dev/ttyACM0" — the command port
        self._data_port_name = data_port   # e.g. "/dev/ttyACM1" — the high-speed data port

        self._cli  = None   # serial.Serial object for the CLI port, opened later in connect_and_configure()
        self._data = None   # serial.Serial object for the DATA port, opened later

        self._buffer = bytearray()   # accumulation buffer — bytes arrive in chunks, frames span multiple reads

    # ── Connection ────────────────────────────────────────────────────────────

    def connect_and_configure(self):
        # Open the CLI port at 115200 baud — this is the command/response channel
        self._cli = serial.Serial(self._cli_port_name, 115200, timeout=0.6)

        # Open the DATA port at 921600 baud — this is the high-speed binary data channel
        self._data = serial.Serial(self._data_port_name, 921600, timeout=1.0)

        # Clear any stale bytes sitting in the DATA port's output buffer from a previous session
        self._data.reset_output_buffer()

        # Send the .cfg file line by line to the radar's DSP over the CLI port
        self._send_cfg()

    def _send_cfg(self):
        with open(self.config.file_path) as f:
            # Read all non-blank, non-comment lines — these are the commands to send
            lines = [l.strip() for l in f if l.strip() and not l.startswith("%")]

        for line in lines:
            self._cli.write((line + "\n").encode())   # send the command as ASCII with a newline terminator

            if line.startswith("sensorStop"):
                time.sleep(0.1)                  # give the DSP time to actually stop before we continue
                self._cli.reset_input_buffer()   # discard any response bytes — we don't need them here
                continue                         # no "Done" acknowledgement expected for sensorStop

            if line.startswith("sensorStart"):
                time.sleep(0.05)                 # brief pause after start before we begin reading data
                self._cli.reset_input_buffer()
                continue                         # no "Done" acknowledgement expected for sensorStart

            # For every other command, wait for the DSP to respond with "Done" before sending the next one
            self._read_until_done()

        self._cli.reset_input_buffer()   # final flush — discard any trailing response bytes

    def _read_until_done(self, timeout: float = 0.3):
        # Poll the CLI port until we see "Done" (success) or an error keyword, or the timeout expires
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self._cli.readline().decode(errors="ignore").strip()   # read one line; ignore non-ASCII bytes
            if "Done" in line:
                return   # DSP acknowledged the command — move on to the next line
            if "Error" in line or "Ignored" in line:
                log.warning("CFG response: %s", line)   # log but don't crash — some commands are advisory
                return

    # ── Frame reading ─────────────────────────────────────────────────────────

    def read_raw_frame(self) -> bytes | None:
        """
        Drain the serial buffer into self._buffer, then try to extract one complete
        binary frame.  Returns the frame bytes if a full frame is ready, otherwise None.
        The caller should loop calling this until it gets a non-None result.
        """

        in_waiting = self._data.in_waiting   # how many bytes are sitting unread in the OS serial buffer

        if in_waiting > 0:
            # Fast path: grab everything that's already arrived without blocking
            self._buffer.extend(self._data.read(in_waiting))
        else:
            # Slow path: no bytes ready yet — do a blocking read of up to 4096 bytes
            # This will block for up to serial timeout (1.0s) if nothing arrives
            chunk = self._data.read(4096)
            if not chunk:
                return None   # timeout expired with no data — tell the caller to try again
            self._buffer.extend(chunk)

        # ── Desync recovery ───────────────────────────────────────────────────
        # If a corrupt frame_len value slipped through, the buffer can grow forever
        # because we never consume enough bytes to reach the next magic word.
        # At 15 FPS a normal frame is ~4 KB; anything over 16 KB is definitely stuck.
        if len(self._buffer) > 16384:
            log.warning("Oversized buffer — flushing to next magic word.")
            # Search from offset 1 (not 0, not 8) so we don't re-find the corrupted
            # sync word at the start, but also don't skip a valid one at bytes 1-7
            idx = self._buffer.find(_MAGIC, 1)
            if idx != -1:
                self._buffer = self._buffer[idx:]   # jump forward to the next valid sync word
            else:
                self._buffer.clear()   # no valid sync word found anywhere — wipe and start fresh
            return None

        # ── Sync word search ──────────────────────────────────────────────────
        idx = self._buffer.find(_MAGIC)   # find the start of the next valid packet

        if idx == -1:
            # No sync word in the buffer yet — keep the last 7 bytes because the
            # sync word might be split across two reads (8 bytes, might overlap boundary)
            if len(self._buffer) > 7:
                self._buffer = self._buffer[-7:]
            return None

        if idx > 0:
            # Garbage bytes before the sync word — discard them
            self._buffer = self._buffer[idx:]

        # ── Frame length check ────────────────────────────────────────────────
        if len(self._buffer) < 40:
            return None   # not enough bytes to read the header yet — wait for more data

        # Bytes 12-15 of the packet header hold the total frame length as a little-endian uint32
        frame_len = int.from_bytes(self._buffer[12:16], byteorder="little")

        # Sanity check: reject lengths that are physically impossible for this radar profile
        # (minimum = bare header, maximum = 16 KB which is well above any real frame)
        if not (16 <= frame_len <= 16384):
            # This sync word was a false positive — skip past it and try again next call
            self._buffer = self._buffer[8:]
            return None

        if len(self._buffer) < frame_len:
            return None   # frame hasn't fully arrived yet — wait for more bytes

        # ── Extract the complete frame ────────────────────────────────────────
        frame_data   = bytes(self._buffer[:frame_len])   # copy out exactly frame_len bytes
        self._buffer = self._buffer[frame_len:]          # advance the buffer past this frame
        return frame_data

    # ── Convenience wrapper (unused by viewer but kept for external callers) ──

    def get_next_frame(self) -> dict | None:
        # Combines read_raw_frame() + parse_standard_frame() into one call
        raw = self.read_raw_frame()
        return parse_standard_frame(raw) if raw else None

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def close(self):
        if self._cli and self._cli.is_open:
            try:
                # Tell the DSP to stop chirping before we close the port.
                # If we close without this, the radar keeps transmitting and
                # the next session may see stale data in the UART buffer.
                self._cli.write(b"sensorStop\n")
                time.sleep(0.1)   # give the DSP time to process the stop command
            except Exception as e:
                log.error("Failed to send sensorStop: %s", e)

        # Close both ports cleanly regardless of whether sensorStop succeeded
        for port in (self._cli, self._data):
            if port and port.is_open:
                port.close()

    # ── Port auto-detection ───────────────────────────────────────────────────

    @staticmethod
    def find_ti_ports() -> tuple[str | None, str | None]:
        """
        Scan all connected serial ports and return (cli_port, data_port).
        Strategy: match on USB description strings first (most reliable),
        fall back to TI Vendor ID (0x0451) + arrival order if descriptions are absent.
        """
        cli = data = None

        for p in list_ports.comports():
            desc      = p.description or ""
            vid_match = getattr(p, "vid", None) == _TI_VID   # True if this port belongs to a TI device

            if "Application/User UART" in desc or "Enhanced COM Port" in desc:
                # This description string is how the CLI port identifies itself on most systems
                cli = p.device

            elif "Auxiliary Data Port" in desc or "Standard COM Port" in desc:
                # This description string is how the DATA port identifies itself
                data = p.device

            elif vid_match:
                # No description match but it's a TI device — assign by arrival order
                # First port seen → CLI, second → DATA (matches physical enumeration order)
                if cli is None:
                    cli = p.device
                elif data is None:
                    data = p.device

        return cli, data