import math        # for ceil() and log2() used in FFT bin padding
import struct       # for unpacking binary data from the radar's USB stream
import logging      # standard Python logging — errors go here instead of crashing

import numpy as np  # numpy for the uint16 frombuffer call in the parser

log = logging.getLogger(__name__)  # module-level logger, name = "core"

# ─────────────────────────────────────────────────────────────────────────────
#  RadarConfig
#  Reads a TI mmWave .cfg text file and derives every physical radar parameter
#  the rest of the pipeline needs (range bins, Doppler bins, max velocity, etc.)
# ─────────────────────────────────────────────────────────────────────────────

class RadarConfig:

    def __init__(self, file_path: str):
        self.file_path = file_path   # keep the path so sensor.py can re-open it when sending the cfg to hardware
        self._parse(file_path)       # parse immediately on construction — object is ready to use after __init__

    def _parse(self, file_path: str):
        with open(file_path) as f:
            # Read every non-blank line that isn't a comment (% = comment in TI cfg files)
            # Split each line into tokens so val[0] is the command name and val[1..] are its arguments
            lines = [l.split() for l in f if l.strip() and not l.startswith("%")]

        chirp  = {}   # will hold the profileCfg values (chirp timing and ADC settings)
        frame  = {}   # will hold the frameCfg values (loops, periodicity)
        rx_en  = 0    # RX antenna bitmask — e.g. 15 = 0b1111 = 4 RX antennas enabled
        tx_en  = 0    # TX antenna bitmask — e.g. 7  = 0b0111 = 3 TX antennas enabled

        for val in lines:
            if not val:
                continue          # skip any line that came out empty after splitting

            cmd = val[0]          # first token is always the command name

            if cmd == "channelCfg":
                rx_en = int(val[1])   # second token: which RX antennas are on (bitmask)
                tx_en = int(val[2])   # third token:  which TX antennas are on (bitmask)

            elif cmd == "profileCfg":
                if int(val[1]) == 0:  # only parse profile ID 0 — we only use one profile
                    chirp = {
                        "startFreq":     float(val[2]),    # carrier frequency in GHz (60 GHz for this sensor)
                        "idleTime":      float(val[3]),    # dead time between chirps in microseconds
                        "rampEndTime":   float(val[5]),    # total chirp sweep duration in microseconds
                        "freqSlope":     float(val[8]),    # how fast the frequency ramps in MHz/us
                        "numADCsamples": int(val[10]),     # how many I/Q samples are collected per chirp
                        "sampleRate":    float(val[11]),   # ADC sampling rate in ksps (kilo-samples/sec)
                    }

            elif cmd == "frameCfg":
                frame = {
                    "chirpStartInd": int(val[1]),   # index of first chirp in the sequence (usually 0)
                    "chirpEndInd":   int(val[2]),   # index of last chirp (e.g. 2 means 3 chirps: 0,1,2)
                    "numLoops":      int(val[3]),   # how many times that chirp sequence repeats per frame = Doppler bins
                    "periodicity":   int(val[5]),   # frame interval in milliseconds — controls FPS
                }

        # Guard: if the file didn't contain the required commands, fail loudly now rather than
        # producing silent wrong results later in the pipeline
        if not chirp:
            raise ValueError(f"No profileCfg (profile 0) found in {file_path}")
        if not frame:
            raise ValueError(f"No frameCfg found in {file_path}")

        # Count how many 1-bits are in each antenna bitmask to get the antenna counts
        self.rxAntennas = bin(rx_en).count("1")   # e.g. bin(15) = '0b1111' → 4 RX antennas
        self.txAntennas = bin(tx_en).count("1")   # e.g. bin(7)  = '0b0111' → 3 TX antennas

        self.ADCsamples = chirp["numADCsamples"]  # raw ADC sample count (64 in this config)

        # The range FFT must be a power of two for efficiency.
        # math.ceil(log2(N)) gives the exponent of the next power of two >= N.
        # e.g. ADCsamples=64 → log2(64)=6 → 2^6=64 (already a power of two, no padding needed)
        # e.g. ADCsamples=100 → ceil(log2(100))=7 → 2^7=128 (padded up to 128)
        self.numRangeBins = 1 if self.ADCsamples == 0 else 2 ** math.ceil(math.log2(self.ADCsamples))

        # Bandwidth = how far the frequency sweeps during the ADC collection window
        # freqSlope (MHz/us) × ADCsamples / sampleRate (ksps) gives time in us, ×1e9 converts to Hz
        self.BW = chirp["freqSlope"] * self.ADCsamples / chirp["sampleRate"] * 1e9

        # Range resolution: the minimum distance between two distinguishable targets
        # Derived from: c / (2 × BW) where c = speed of light
        self.rangeRes = 3e8 / (2 * self.BW)

        # Maximum unambiguous range: how far out the range axis goes
        # Uses numRangeBins (padded FFT size) not raw ADCsamples to match what the DSP actually outputs
        self.rangeMax = self.rangeRes * self.numRangeBins

        # chirps_per_loop: how many distinct TX chirps fire in one loop iteration (3 for TDM-MIMO with 3 TX)
        chirps_per_loop = frame["chirpEndInd"] - frame["chirpStartInd"] + 1

        self.numLoops = frame["numLoops"]                   # Doppler velocity bins = number of loops per frame (32)
        numChirps     = chirps_per_loop * self.numLoops     # total chirps per frame = 3 × 32 = 96

        # Tc: total time for one chirp (idle + ramp), converted from microseconds to seconds
        Tc = (chirp["idleTime"] + chirp["rampEndTime"]) * 1e-6

        # fc: carrier frequency in Hz (60 GHz → 60e9 Hz)
        fc = chirp["startFreq"] * 1e9

        # Doppler resolution: how small a velocity difference can be detected
        # Derived from: c / (2 × fc × Tc × numChirps)
        self.dopRes = 3e8 / (2 * fc * Tc * numChirps)

        # Maximum unambiguous velocity (±dopMax): beyond this, velocities alias (wrap around)
        # Uses the full numChirps count (not just numLoops) for correct scaling
        self.dopMax = numChirps * self.dopRes / 2

        self.T         = frame["periodicity"]   # frame period in milliseconds (66 ms)
        self.frameRate = 1e3 / self.T           # frames per second = 1000 / 66 ≈ 15.1 FPS

    def summary(self) -> dict:
        # Returns a human-readable dict printed in the terminal on startup
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
#  Frame parser
#  The radar sends binary packets over USB. Each packet has:
#    1. A fixed-length header  (40 bytes, format "<Q8I")
#    2. One or more TLV blocks (Type-Length-Value), each with an 8-byte header
#       followed by `length` bytes of payload
#  We only care about TLV type 5 = Range-Doppler Heat Map (RDHM).
# ─────────────────────────────────────────────────────────────────────────────

# TLV type 5 is the Range-Doppler Heat Map — the 2D matrix we visualise
TLV_RANGE_DOPPLER_HEAT_MAP = 5

# Packet header format string for struct.unpack:
#   < = little-endian (TI uses little-endian throughout)
#   Q = uint64 (8 bytes) — the magic sync word
#   8I = eight uint32s (32 bytes) — version, totalPacketLen, platform, frameNum,
#        timeCpuCycles, numDetectedObj, numTLVs, subFrameNum
_HEADER_FMT = "<Q8I"
_HEADER_LEN = struct.calcsize(_HEADER_FMT)   # = 40 bytes total

_TLV_HDR_LEN = 8   # every TLV starts with two uint32s: type (4 bytes) + length (4 bytes)


def parse_standard_frame(data: bytes) -> dict:
    # Start with a clean result — RDHM stays None if we never find TLV type 5
    out = {"error": 0, "RDHM": None}

    # Reject packets that are too short to even contain a header
    if len(data) < _HEADER_LEN:
        out["error"] = 1
        return out

    try:
        # Unpack the 40-byte header into 9 fields
        header   = struct.unpack(_HEADER_FMT, data[:_HEADER_LEN])
        num_tlvs = header[7]   # field index 7 = numTLVs — how many TLV blocks follow the header
    except struct.error:
        # struct.unpack raises if the byte count doesn't match — treat as corrupt
        out["error"] = 1
        return out

    # Advance past the header so `data` now points at the first TLV
    data = data[_HEADER_LEN:]

    for _ in range(num_tlvs):
        # Each TLV starts with an 8-byte mini-header: [type: uint32][length: uint32]
        if len(data) < _TLV_HDR_LEN:
            break   # truncated packet — stop safely

        tlv_type, tlv_len = struct.unpack("<2I", data[:_TLV_HDR_LEN])
        data = data[_TLV_HDR_LEN:]   # advance past the TLV header to the payload

        if len(data) < tlv_len:
            break   # payload is shorter than declared — corrupt, stop safely

        if tlv_type == TLV_RANGE_DOPPLER_HEAT_MAP:
            try:
                # Interpret the raw payload bytes as a flat array of uint16 values.
                # data[:tlv_len] ensures we only consume exactly the declared bytes.
                # .copy() detaches the array from the original buffer so it's safe to hold
                out["RDHM"] = np.frombuffer(data[:tlv_len], dtype=np.uint16).copy()
            except Exception as e:
                log.error("RDHM parse failed: %s", e)

            # We only need TLV 5 — no point scanning the rest of the packet
            break

        # Not the TLV we want — skip over its payload and check the next one
        data = data[tlv_len:]

    return out