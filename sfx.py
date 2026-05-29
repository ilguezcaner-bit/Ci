import subprocess
import os
from pathlib import Path

SFX_DIR = Path("sfx_cache")
SFX_DIR.mkdir(exist_ok=True)

# (lavfi_source, af_filter_chain)
_DEFS = {
    "swoosh": (
        "anoisesrc=d=0.6:c=white:a=1.0",
        "afade=t=in:st=0:d=0.03,afade=t=out:st=0.45:d=0.15,"
        "bandpass=f=2800:width_type=o:w=2.0,volume=3.0",
    ),
    "whoosh": (
        "anoisesrc=d=1.0:c=white:a=0.8",
        "afade=t=in:st=0:d=0.1,afade=t=out:st=0.8:d=0.2,"
        "lowpass=f=700,highpass=f=90,volume=2.5",
    ),
    "wind": (
        "anoisesrc=d=1.8:c=white:a=0.5",
        "afade=t=in:st=0:d=0.4,afade=t=out:st=1.4:d=0.4,"
        "lowpass=f=350,highpass=f=40,volume=1.8",
    ),
    "flash": (
        "sine=f=80:d=0.35",
        "afade=t=out:st=0:d=0.35,volume=4",
    ),
    "cinematic": (
        "sine=f=110:d=0.65",
        "afade=t=in:st=0:d=0.04,afade=t=out:st=0.45:d=0.2,"
        "aecho=0.8:0.7:80:0.5,volume=3",
    ),
    "sparkle": (
        "anoisesrc=d=0.5:c=white:a=0.4",
        "highpass=f=6000,afade=t=in:st=0:d=0.02,afade=t=out:st=0.35:d=0.15,volume=2.5",
    ),
    "film_click": (
        "anoisesrc=d=0.25:c=white:a=1.0",
        "afade=t=out:st=0:d=0.25,bandpass=f=800:width_type=o:w=1.5,volume=3.5",
    ),
    "air": (
        "anoisesrc=d=0.7:c=white:a=0.6",
        "afade=t=in:st=0:d=0.08,afade=t=out:st=0.5:d=0.2,"
        "bandpass=f=3500:width_type=o:w=3.0,volume=2.5",
    ),
    "impact": (
        "anoisesrc=d=0.45:c=white:a=1.0",
        "afade=t=out:st=0:d=0.45,lowpass=f=220,volume=5",
    ),
    "zap": (
        "anoisesrc=d=0.3:c=white:a=1.0",
        "afade=t=out:st=0:d=0.3,highpass=f=3000,lowpass=f=9000,volume=4",
    ),
}


def get_sfx_path(name: str) -> str:
    path = SFX_DIR / f"{name}.wav"
    if not path.exists():
        _generate(name, str(path))
    return str(path)


def _generate(name: str, output: str) -> None:
    src, af = _DEFS[name]
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", src, "-af", af, output]
    subprocess.run(cmd, capture_output=True, check=True)


def available() -> list:
    return list(_DEFS.keys())
