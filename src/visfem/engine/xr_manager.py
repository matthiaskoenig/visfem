"""WebXR session management."""

from __future__ import annotations

import asyncio
from typing import Any

import pyvista as pv
from trame.widgets.vtk import VtkWebXRHelper

from visfem.log import get_logger

logger = get_logger(__name__)


class XRManager:
    """Manages WebXR entry and exit."""

    def __init__(self, plotter: pv.Plotter, state: Any, ctrl: Any) -> None:
        """Store the plotter, trame state and controller."""
        self.plotter = plotter
        self.state = state
        self.ctrl = ctrl
        self._saved_cam: dict | None = None
        self._refresh_task: asyncio.Task | None = None

    def on_enter_xr(self) -> None:
        """Save the camera, set xr_active and push a view update on XR entry."""
        if self.state.xr_active:
            logger.info("[XR] on_enter_xr fired while already active, ignored")
            return
        self._save_camera()
        logger.info("[XR] on_enter_xr: setting xr_active=True")
        self.state.xr_active = True
        self.ctrl.view_update()
        logger.info("[XR] view_update sent after entering XR")

    def on_exit_xr(self) -> None:
        """Clear xr_active, restore the camera and schedule the 250 ms refresh."""
        logger.info("[XR] on_exit_xr: restoring camera and resyncing scene")
        self.state.xr_active = False
        self._restore_camera()
        self.ctrl.view_update()
        self._refresh_task = asyncio.ensure_future(self._post_exit_refresh())
        logger.info("[XR] camera pushed, geometry refresh scheduled in 250ms")

    def toggle_xr(self) -> None:
        """Stop the XR session when active, else start an HmdVR session."""
        if self.state.xr_active:
            logger.info("[XR] toggle_xr: stopping XR session")
            self.ctrl.stop_xr()
        else:
            logger.info("[XR] toggle_xr: starting XR session (HmdVR)")
            self.ctrl.start_xr(VtkWebXRHelper.XrSessionTypes.HmdVR)

    def on_session_ended(self, ended: bool) -> None:
        """Handle the JS session 'end' event flagged by `ended` (system-button exit)."""
        logger.info(
            "[XR] on_session_ended called with ended=%s xr_active=%s",
            ended,
            self.state.xr_active,
        )
        if ended:
            self.state.xr_session_ended = False
            if self.state.xr_active:
                # Full cleanup for an exit that bypasses on_exit_xr
                logger.info(
                    "[XR] on_session_ended with xr_active still set, cleaning up"
                )
                self.state.xr_active = False
                self._restore_camera()
                self.ctrl.view_update()
            self._refresh_task = asyncio.ensure_future(self._post_session_end_refresh())
            logger.info("[XR] extended refresh scheduled in 500ms (system button exit)")

    def reset_on_reconnect(self) -> None:
        """Reset XR state when the client reconnects."""
        logger.info("[XR] client reconnected: resetting xr_active to False")
        self.state.xr_active = False

    def _save_camera(self) -> None:
        """Store the camera position, focal point and view-up for restore after XR."""
        cam = self.plotter.camera
        self._saved_cam = {
            "position": tuple(cam.position),
            "focal_point": tuple(cam.focal_point),
            "view_up": tuple(cam.up),
        }
        logger.info(
            "[XR] camera saved: pos=(%.1f,%.1f,%.1f)", *self._saved_cam["position"]
        )

    def _restore_camera(self) -> None:
        """Undo the headset-pose overwrite of the vtk.js camera and push to client."""
        cam = self.plotter.camera
        if self._saved_cam:
            cam.position = self._saved_cam["position"]
            cam.focal_point = self._saved_cam["focal_point"]
            cam.up = self._saved_cam["view_up"]
            self.plotter.renderer.ResetCameraClippingRange()
            logger.info(
                "[XR] camera restored: pos=(%.1f,%.1f,%.1f)",
                *self._saved_cam["position"],
            )
            self._saved_cam = None
        else:
            self.plotter.renderer.reset_camera()
            logger.info("[XR] camera reset to fit mesh, saved camera absent")
        self.ctrl.view_push_camera()

    async def _post_exit_refresh(self) -> None:
        """Push camera and geometry again 250 ms after XR exit."""
        await asyncio.sleep(0.25)  # the first push after exit can race vtk.js teardown
        logger.info("[XR] _post_exit_refresh: resyncing camera + geometry")
        self.ctrl.view_push_camera()
        self.ctrl.view_update_geometry()

    async def _post_session_end_refresh(self) -> None:
        """Push camera, view and geometry 500 ms after a system-button exit."""
        await asyncio.sleep(0.5)  # a system-button exit can leave the viewport blank
        logger.info("[XR] _post_session_end_refresh: final camera + geometry resync")
        self.ctrl.view_push_camera()
        self.ctrl.view_update()
        self.ctrl.view_update_geometry()
