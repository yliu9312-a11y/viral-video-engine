"""Motion Analyzer: optical flow energy + element tracking for S1.

Stage 1: Per-frame optical flow → visual_energy_curve + motion_events
Stage 2: Element detection + trajectory tracking → ElementTrack list

Uses RAFT (torchvision) for optical flow, with Farneback (OpenCV) fallback.
Element detection via contour analysis + per-element optical flow tracking.
"""

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
FLOW_SIZE = (480, 272)          # RAFT input (must be /8); smaller = faster
SMOOTH_WINDOW_SEC = 0.8         # energy curve smoothing window
EVENT_MIN_DURATION_SEC = 0.3    # minimum motion event duration
EVENT_PROMINENCE = 0.15         # peak prominence threshold (normalized 0-1)
TRACK_SAMPLE_INTERVAL = 0.1     # element position sample interval (seconds)
TRACK_SEARCH_RADIUS_RATIO = 0.15  # search radius as fraction of frame size
ELEMENT_MIN_AREA_RATIO = 0.002  # minimum contour area as fraction of frame
ELEMENT_MAX_COUNT = 15          # max elements to track per video
MAX_TRACK_DURATION_SEC = 5.0    # max tracking duration per element (seconds)
MAX_DRIFT_RATIO = 0.3           # max cumulative drift from original position (fraction of frame)
DEAD_ZONE = 0.005               # ignore displacements smaller than this (noise threshold)
SCENE_CHANGE_THRESHOLD = 0.04   # displacement jump indicating scene transition (normalized)
CONTENT_MATCH_THRESHOLD = 0.25  # NCC threshold (0-1, higher=stricter; 0.25 accounts for JPEG + edge clipping)


# ── Data Classes ───────────────────────────────────────────────────────────
@dataclass
class MotionSample:
    """An element's state at one moment."""
    t: float
    x: float              # normalized center [0,1]
    y: float
    w: float              # normalized bbox
    h: float
    rotation: float = 0.0
    opacity: float = 1.0
    visible: bool = True


@dataclass
class ElementTrack:
    """Trajectory of one tracked element across frames."""
    element_id: int
    label: str
    samples: list[MotionSample] = field(default_factory=list)
    enter_t: float = 0.0
    exit_t: float = 0.0
    motion_type: str = "static"
    path_summary: str = ""
    beat_synced: bool = False
    confidence: float = 1.0


@dataclass
class MotionTimeline:
    """Complete motion analysis output for a video."""
    visual_energy_curve: list[float] = field(default_factory=list)
    motion_events: list[dict] = field(default_factory=list)
    tracks: list[ElementTrack] = field(default_factory=list)

    def resample_energy(self, n_segments: int) -> list[float]:
        """Resample visual_energy_curve to n_segments (for alignment with audio.energy_curve)."""
        curve = self.visual_energy_curve
        if not curve or n_segments <= 0:
            return []
        if len(curve) == n_segments:
            return list(curve)
        # Average-pool into n_segments bins
        result = []
        bin_size = len(curve) / n_segments
        for i in range(n_segments):
            start = int(i * bin_size)
            end = int((i + 1) * bin_size)
            end = max(end, start + 1)
            result.append(float(np.mean(curve[start:end])))
        return result


# ── MotionAnalyzer ─────────────────────────────────────────────────────────
class MotionAnalyzer:
    """Optical flow + SAM2 element tracking analyzer."""

    def __init__(self, model, backend: str, fps: float, fw: int, fh: int, sam2_predictor=None):
        self.model = model
        self.backend = backend
        self.fps = fps
        self.fw = fw
        self.fh = fh
        self.sam2 = sam2_predictor

    @classmethod
    def create(cls, video_path: str) -> "MotionAnalyzer":
        """Create analyzer with RAFT optical flow + SAM2 element detection."""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        # Load RAFT optical flow
        model, backend = None, "farneback"
        try:
            import torch
            from torchvision.models.optical_flow import raft_small, Raft_Small_Weights
            model = raft_small(weights=Raft_Small_Weights.DEFAULT)
            model.eval()
            if torch.cuda.is_available():
                model = model.cuda()
            backend = "raft"
            logger.info("motion_analyzer: RAFT-Small loaded")
        except Exception as e:
            logger.info("motion_analyzer: RAFT unavailable (%s), using Farneback", e)

        # Load SAM2 for element detection
        sam2_predictor = None
        try:
            from sam2.build_sam import build_sam2_hf
            from sam2.sam2_image_predictor import SAM2ImagePredictor
            import torch as _torch
            device = "cuda" if _torch.cuda.is_available() else "cpu"
            sam2_model = build_sam2_hf("facebook/sam2.1-hiera-small", device=device)
            sam2_predictor = SAM2ImagePredictor(sam2_model)
            logger.info("motion_analyzer: SAM2.1-small loaded")
        except Exception as e:
            logger.info("motion_analyzer: SAM2 unavailable (%s), falling back to contour", e)

        return cls(model, backend, fps, fw, fh, sam2_predictor)

    def analyze(self, video_path: str) -> MotionTimeline:
        """Full analysis: energy curve + motion events + element tracks."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning("motion_analyzer: cannot open %s", video_path)
            return MotionTimeline()

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames < 2:
            cap.release()
            return MotionTimeline()

        # ── Stage 1: optical flow energy ───────────────────────────────────
        energies, timestamps = [], []
        prev_gray = None
        frame_idx = 0

        while True:
            ret, bgr = cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            t = frame_idx / self.fps

            if prev_gray is not None:
                try:
                    energy = float(self._compute_flow(prev_gray, gray))
                except Exception as e:
                    logger.debug("flow frame %d failed: %s", frame_idx, e)
                    energy = 0.0
                energies.append(energy)
                timestamps.append(t)

            prev_gray = gray
            frame_idx += 1

        cap.release()

        if not energies:
            return MotionTimeline()

        # Smooth first, THEN normalize — so peak reaches 1.0 and is comparable to audio.energy_curve
        smooth_energy = self._smooth(energies, self.fps, SMOOTH_WINDOW_SEC)
        norm_energy = self._normalize(smooth_energy)
        self._norm_energy = norm_energy  # store for scene change detection in tracking
        events = self._detect_events(norm_energy, timestamps, self.fps)

        # ── Stage 2: element tracking ──────────────────────────────────────
        tracks = self._track_elements(video_path, total_frames)

        return MotionTimeline(
            visual_energy_curve=norm_energy,
            motion_events=events,
            tracks=tracks,
        )

    def _compute_flow(self, prev_gray: np.ndarray, gray: np.ndarray) -> float:
        """Compute mean optical flow magnitude between two grayscale frames."""
        if self.backend == "raft":
            return self._raft_flow(prev_gray, gray)
        return self._farneback_flow(prev_gray, gray)

    def _raft_flow(self, f1_gray: np.ndarray, f2_gray: np.ndarray) -> float:
        """RAFT optical flow."""
        import torch

        f1 = cv2.resize(f1_gray, FLOW_SIZE).astype(np.float32) / 255.0
        f2 = cv2.resize(f2_gray, FLOW_SIZE).astype(np.float32) / 255.0
        t1 = torch.from_numpy(np.stack([f1, f1, f1], axis=0)).unsqueeze(0).float()
        t2 = torch.from_numpy(np.stack([f2, f2, f2], axis=0)).unsqueeze(0).float()

        if next(self.model.parameters()).is_cuda:
            t1, t2 = t1.cuda(), t2.cuda()

        with torch.no_grad():
            preds = self.model(t1, t2)

        flow = preds[-1][0].cpu().numpy()  # [2, H, W]
        mag = np.sqrt(flow[0] ** 2 + flow[1] ** 2)
        return float(np.mean(mag))

    def _farneback_flow(self, f1: np.ndarray, f2: np.ndarray) -> float:
        """OpenCV Farneback optical flow."""
        r1 = cv2.resize(f1, FLOW_SIZE)
        r2 = cv2.resize(f2, FLOW_SIZE)
        flow = cv2.calcOpticalFlowFarneback(
            r1, r2, None, 0.5, 3, 15, 3, 5, 1.2, 0,
        )
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        return float(np.mean(mag))

    # ── Energy Processing (static helpers) ──────────────────────────────────

    @staticmethod
    def _normalize(values: list[float]) -> list[float]:
        if not values:
            return []
        lo, hi = min(values), max(values)
        if hi - lo < 1e-9:
            return [0.0] * len(values)
        return [(v - lo) / (hi - lo) for v in values]

    @staticmethod
    def _smooth(values: list[float], fps: float, window_sec: float) -> list[float]:
        if len(values) < 3:
            return values
        win = max(3, int(fps * window_sec))
        if win > len(values):
            win = len(values)
        if win < 3:
            return values
        kernel = np.ones(win) / win
        smoothed = np.convolve(np.array(values), kernel, mode="same")
        return smoothed.tolist()

    @staticmethod
    def _detect_events(
        energy: list[float], timestamps: list[float], fps: float,
    ) -> list[dict]:
        if len(energy) < 5:
            return []
        try:
            from scipy.signal import find_peaks
            arr = np.array(energy)
            mean_e = float(np.mean(arr))
            std_e = float(np.std(arr))
            peaks, props = find_peaks(
                arr, height=mean_e + std_e * 0.2,
                distance=max(1, int(fps * 0.3)),
                prominence=EVENT_PROMINENCE,
            )
            valleys, _ = find_peaks(-arr, distance=max(1, int(fps * 0.3)))
            if len(peaks) == 0:
                return []
            events = []
            for p in peaks:
                v_before = valleys[valleys < p]
                v_after = valleys[valleys > p]
                start_t = timestamps[v_before[-1]] if len(v_before) > 0 else timestamps[0]
                end_t = timestamps[v_after[0]] if len(v_after) > 0 else timestamps[-1]
                dur = end_t - start_t
                if dur < EVENT_MIN_DURATION_SEC:
                    continue
                events.append({
                    "start_t": round(float(start_t), 3),
                    "end_t": round(float(end_t), 3),
                    "peak_t": round(float(timestamps[p]), 3),
                    "intensity": round(float(arr[p]), 4),
                    "duration": round(dur, 3),
                })
            return events
        except ImportError:
            # Fallback: simple threshold-based detection
            mean_e = float(np.mean(energy))
            events, in_event, start_idx = [], False, 0
            threshold = mean_e * 1.2
            for i, e in enumerate(energy):
                if e > threshold and not in_event:
                    in_event, start_idx = True, i
                elif e <= threshold and in_event:
                    if timestamps[i] - timestamps[start_idx] >= EVENT_MIN_DURATION_SEC:
                        peak_idx = start_idx + int(np.argmax(energy[start_idx:i]))
                        events.append({
                            "start_t": round(timestamps[start_idx], 3),
                            "end_t": round(timestamps[i], 3),
                            "peak_t": round(timestamps[peak_idx], 3),
                            "intensity": round(max(energy[start_idx:i]), 4),
                            "duration": round(timestamps[i] - timestamps[start_idx], 3),
                        })
                    in_event = False
            return events

    # ── Stage 2: Element Tracking ──────────────────────────────────────────

    def _track_elements(self, video_path: str, total_frames: int) -> list[ElementTrack]:
        """Detect elements from the most visually complex frame, track via optical flow."""
        sample_step = max(1, int(self.fps * TRACK_SAMPLE_INTERVAL))
        sample_indices = list(range(0, total_frames, sample_step))
        n_samples = len(sample_indices)

        # Find the frame with highest visual complexity for element detection
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []

        best_frame_idx = 0
        best_variance = -1.0
        best_bgr = None
        sample_count = min(20, total_frames)
        check_step = max(1, total_frames // sample_count)

        for idx in range(0, total_frames, check_step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, bgr = cap.read()
            if not ret:
                continue
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            v = float(np.var(gray))
            if v > best_variance:
                best_variance = v
                best_frame_idx = idx
                best_bgr = bgr

        if best_bgr is None:
            cap.release()
            return []

        logger.info("motion_analyzer: best detection frame: %d (variance=%.0f)", best_frame_idx, best_variance)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        elements = self._detect_elements(best_bgr)
        if not elements:
            cap.release()
            return []

        n_el = len(elements)
        cx_arr = np.zeros((n_el, n_samples), dtype=np.float32)
        cy_arr = np.zeros((n_el, n_samples), dtype=np.float32)
        w_arr = np.zeros((n_el, n_samples), dtype=np.float32)
        h_arr = np.zeros((n_el, n_samples), dtype=np.float32)
        vis_arr = np.zeros((n_el, n_samples), dtype=bool)

        # Find detection sample index
        det_sample_idx = 0
        for si, sfi in enumerate(sample_indices):
            if sfi >= best_frame_idx:
                det_sample_idx = si
                break

        orig_cx = np.array([e["cx"] for e in elements], dtype=np.float32)
        orig_cy = np.array([e["cy"] for e in elements], dtype=np.float32)
        track_start = np.full(n_el, -1.0)

        for i in range(n_el):
            cx_arr[i, det_sample_idx] = elements[i]["cx"]
            cy_arr[i, det_sample_idx] = elements[i]["cy"]
            w_arr[i, det_sample_idx] = elements[i]["w"]
            h_arr[i, det_sample_idx] = elements[i]["h"]
            vis_arr[i, det_sample_idx] = True

        # Detect scene changes from visual energy curve
        scene_changes = set()
        if self._norm_energy is not None and len(self._norm_energy) > 1:
            for si in range(det_sample_idx + 1, n_samples):
                ei = min(len(self._norm_energy) - 1, int(sample_indices[si] / total_frames * len(self._norm_energy)))
                ei_prev = min(len(self._norm_energy) - 1, int(sample_indices[si - 1] / total_frames * len(self._norm_energy)))
                if ei > 0 and ei_prev > 0:
                    if self._norm_energy[ei_prev] > 0.3 and self._norm_energy[ei] < self._norm_energy[ei_prev] * 0.4:
                        scene_changes.add(si)
        logger.info("motion_analyzer: %d scene changes detected", len(scene_changes))

        # Track forward via optical flow
        sr = TRACK_SEARCH_RADIUS_RATIO
        prev_gray = None

        for f_idx in range(total_frames):
            ret, bgr = cap.read()
            if not ret:
                break
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

            if f_idx in sample_indices:
                s_idx = sample_indices.index(f_idx)

                if s_idx > det_sample_idx and prev_gray is not None:
                    cur_t = sample_indices[s_idx] / self.fps

                    if s_idx in scene_changes:
                        for i in range(n_el):
                            vis_arr[i, s_idx] = False
                        prev_gray = gray
                        continue

                    for i in range(n_el):
                        if not vis_arr[i, s_idx - 1]:
                            continue

                        if track_start[i] < 0:
                            track_start[i] = cur_t
                        if cur_t - track_start[i] > MAX_TRACK_DURATION_SEC:
                            vis_arr[i, s_idx] = False
                            continue

                        cx, cy = cx_arr[i, s_idx - 1], cy_arr[i, s_idx - 1]
                        if cx < 0 or cy < 0 or cx >= 1.0 or cy >= 1.0:
                            vis_arr[i, s_idx] = False
                            continue

                        disp = self._element_displacement(
                            prev_gray, gray, cx, cy,
                            max(w_arr[i, s_idx - 1], h_arr[i, s_idx - 1]), sr,
                        )
                        if disp is None:
                            vis_arr[i, s_idx] = False
                            continue

                        dx, dy = disp
                        if (dx ** 2 + dy ** 2) ** 0.5 > SCENE_CHANGE_THRESHOLD:
                            vis_arr[i, s_idx] = False
                            continue

                        if abs(dx) < DEAD_ZONE and abs(dy) < DEAD_ZONE:
                            dx, dy = 0.0, 0.0

                        nx = orig_cx[i] + max(-MAX_DRIFT_RATIO, min(MAX_DRIFT_RATIO, cx + dx - orig_cx[i]))
                        ny = orig_cy[i] + max(-MAX_DRIFT_RATIO, min(MAX_DRIFT_RATIO, cy + dy - orig_cy[i]))
                        cx_arr[i, s_idx] = max(0.0, min(1.0, nx))
                        cy_arr[i, s_idx] = max(0.0, min(1.0, ny))
                        w_arr[i, s_idx] = w_arr[i, s_idx - 1]
                        h_arr[i, s_idx] = h_arr[i, s_idx - 1]
                        vis_arr[i, s_idx] = True

            prev_gray = gray

        cap.release()

        # Build tracks
        tracks = []
        for i, el in enumerate(elements):
            samples = []
            enter_t, exit_t = 0.0, 0.0
            first = True
            for j in range(n_samples):
                if vis_arr[i, j]:
                    t = sample_indices[j] / self.fps
                    samples.append(MotionSample(
                        t=t, x=float(cx_arr[i, j]), y=float(cy_arr[i, j]),
                        w=float(w_arr[i, j]), h=float(h_arr[i, j]),
                    ))
                    if first:
                        enter_t = t
                        first = False
                    exit_t = t
            if not samples:
                continue
            motion_type, path_summary = _classify_motion(samples)
            tracks.append(ElementTrack(
                element_id=i, label=el.get("label", f"element_{i}"),
                samples=samples, enter_t=enter_t, exit_t=exit_t,
                motion_type=motion_type, path_summary=path_summary,
                confidence=max(0.0, 1.0 - (len(samples) / max(n_samples, 1)) * 0.3),
            ))

        logger.info("motion_analyzer: tracked %d elements", len(tracks))
        return tracks

    def _detect_elements(self, bgr: np.ndarray) -> list[dict]:
        """Detect elements using SAM2 (preferred) or contour fallback.

        Returns list of {cx, cy, w, h, area_ratio, label} in normalized coords.
        """
        if self.sam2 is not None:
            try:
                return self._detect_elements_sam2(bgr)
            except Exception as e:
                logger.warning("motion_analyzer: SAM2 detection failed (%s), falling back to contour", e)
        return _detect_elements_contour(bgr, ELEMENT_MAX_COUNT, ELEMENT_MIN_AREA_RATIO)

    def _detect_elements_sam2(self, bgr: np.ndarray) -> list[dict]:
        """Use SAM2 automatic mask generator to find distinct elements."""
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator

        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        mask_gen = SAM2AutomaticMaskGenerator(
            model=self.sam2.model,
            points_per_side=32,
            points_per_batch=64,
            pred_iou_thresh=0.7,
            stability_score_thresh=0.92,
            min_mask_region_area=100,
        )

        masks_data = mask_gen.generate(rgb)
        if not masks_data:
            logger.info("motion_analyzer: SAM2 found no masks")
            return []

        # Sort by area (descending), take top-K
        masks_data.sort(key=lambda m: m["area"], reverse=True)
        frame_area = h * w

        elements = []
        for i, mask_info in enumerate(masks_data[:ELEMENT_MAX_COUNT]):
            bbox = mask_info["bbox"]  # (x, y, bw, bh)
            area = mask_info["area"]
            if area / frame_area < ELEMENT_MIN_AREA_RATIO:
                continue

            bx, by, bw, bh = bbox
            cx = (bx + bw / 2) / w
            cy = (by + bh / 2) / h
            nw = bw / w
            nh = bh / h

            # Generate label from mask properties
            aspect = bw / max(bh, 1)
            if aspect > 3:
                label = f"bar_{i}"
            elif aspect < 0.4:
                label = f"column_{i}"
            elif area / frame_area > 0.15:
                label = f"large_element_{i}"
            else:
                label = f"element_{i}"

            elements.append({
                "cx": cx, "cy": cy, "w": nw, "h": nh,
                "area_ratio": area / frame_area,
                "label": label,
                "mask": mask_info["segmentation"],
            })

        logger.info("motion_analyzer: SAM2 detected %d elements (from %d masks)", len(elements), len(masks_data))
        return elements

    def _element_displacement(
        self,
        prev_gray: np.ndarray,
        gray: np.ndarray,
        cx: float,
        cy: float,
        size: float,
        sr: float,
    ) -> tuple[float, float] | None:
        """Compute displacement of element at (cx,cy) between frames.

        Returns normalized (dx, dy) or None if tracking fails.
        """
        h, w = prev_gray.shape[:2]
        px, py = int(cx * w), int(cy * h)
        radius = max(int(size * max(h, w) * sr), 8)

        x1 = max(0, px - radius)
        y1 = max(0, py - radius)
        x2 = min(w, px + radius)
        y2 = min(h, py + radius)

        if x2 - x1 < 4 or y2 - y1 < 4:
            return None

        roi1 = prev_gray[y1:y2, x1:x2]
        roi2 = gray[y1:y2, x1:x2]

        try:
            if self.backend == "raft":
                return self._raft_roi_flow(roi1, roi2, w, h)
            return self._farneback_roi_flow(roi1, roi2, w, h)
        except Exception:
            return None

    def _raft_roi_flow(self, r1: np.ndarray, r2: np.ndarray, fw: int, fh: int) -> tuple[float, float]:
        """RAFT flow for a small ROI. Falls back to Farneback if ROI too small."""
        import torch

        rh, rw = r1.shape[:2]
        # RAFT needs input >= 128x128 (feature maps >= 16x16 after /8 downsampling)
        if rh < 128 or rw < 128:
            return self._farneback_roi_flow(r1, r2, fw, fh)

        def _round8(v): return max(8, (v // 8) * 8)
        new_w, new_h = _round8(rw), _round8(rh)
        f1 = cv2.resize(r1, (new_w, new_h)).astype(np.float32) / 255.0
        f2 = cv2.resize(r2, (new_w, new_h)).astype(np.float32) / 255.0

        t1 = torch.from_numpy(np.stack([f1, f1, f1], axis=0)).unsqueeze(0).float()
        t2 = torch.from_numpy(np.stack([f2, f2, f2], axis=0)).unsqueeze(0).float()

        if next(self.model.parameters()).is_cuda:
            t1, t2 = t1.cuda(), t2.cuda()

        with torch.no_grad():
            preds = self.model(t1, t2)

        flow = preds[-1][0].cpu().numpy()
        return (float(np.mean(flow[0])) / fw, float(np.mean(flow[1])) / fh)

    def _farneback_roi_flow(self, r1: np.ndarray, r2: np.ndarray, fw: int, fh: int) -> tuple[float, float]:
        """Farneback flow for a small ROI."""
        flow = cv2.calcOpticalFlowFarneback(r1, r2, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        return (float(np.mean(flow[..., 0])) / fw, float(np.mean(flow[..., 1])) / fh)


# ── Element Detection (contour-based, no SAM2 dependency) ──────────────────

def _detect_scene_changes(energy: list[float], threshold: float = 0.3) -> list[int]:
    """Detect scene change boundaries from visual energy curve.

    A scene change is where energy drops sharply (high → low transition).
    Returns list of sample indices where scene changes occur.
    """
    if len(energy) < 3:
        return []
    changes = []
    for i in range(1, len(energy) - 1):
        # Sharp drop: current much lower than previous, and next is also low
        if energy[i - 1] > threshold and energy[i] < energy[i - 1] * 0.5:
            changes.append(i)
    return changes


def _detect_elements_contour(bgr: np.ndarray, max_count: int, min_area_ratio: float) -> list[dict]:
    """Detect distinct visual elements via contour analysis.

    Returns list of {cx, cy, w, h, area, label} in normalized coordinates.
    """
    h, w = bgr.shape[:2]
    frame_area = h * w

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Adaptive threshold handles varying backgrounds
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 4,
    )

    # Close small gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Score and filter contours
    elements = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < frame_area * min_area_ratio:
            continue

        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bw < 5 or bh < 5:
            continue

        score = area / frame_area
        elements.append({
            "cx": (bx + bw / 2) / w,
            "cy": (by + bh / 2) / h,
            "w": bw / w,
            "h": bh / h,
            "area_ratio": area / frame_area,
            "score": score,
            "label": f"element_{len(elements)}",
        })

    # Sort by area, take top-K
    elements.sort(key=lambda e: e["area_ratio"], reverse=True)
    elements = elements[:max_count]

    # Assign semantic labels via simple heuristics
    for i, el in enumerate(elements):
        ar = el["w"] / max(el["h"], 0.01)
        if ar > 3:
            el["label"] = f"horizontal_bar_{i}"
        elif ar < 0.4:
            el["label"] = f"vertical_element_{i}"
        elif el["area_ratio"] > 0.1:
            el["label"] = f"large_block_{i}"
        else:
            el["label"] = f"element_{i}"

    return elements


# ── Motion Classification ──────────────────────────────────────────────────

def _classify_motion(samples: list[MotionSample]) -> tuple[str, str]:
    """Classify motion type from trajectory samples.

    Returns (motion_type, path_summary).
    """
    if len(samples) < 2:
        return "static", "stationary"

    xs = [s.x for s in samples]
    ys = [s.y for s in samples]

    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    displacement = (dx ** 2 + dy ** 2) ** 0.5

    if displacement < 0.02:
        return "static", "stationary"

    # Velocity profile
    velocities = []
    for i in range(1, len(samples)):
        dt = samples[i].t - samples[i - 1].t
        if dt <= 0:
            continue
        ddx = samples[i].x - samples[i - 1].x
        ddy = samples[i].y - samples[i - 1].y
        velocities.append((ddx ** 2 + ddy ** 2) ** 0.5 / dt)

    if not velocities:
        return "linear", _describe_path(samples)

    avg_v = sum(velocities) / len(velocities)
    max_v = max(velocities)
    v_ratio = max_v / max(avg_v, 0.001)

    # Check for oscillation (sign changes in velocity)
    sign_changes = 0
    for i in range(1, len(velocities)):
        if velocities[i] * velocities[i - 1] < 0:
            sign_changes += 1

    if sign_changes >= len(velocities) * 0.4:
        return "bounce", _describe_path(samples)

    # Acceleration profile: slow-fast-slow = ease_in_out
    if len(velocities) >= 4:
        n = len(velocities)
        early = sum(velocities[: n // 3]) / (n // 3)
        mid = sum(velocities[n // 3: 2 * n // 3]) / (n // 3)
        late = sum(velocities[2 * n // 3:]) / max(n - 2 * (n // 3), 1)

        if mid > early * 1.3 and mid > late * 1.3:
            return "ease_in_out", _describe_path(samples)

        if late > early * 1.5:
            return "ease_in", _describe_path(samples)

        if early > late * 1.5:
            return "ease_out", _describe_path(samples)

    if v_ratio > 2.0:
        return "overshoot", _describe_path(samples)

    return "linear", _describe_path(samples)


def _describe_path(samples: list[MotionSample]) -> str:
    """Generate human-readable path description."""
    if len(samples) < 2:
        return "stationary"

    sx, sy = samples[0].x, samples[0].y
    ex, ey = samples[-1].x, samples[-1].y
    disp = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5

    if disp < 0.02:
        return "stationary"

    parts = [f"from ({sx:.2f},{sy:.2f}) to ({ex:.2f},{ey:.2f})"]

    # Direction
    adx, ady = ex - sx, ey - sy
    if abs(adx) > abs(ady):
        parts.append("horizontal" if adx > 0 else "horizontal-reverse")
    else:
        parts.append("downward" if ady > 0 else "upward")

    # Scale change
    if samples[0].w > 0 and samples[-1].w > 0:
        scale = samples[-1].w / samples[0].w
        if scale > 1.2:
            parts.append(f"scale {scale:.0%}")
        elif scale < 0.8:
            parts.append(f"shrink {scale:.0%}")

    return ", ".join(parts)
