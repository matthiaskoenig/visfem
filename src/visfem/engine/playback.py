"""Async background coroutines: vtk.js warmup, step preloading, and autoplay."""
import asyncio
import math
from pathlib import Path
from typing import Any

import pyvista as pv

from visfem.engine.selection import select_step
from visfem.log import get_logger
from visfem.mesh import load_mesh
from visfem.models import MeshMetadata, ProjectMetadata

logger = get_logger(__name__)


async def preload_steps(path: Path, steps: list[int]) -> None:
    """Load mesh steps into the LRU cache in the background without blocking the UI."""
    loop = asyncio.get_running_loop()
    for step in steps:
        try:
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        try:
            await loop.run_in_executor(None, load_mesh, path, step)
        except Exception:
            logger.warning("preload: failed to load step %d from %s", step, path, exc_info=True)


async def vtkjs_warmup(
    state: Any,
    path: Path,
    n_frames: int,
) -> None:
    """Warm the mesh cache for keyframes in the active series."""
    n_steps = int(state.n_steps)
    if n_steps <= 1:
        return
    loop = asyncio.get_running_loop()
    inc = math.ceil(n_steps / n_frames)
    steps = list(range(0, n_steps, inc))
    for step in steps:
        try:
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        try:
            await loop.run_in_executor(None, load_mesh, path, step)
        except Exception:
            logger.warning("warmup: failed to load step %d from %s", step, path, exc_info=True)


async def autoplay_loop(
    state: Any,
    plotter: pv.Plotter,
    ctrl: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    frame_sleep: float,
) -> None:
    """Advance steps until stopped or the sequence ends."""
    try:
        while state.autoplay:
            step = int(state.active_step)
            n = int(state.n_steps)
            inc = int(state.step_inc)
            next_step = 0 if step + inc >= n else step + inc
            select_step(plotter, ctrl, state, project_metadata, xdmf_meta, next_step)
            with state:  # flush the step change to the client
                pass
            speed = float(getattr(state, "playback_speed", 1.0)) or 1.0
            await asyncio.sleep(frame_sleep / speed)
    finally:
        state.autoplay = False
