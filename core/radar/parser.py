import math         # Used for ceil() and log2() to calculate FFT padding
import struct       # Used for unpacking raw C-style binary data from the USB stream
import logging      

import numpy as np  # Used for high-speed binary-to-matrix conversion

log = logging.getLogger("RadarParser")

# ─────────────────────────────────────────────────────────────────────────────
#  RadarConfig
#  Reads a TI mmWave .cfg text file and derives every physical radar parameter
#  (range bins, Doppler bins, max velocity, etc.) required by the DSP engine.
# ─────────────────────────────────────────────────────────────────────────────

class RadarConfig:

    def __init__(self, file_path: str):
        self.file_path = file_path   
        self._parse(file_path)       

    def _parse(self, file_path: str):
        with open(file_path) as f:
            # Read every non-blank line that isn't a comment (% = comment in TI syntax)
            lines = [l.split() for l in f if l.strip() and not l.startswith("%")]

        chirp  = {}   # profileCfg values (chirp timing and ADC settings)
        frame  = {}   # frameCfg values (loops, periodicity)
        rx_en  = 0    # RX antenna bitmask (e.g., 15 = 0b1111 = 4 RX antennas enabled)
        tx_en  = 0    # TX antenna bitmask (e.g., 7  = 0b0111 = 3 TX antennas enabled)

        for val in lines:
            if not val:
                continue 

            cmd = val[0] # The command name (e.g., 'profileCfg')

            if cmd == "channelCfg":
                rx_en = int(val[1])  
                tx_en = int(val[2])  

            elif cmd == "profileCfg":
                if int(val[1]) == 0:  # Only parse profile ID 0
                    chirp = {
                        "startFreq":     float(val[2]),    # Carrier frequency in GHz (usually 60 or 77)
                        "idleTime":      float(val[3]),    # Dead time between chirps in microseconds
                        "rampEndTime":   float(val[5]),    # Total chirp sweep duration in microseconds
                        "freqSlope":     float(val[8]),    # How fast the frequency ramps in MHz/us
                        "numADCsamples": int(val[10]),     # I/Q samples collected per chirp
                        "sampleRate":    float(val[11]),   # ADC sampling rate in ksps
                    }

            elif cmd == "frameCfg":
                frame = {
                    "chirpStartInd": int(val[1]),   # Index of first chirp 
                    "chirpEndInd":   int(val[2]),   # Index of last chirp 
                    "numLoops":      int(val[3]),   # Number of times the chirp repeats = Doppler velocity bins
                    "periodicity":   int(val[5]),   # Frame interval in milliseconds (controls FPS)
                }

        # Guard: Ensure the file wasn't empty or corrupted
        if not chirp:
            raise ValueError(f"No profileCfg (profile 0) found in {file_path}")
        if not frame:
            raise ValueError(f"No frameCfg found in {file_path}")

        # Count the 1-bits in the bitmask to figure out how many physical antennas are active
        self.rxAntennas = bin(rx_en).count("1")  
        self.txAntennas = bin(tx_en).count("1")  

        self.ADCsamples = chirp["numADCsamples"] 

        # The FFT algorithm requires arrays to be a perfect power of two (64, 128, 256).
        # If the ADC samples are 100, this math bumps it up to 128 (padding the rest with zeros).
        self.numRangeBins = 1 if self.ADCsamples == 0 else 2 ** math.ceil(math.log2(self.ADCsamples))

        # Bandwidth Formula: freqSlope * (ADCsamples / sampleRate)
        self.BW = chirp["freqSlope"] * self.ADCsamples / chirp["sampleRate"] * 1e9

        # Range Resolution: Speed of Light / (2 * Bandwidth)
        self.rangeRes = 3e8 / (2 * self.BW)

        # Maximum Range
        self.rangeMax = self.rangeRes * self.numRangeBins

        chirps_per_loop = frame["chirpEndInd"] - frame["chirpStartInd"] + 1

        self.numLoops = frame["numLoops"]                   
        numChirps     = chirps_per_loop * self.numLoops     

        # Total time for one chirp (idle + ramp), converted to seconds
        Tc = (chirp["idleTime"] + chirp["rampEndTime"]) * 1e-6

        # Carrier frequency in Hz
        fc = chirp["startFreq"] * 1e9

        # Doppler Resolution Formula: Speed of light / (2 * CarrierFreq * ChirpTime * TotalChirps)
        self.dopRes = 3e8 / (2 * fc * Tc * numChirps)

        # Maximum unambiguous velocity (Beyond this, the runner's speed will alias/wrap around)
        self.dopMax = numChirps * self.dopRes / 2

        self.T         = frame["periodicity"]   # Frame period in milliseconds
        self.frameRate = 1e3 / self.T           # Frames per second (FPS)

    def summary(self) -> dict:
        """Returns a clean summary dictionary for the UI console."""
        return {
            "TX / RX antennas":   f"{self.txAntennas} / {self.rxAntennas}",
            "Bandwidth":          f"{self.BW / 1e9:.3f} GHz",
            "Range resolution":   f"{self.rangeRes * 100:.2f} cm",
            "Range max":          f"{self.rangeMax:.2f} m",
            "Range FFT Bins":     f"{self.numRangeBins}",
            "Doppler resolution": f"{self.dopRes:.3f} m/s",
            "Max velocity":       f"±{self.dopMax:.2f} m/s",
            "Frame rate":         f"{self.frameRate:.1f} Hz ({self.T:.0f} ms)",
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Frame Parser (Binary Unpacker)
# ─────────────────────────────────────────────────────────────────────────────

# TI designates TLV Type 5 as the Range-Doppler Heat Map
TLV_RANGE_DOPPLER_HEAT_MAP = 5

# Packet header format string for struct.unpack:
#   <  = little-endian (Intel/TI architecture)
#   Q  = uint64 (Magic sync word)
#   8I = eight uint32s (Packet length, frame number, TLV count, etc.)
_HEADER_FMT = "<Q8I"
_HEADER_LEN = struct.calcsize(_HEADER_FMT)   # Always exactly 40 bytes

_TLV_HDR_LEN = 8   # Every TLV block starts with [Type: 4 bytes] and [Length: 4 bytes]


def parse_standard_frame(data: bytes) -> dict:
    """
    Sifts through a raw binary stream to find and extract the Range-Doppler matrix.
    """
    out = {"error": 0, "RDHM": None}

    # Reject packets that are physically too small to even be a header
    if len(data) < _HEADER_LEN:
        out["error"] = 1
        return out

    try:
        # Unpack the 40-byte header
        header   = struct.unpack(_HEADER_FMT, data[:_HEADER_LEN])
        num_tlvs = header[7]   # Field 7 tells us how many TLV blocks are attached
    except struct.error:
        # Corrupted header
        out["error"] = 1
        return out

    # Slice the header off the data, leaving only the TLV blocks
    data = data[_HEADER_LEN:]

    for _ in range(num_tlvs):
        # Prevent crashes if the network dropped the end of the packet
        if len(data) < _TLV_HDR_LEN:
            break 

        # Unpack the 8-byte TLV header to find out what type of data this block holds
        tlv_type, tlv_len = struct.unpack("<2I", data[:_TLV_HDR_LEN])
        
        # Advance the pointer past the TLV header to the actual payload
        data = data[_TLV_HDR_LEN:] 

        if len(data) < tlv_len:
            break 

        # If it's Type 5, we found the Heatmap!
        if tlv_type == TLV_RANGE_DOPPLER_HEAT_MAP:
            try:
                # Convert the raw bytes into unsigned 16-bit integers.
                # .copy() is critical here! It detaches the matrix from the massive raw memory buffer,
                # allowing Python's Garbage Collector to safely delete the raw buffer to prevent RAM leaks.
                out["RDHM"] = np.frombuffer(data[:tlv_len], dtype=np.uint16).copy()
            except Exception as e:
                log.error("RDHM parse failed: %s", e)

            # We found what we need, stop searching this packet to save CPU time
            break

        # If it wasn't Type 5, slice off the payload and loop back around to check the next TLV block
        data = data[tlv_len:]

    return out