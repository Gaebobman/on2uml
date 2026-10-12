"""Turn .puml source into an image with a local PlantUML (no remote server)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _command(jar: str | None) -> list[str]:
    jar = jar or os.environ.get("PLANTUML_JAR")
    if jar:
        return ["java", "-DPLANTUML_LIMIT_SIZE=16384", "-jar", jar]
    exe = shutil.which("plantuml")
    if exe:
        return [exe]
    raise RuntimeError(
        "PlantUML not found: pass --plantuml-jar, set PLANTUML_JAR, or put `plantuml` on PATH"
    )


def render(puml_path: Path, fmt: str, jar: str | None = None) -> Path:
    cmd = [*_command(jar), f"-t{fmt}", "-charset", "UTF-8", "-failfast2", str(puml_path)]
    env = {**os.environ, "PLANTUML_LIMIT_SIZE": "16384"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    out = puml_path.with_suffix(f".{fmt}")
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"PlantUML failed ({proc.returncode}):\n{proc.stderr or proc.stdout}")
    return out


def render_many(puml_paths: list[Path], fmt: str, jar: str | None = None) -> None:
    """Render many .puml files with a single JVM start (much faster than one call each)."""
    if not puml_paths:
        return
    for p in puml_paths:
        p.with_suffix(f".{fmt}").unlink(missing_ok=True)
    cmd = [*_command(jar), f"-t{fmt}", "-charset", "UTF-8", "-nbthread", "auto", *map(str, puml_paths)]
    env = {**os.environ, "PLANTUML_LIMIT_SIZE": "16384"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    missing = [p.name for p in puml_paths if not p.with_suffix(f".{fmt}").exists()]
    if proc.returncode != 0 or missing:
        detail = f"missing: {', '.join(missing[:10])}" if missing else ""
        raise RuntimeError(f"PlantUML failed ({proc.returncode}) {detail}\n{proc.stderr or proc.stdout}")
