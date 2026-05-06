import subprocess
import json
import os
import tempfile
from pathlib import Path


def get_clip_info(path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    duration = float(data["format"].get("duration", 0))
    return {"duration": duration, "path": path}


def trim_clip(input_path: str, start: float | None, end: float | None, output_path: str) -> None:
    cmd = ["ffmpeg", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", input_path]
    if end is not None:
        if start is not None:
            cmd += ["-t", str(end - start)]
        else:
            cmd += ["-to", str(end)]
    cmd += ["-c", "copy", output_path]
    subprocess.run(cmd, capture_output=True, check=True)


def concat_clips(clip_paths: list[str], output_path: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
        list_file = f.name
    try:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)
    finally:
        os.unlink(list_file)


def process_edit_plan(plan: dict, clip_map: dict[str, str], output_path: str) -> None:
    """Execute an edit plan. clip_map maps clip name → file path."""
    steps = plan["steps"]
    tmp_dir = tempfile.mkdtemp()
    trimmed = []

    try:
        for i, step in enumerate(steps):
            clip_name = step["clip"]
            if clip_name not in clip_map:
                raise ValueError(f"Clip '{clip_name}' not found. Available: {list(clip_map.keys())}")

            src = clip_map[clip_name]
            start = step.get("start")
            end = step.get("end")
            out = os.path.join(tmp_dir, f"segment_{i}.mp4")

            if start is None and end is None:
                trimmed.append(src)
            else:
                trim_clip(src, start, end, out)
                trimmed.append(out)

        if len(trimmed) == 1:
            import shutil
            shutil.copy(trimmed[0], output_path)
        else:
            concat_clips(trimmed, output_path)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
