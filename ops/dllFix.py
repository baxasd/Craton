# Fix for DLL conflict
import sys

try:
    import mediapipe
    from mediapipe.python import _framework_bindings

    print("HOOK: MediaPipe loaded successfully.")
except ImportError as e:
    print(f"HOOK: Failed to load MediaPipe: {e}")
