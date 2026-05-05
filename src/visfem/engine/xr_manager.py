"""WebXR session management and in-VR exit panel."""
from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pyvista as pv
from trame.widgets.vtk import VtkWebXRHelper
from vtkmodules.vtkRenderingCore import vtkActor

from visfem.log import get_logger

logger = get_logger(__name__)

# Exit panel geometry (mm — mesh units)
_PANEL_W = 200.0
_PANEL_H = 80.0
_BORDER_PAD = 10.0
_TEXT_HEIGHT = 26.0

# Placement offsets relative to camera at VR entry (mm)
_FORWARD = 600.0    # arm's length in front
_RIGHTWARD = 350.0  # offset to the right so it doesn't block the mesh
_DOWNWARD = 80.0    # slightly below eye level

PANEL_COLOR = "#00bfa5"   # app accent teal


class XRManager:
    """Manages WebXR entry/exit and the in-VR exit panel actor."""

    def __init__(self, plotter: pv.Plotter, state: Any, ctrl: Any) -> None:
        self.plotter = plotter
        self.state = state
        self.ctrl = ctrl
        self._panel_actor: vtkActor | None = None
        self._border_actor: vtkActor | None = None
        self._label_actor: vtkActor | None = None
        self._saved_cam: dict | None = None

    def on_enter_xr(self) -> None:
        if self.state.xr_active:
            logger.info("[XR] on_enter_xr fired again — idempotency guard blocked (already active)")
            return
        self._save_camera()
        logger.info("[XR] on_enter_xr — setting xr_active=True")
        self.state.xr_active = True
        # self._place_exit_panel()
        self.ctrl.view_update()
        logger.info("[XR] view_update sent after entering XR")

    def on_exit_xr(self) -> None:
        logger.info("[XR] on_exit_xr — restoring camera and resyncing scene")
        self.state.xr_active = False
        # self._remove_exit_panel()
        self._restore_camera()   # undo headset-pose overwrite of vtk.js camera
        self.ctrl.view_update()
        asyncio.ensure_future(self._post_exit_refresh())
        logger.info("[XR] camera pushed, geometry refresh scheduled in 250ms")

    def toggle_xr(self) -> None:
        if self.state.xr_active:
            logger.info("[XR] toggle_xr — stopping XR session")
            self.ctrl.stop_xr()
        else:
            logger.info("[XR] toggle_xr — starting XR session (HmdVR)")
            self.ctrl.start_xr(VtkWebXRHelper.XrSessionTypes.HmdVR)

    def on_exit_triggered(self, triggered: bool) -> None:
        """JS ray-sphere hit detected — stop XR session."""
        logger.info("[XR] on_exit_triggered called with triggered=%s xr_active=%s", triggered, self.state.xr_active)
        if triggered and self.state.xr_active:
            self.state.xr_exit_triggered = False
            logger.info("[XR] exit panel triggered — stopping XR")
            self.ctrl.stop_xr()

    def on_session_ended(self, ended: bool) -> None:
        """JS session 'end' event (system button exit)."""
        logger.info("[XR] on_session_ended called with ended=%s xr_active=%s", ended, self.state.xr_active)
        if ended:
            self.state.xr_session_ended = False
            if self.state.xr_active:
                # on_exit_xr didn't fire (unexpected) — do full cleanup here
                logger.info("[XR] on_exit_xr did not fire before on_session_ended — cleaning up")
                self.state.xr_active = False
                self._restore_camera()
                self.ctrl.view_update()
            asyncio.ensure_future(self._post_session_end_refresh())
            logger.info("[XR] extended refresh scheduled in 500ms (system button exit)")

    def reset_on_reconnect(self) -> None:
        """Reset XR state when the client reconnects."""
        logger.info("[XR] client reconnected — resetting xr_active to False")
        self.state.xr_active = False
        # self._remove_exit_panel()


    def _save_camera(self) -> None:
        cam = self.plotter.camera
        self._saved_cam = {
            "position": tuple(cam.position),
            "focal_point": tuple(cam.focal_point),
            "view_up": tuple(cam.up),
        }
        logger.info("[XR] camera saved: pos=(%.1f,%.1f,%.1f)", *self._saved_cam["position"])

    def _restore_camera(self) -> None:
        """Undo the headset-pose overwrite of the vtk.js camera and push to client."""
        cam = self.plotter.camera
        if self._saved_cam:
            cam.position = self._saved_cam["position"]
            cam.focal_point = self._saved_cam["focal_point"]
            cam.up = self._saved_cam["view_up"]
            self.plotter.renderer.ResetCameraClippingRange()
            logger.info("[XR] camera restored: pos=(%.1f,%.1f,%.1f)", *self._saved_cam["position"])
            self._saved_cam = None
        else:
            self.plotter.reset_camera()
            logger.info("[XR] camera reset to fit mesh (no saved camera)")
        self.ctrl.view_push_camera()

    async def _post_exit_refresh(self) -> None:
        """250ms after exit: push camera + geometry again in case the first push raced vtk.js teardown."""
        await asyncio.sleep(0.25)
        logger.info("[XR] _post_exit_refresh: resyncing camera + geometry")
        self.ctrl.view_push_camera()
        self.ctrl.view_update_geometry()

    async def _post_session_end_refresh(self) -> None:
        """500ms after system-button exit: final push to recover a blank viewport."""
        await asyncio.sleep(0.5)
        logger.info("[XR] _post_session_end_refresh: final camera + geometry resync")
        self.ctrl.view_push_camera()
        self.ctrl.view_update()
        self.ctrl.view_update_geometry()

    def _camera_frame(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return (pos, fwd, right, up) unit vectors from current camera."""
        cam = self.plotter.camera
        pos = np.array(cam.position, dtype=float)
        fp = np.array(cam.focal_point, dtype=float)

        fwd = fp - pos
        n = np.linalg.norm(fwd)
        fwd = fwd / n if n > 1e-6 else np.array([0.0, 1.0, 0.0])

        # Orthogonalize cam.up against fwd to get a clean up vector
        raw_up = np.array(cam.up, dtype=float)
        raw_up -= np.dot(raw_up, fwd) * fwd
        u = np.linalg.norm(raw_up)
        if u < 1e-6:
            raw_up = np.array([0.0, 0.0, 1.0])
            raw_up -= np.dot(raw_up, fwd) * fwd
            u = np.linalg.norm(raw_up)
        up = raw_up / u

        right = np.cross(fwd, up)
        right /= np.linalg.norm(right)
        return pos, fwd, right, up

    def _place_exit_panel(self) -> None:
        self._remove_exit_panel()
        pos, fwd, right, up = self._camera_frame()

        # Panel center: arm's length forward, offset right, slightly down
        center = pos + fwd * _FORWARD + right * _RIGHTWARD - up * _DOWNWARD
        logger.info("[XR] placing exit panel at (%.1f, %.1f, %.1f)", *center)

        # Flat panel — normal faces back toward camera (-fwd)
        panel_mesh = pv.Plane(
            center=center, direction=-fwd,
            i_size=_PANEL_W, j_size=_PANEL_H,
            i_resolution=1, j_resolution=1,
        )
        # Border: slightly behind the panel (2 mm further from camera)
        border_mesh = pv.Plane(
            center=center + fwd * 2, direction=-fwd,
            i_size=_PANEL_W + _BORDER_PAD * 2,
            j_size=_PANEL_H + _BORDER_PAD * 2,
            i_resolution=1, j_resolution=1,
        )

        # Text: create in local XY, center it, then transform to face camera
        label_mesh = pv.Text3D("EXIT VR", depth=4, height=_TEXT_HEIGHT)
        tb = label_mesh.bounds
        tw = tb[1] - tb[0]
        th = tb[3] - tb[2]
        label_mesh.translate([-tw / 2, -th / 2, 0], inplace=True)
        # local X→world right, local Y→world up, local Z→-fwd (faces camera)
        R = np.column_stack([right, up, -fwd])
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = center - fwd * 3  # 3 mm in front of panel
        label_mesh.transform(T, inplace=True)

        panel_actor = self.plotter.add_mesh(
            panel_mesh, color=PANEL_COLOR, show_scalar_bar=False, render=False, opacity=0.93,
        )
        assert panel_actor is not None
        panel_actor.DragableOff()
        self._panel_actor = panel_actor

        border_actor = self.plotter.add_mesh(
            border_mesh, color="white", show_scalar_bar=False, render=False, opacity=0.20,
        )
        assert border_actor is not None
        border_actor.DragableOff()
        self._border_actor = border_actor

        label_actor = self.plotter.add_mesh(
            label_mesh, color="white", show_scalar_bar=False, render=False,
        )
        assert label_actor is not None
        label_actor.DragableOff()
        self._label_actor = label_actor

        self.state.exit_btn_pos = list(center)
        logger.info("[XR] exit panel actors added at (%.1f, %.1f, %.1f)", *center)

    def _remove_exit_panel(self) -> None:
        for attr in ("_panel_actor", "_border_actor", "_label_actor"):
            actor = getattr(self, attr, None)
            if actor is not None:
                self.plotter.remove_actor(actor)
                setattr(self, attr, None)
