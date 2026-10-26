"""Async background coroutines: vtk.js warmup and autoplay."""

import asyncio
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from visfem.engine.scene import Scene
from visfem.engine.selection import select_step
from visfem.log import get_logger
from visfem.mesh import load_mesh
from visfem.models import MeshMetadata, ProjectMetadata

logger = get_logger(__name__)

TARGET_FRAMES: int = 30  # max rendered frames for autoplay


def keyframe_increment(n_steps: int, n_frames: int = TARGET_FRAMES) -> int:
    """Return the step stride that spreads *n_steps* steps over at most *n_frames* keyframes."""
    return math.ceil(n_steps / n_frames)


def clear_overlay(state: Any) -> None:
    """Clear the loading and busy flags on *state* and flush them to the client; returns None."""
    with state:
        state.loading = False
        state.busy = False


async def vtkjs_warmup(
    gen: int,
    get_gen: Callable[[], int],
    state: Any,
    path: Path,
) -> None:
    """Load every keyframe step of *path* into the server-side mesh cache, then clear the overlay on *state* when *get_gen()* still equals *gen*."""
    n_steps = int(state.n_steps)
    if n_steps <= 1:
        return
    loop = asyncio.get_running_loop()
    inc = keyframe_increment(n_steps)
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
                logger.warning(
                    "warmup: step %d from %s failed", step, path, exc_info=True
                )
    finally:
        if get_gen() == gen:
            clear_overlay(state)


async def autoplay_loop(
    state: Any,
    scene: Scene,
    ctrl: Any,
    project_metadata: dict[str, ProjectMetadata],
    xdmf_meta: dict[Path, MeshMetadata],
    frame_sleep: float,
) -> None:
    """Advance *state.active_step* by *state.step_inc* through select_step with *scene*, *ctrl*, *project_metadata* and *xdmf_meta*, wrapping to step 0, every *frame_sleep* / *state.playback_speed* seconds until *state.autoplay* clears or a step fails."""
    try:
        while state.autoplay:
            step = int(state.active_step)
            n = int(state.n_steps)
            # the client sets step_inc and playback_speed, clamp them to what the UI offers
            inc = max(int(state.step_inc), 1)
            next_step = 0 if step + inc >= n else step + inc
            try:
                select_step(scene, ctrl, state, project_metadata, xdmf_meta, next_step)
            except Exception as e:
                logger.exception(
                    "autoplay: step %d of %s failed", next_step, state.active_dataset
                )
                with state:
                    state.error_message = f"Playback stopped at step {next_step}: {e}"
                    state.error_open = True
                return
            with state:  # flush the step change to the client
                pass
            speed = min(max(float(getattr(state, "playback_speed", 1.0)), 0.5), 4.0)
            # frame_sleep is the delay at 1x speed
            await asyncio.sleep(frame_sleep / speed)
    finally:
        # flushed, the client shows the stop of a failed or cancelled playback
        with state:
            state.autoplay = False
