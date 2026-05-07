import subprocess
import json
import os
import shutil
import tempfile
from typing import Optional


def get_clip_info(path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    duration = float(data["format"].get("duration", 0))
    return {"duration": duration, "path": path}


def process_segment(
    input_path: str,
    start: Optional[float],
    end: Optional[float],
    rotate: Optional[int],
    output_path: str,
) -> None:
    """Trim and/or rotate a single segment. rotate: -90 = left, 90 = right, 180 = flip."""
    # transpose values: 2 = 90° counter-clockwise (left), 1 = 90° clockwise (right)
    transpose_map = {-90: "2", 90: "1", 180: "2,transpose=2"}

    needs_encode = rotate is not None

    cmd = ["ffmpeg", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", input_path]
    if end is not None:
        if start is not None:
            cmd += ["-t", str(end - start)]
        else:
            cmd += ["-to", str(end)]

    if needs_encode:
        vf = ",".join(f"transpose={t}" for t in transpose_map.get(rotate, "2").split(","))
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "copy"]
    else:
        cmd += ["-c", "copy"]

    cmd.append(output_path)
    subprocess.run(cmd, capture_output=True, check=True)


def concat_clips(clip_paths: list, output_path: str) -> None:
    # Re-encode for concat to ensure uniform stream parameters after possible rotation
    inputs = []
    filter_parts = []
    for i, p in enumerate(clip_paths):
        inputs += ["-i", p]
        filter_parts.append(f"[{i}:v][{i}:a]")

    filter_complex = "".join(filter_parts) + f"concat=n={len(clip_paths)}:v=1:a=1[vout][aout]"
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def process_edit_plan(plan: dict, clip_map: dict, output_path: str) -> None:
    steps = plan["steps"]
    tmp_dir = tempfile.mkdtemp()
    segments = []

    try:
        for i, step in enumerate(steps):
            clip_name = step["clip"]
            if clip_name not in clip_map:
                raise ValueError(f"Clip '{clip_name}' not found. Available: {list(clip_map.keys())}")

            src = clip_map[clip_name]
            start = step.get("start")
            end = step.get("end")
            rotate = step.get("rotate")  # -90, 90, or 180
            out = os.path.join(tmp_dir, f"segment_{i}.mp4")

            needs_processing = start is not None or end is not None or rotate is not None
            if needs_processing:
                process_segment(src, start, end, rotate, out)
                segments.append(out)
            else:
                segments.append(src)

        if len(segments) == 1:
            shutil.copy(segments[0], output_path)
        else:
            concat_clips(segments, output_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
