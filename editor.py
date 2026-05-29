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
    has_audio = any(s["codec_type"] == "audio" for s in data.get("streams", []))
    return {"duration": duration, "path": path, "has_audio": has_audio}


def process_segment(
    input_path: str,
    start: Optional[float],
    end: Optional[float],
    rotate: Optional[int],
    output_path: str,
) -> None:
    """Trim and/or rotate a clip segment. rotate: -90=left, 90=right, 180=flip."""
    # transpose: 1=90°CW(right), 2=90°CCW(left)
    transpose_map = {-90: ["2"], 90: ["1"], 180: ["2", "2"]}
    needs_encode = rotate is not None

    cmd = ["ffmpeg", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", input_path]
    if end is not None:
        cmd += ["-t", str(end - start) if start is not None else str(end)]

    if needs_encode:
        transposes = transpose_map.get(rotate, ["2"])
        vf = ",".join(f"transpose={t}" for t in transposes)
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "copy"]
    else:
        cmd += ["-c", "copy"]

    cmd.append(output_path)
    subprocess.run(cmd, capture_output=True, check=True)


def concat_with_transitions(segments: list, output_path: str) -> None:
    """
    segments: list of {path, transition_in, transition_duration}
    transition_in: 'crossfade' | 'fadeblack' | None
    transition_duration: float seconds
    """
    n = len(segments)
    if n == 1:
        shutil.copy(segments[0]["path"], output_path)
        return

    has_any_transition = any(s.get("transition_in") for s in segments[1:])
    durations = [get_clip_info(s["path"])["duration"] for s in segments]

    inputs = []
    for s in segments:
        inputs += ["-i", s["path"]]

    if not has_any_transition:
        # Simple re-encode concat
        parts = "".join(f"[{i}:v][{i}:a]" for i in range(n))
        fc = f"{parts}concat=n={n}:v=1:a=1[vout][aout]"
        cmd = [
            "ffmpeg", "-y", *inputs,
            "-filter_complex", fc,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return

    # Build chained xfade / concat filter
    fv, fa = [], []
    cur_v, cur_a = "[0:v]", "[0:a]"
    cur_dur = durations[0]

    for i in range(1, n):
        is_last = (i == n - 1)
        out_v = "[vout]" if is_last else f"[v{i}]"
        out_a = "[aout]" if is_last else f"[a{i}]"
        t_type = segments[i].get("transition_in")
        t_dur = float(segments[i].get("transition_duration") or 1.0)

        # "crossfade" is our alias for ffmpeg's "fade" effect
        ALIAS = {"crossfade": "fade"}
        if t_type:
            xfade_name = ALIAS.get(t_type, t_type)
            offset = max(0.0, cur_dur - t_dur)
            fv.append(f"{cur_v}[{i}:v]xfade=transition={xfade_name}:duration={t_dur}:offset={offset:.4f}{out_v}")
            fa.append(f"{cur_a}[{i}:a]acrossfade=d={t_dur}{out_a}")
            cur_dur += durations[i] - t_dur
        else:  # hard cut
            fv.append(f"{cur_v}[{i}:v]concat=n=2:v=1:a=0{out_v}")
            fa.append(f"{cur_a}[{i}:a]concat=n=2:v=0:a=1{out_a}")
            cur_dur += durations[i]

        cur_v, cur_a = out_v, out_a

    fc = ";".join(fv + fa)
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac",
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
                raise ValueError(f"Clip '{clip_name}' nicht gefunden. Verfügbar: {list(clip_map.keys())}")

            src = clip_map[clip_name]
            start = step.get("start")
            end = step.get("end")
            rotate = step.get("rotate")
            out = os.path.join(tmp_dir, f"segment_{i}.mp4")

            if start is not None or end is not None or rotate:
                process_segment(src, start, end, rotate, out)
                seg_path = out
            else:
                seg_path = src

            segments.append({
                "path": seg_path,
                "transition_in": step.get("transition_in"),
                "transition_duration": step.get("transition_duration"),
            })

        concat_with_transitions(segments, output_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
