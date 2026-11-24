#!/usr/bin/env python3
"""Read a secret from the macOS Keychain (never from files or chat).
Owner stores them once:  security add-generic-password -a studio -s <name> -w   (prompts; nothing is shown)
Names: studio-elevenlabs (ElevenLabs API key) · studio-gmail (Gmail app password for the sending account)"""
import subprocess, sys


def get(name):
    r = subprocess.run(["security", "find-generic-password", "-a", "studio", "-s", name, "-w"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


if __name__ == "__main__":
    print("set" if get(sys.argv[1]) else "missing")
