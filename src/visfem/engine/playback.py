"""Async background coroutines: vtk.js warmup, step preloading, and autoplay."""
import asyncio
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyvista as pv

from visfem.engine.selection import select_step
from visfem.mesh import load_mesh
from visfem.models import MeshMetadata, ProjectMetadata


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
            pass


async def vtkjs_warmup(
    gen: int,
    get_gen: Callable[[], int],
    state: Any,
    path: Path,
    n_frames: int,
) -> None:
    """Warm the server-side mesh LRU cache for all keyframes, then clear loading state."""
    n_steps = int(state.n_steps)
    if n_steps <= 1:
        return
    loop = asyncio.get_running_loop()
    inc = math.ceil(n_steps / n_frames)
    steps = list(range(0, n_steps, inc))
    try:
        for step in steps:
            try:
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                return
            try:
                await loop.run_in_executor(None, load_mesh, path, step)
            except Exception:
                pass
    finally:
        if get_gen() == gen:
            with state:
                state.loading = False
                state.busy = False


async def autoplay_loop(
    state: Any,
    plotter: pv.Plotter,
    ctrl: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    frame_sleep: float,
) -> None:
    """Advance one step at a time until stopped or the end of the sequence.

    ``frame_sleep`` is the base delay at 1x speed; the live ``playback_speed`` state
    (cycled from the UI) divides it, so changing speed mid-playback takes effect on
    the next frame.
    """
    try:
        while state.autoplay:
            step = int(state.active_step)
            n = int(state.n_steps)
            inc = int(state.step_inc)
            next_step = 0 if step + inc >= n else step + inc
            select_step(plotter, ctrl, state, project_metadata, xdmf_meta, next_step)
            with state:
                pass
            speed = float(getattr(state, "playback_speed", 1.0)) or 1.0
            await asyncio.sleep(frame_sleep / speed)
    finally:
        state.autoplay = False
