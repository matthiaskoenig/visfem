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
    plotter: pv.Plotter,
    ctrl: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[str, MeshMetadata],
    n_frames: int,
) -> None:
    """Cycle through keyframes to pre-populate the vtk.js SHA cache."""
    n_steps = int(state.n_steps)
    if n_steps <= 1:
        return
    inc = math.ceil(n_steps / n_frames)
    steps = list(range(0, n_steps, inc))
    try:
        for step in steps:
            await asyncio.sleep(0)
            select_step(plotter, ctrl, state, project_metadata, xdmf_meta, step)
            with state:
                state.active_step = 0  # keep slider pinned at 0 during warmup
            await asyncio.sleep(0.04)
        if int(state.active_step) != 0:
            select_step(plotter, ctrl, state, project_metadata, xdmf_meta, 0)
            with state:
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
    """Advance one step at a time until stopped or the end of the sequence."""
    try:
        while state.autoplay:
            step = int(state.active_step)
            n = int(state.n_steps)
            inc = int(state.step_inc)
            next_step = 0 if step + inc >= n else step + inc
            select_step(plotter, ctrl, state, project_metadata, xdmf_meta, next_step)
            with state:
                pass
            await asyncio.sleep(frame_sleep)
    finally:
        state.autoplay = False
