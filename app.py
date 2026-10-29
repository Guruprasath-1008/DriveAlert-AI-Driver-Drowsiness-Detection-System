"""
DriveAlert - AI Driver Drowsiness Detection System
High-performance, fault-tolerant Flask backend with OpenCV + MediaPipe Tasks FaceLandmarker.
Compatible with mediapipe >= 0.10.30 and Python 3.10 - 3.13+.
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import threading
import os
import sys
import socket
import base64
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from flask import Flask, render_template, Response, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ─── Model path & Certificates ─────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(ROOT_DIR, "face_landmarker.task")
CERT_FILE = os.path.join(ROOT_DIR, "cert.pem")
KEY_FILE = os.path.join(ROOT_DIR, "key.pem")

# ─── Eye landmark indices (MediaPipe Face Mesh 478-point model) ─────────────
LEFT_EYE_EAR  = [362, 385, 387, 263, 373, 380]  # P1 P2 P3 P4 P5 P6
RIGHT_EYE_EAR = [33,  160, 158, 133, 153, 144]   # P1 P2 P3 P4 P5 P6

LEFT_EYE_CONTOUR  = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
RIGHT_EYE_CONTOUR = [33,  7,   163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]

# ─── SSL Certificate Generator ─────────────────────────────────────────────
def ensure_ssl_certs():
    """Generates self-signed SSL certificates for HTTPS access on any network."""
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return True
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime, ipaddress

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, u'DriveAlert'),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u'DriveAlert AI'),
        ])
        
        sans = [
            x509.DNSName(u'localhost'),
            x509.IPAddress(ipaddress.IPv4Address('127.0.0.1')),
        ]
        local_ip = get_local_ip()
        if local_ip != "127.0.0.1":
            try:
                sans.append(x509.IPAddress(ipaddress.IPv4Address(local_ip)))
            except Exception:
                pass

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .sign(key, hashes.SHA256())
        )

        with open(KEY_FILE, 'wb') as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        with open(CERT_FILE, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        return True
    except Exception as exc:
        print("[SSL] Could not generate self-signed certificate:", exc)
        return False


def get_local_ip():
    """Detect local LAN IP for network sharing."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ─── Thread-Safe Face Landmarker Manager ────────────────────────────────────
class LandmarkerManager:
    """Manages MediaPipe FaceLandmarker with thread safety and fast re-use."""
    def __init__(self):
        self._landmarker = None
        self._lock = threading.Lock()

    def get(self):
        if self._landmarker is not None:
            return self._landmarker
        with self._lock:
            if self._landmarker is None:
                if not os.path.exists(MODEL_PATH):
                    return None
                base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
                options = mp_vision.FaceLandmarkerOptions(
                    base_options=base_options,
                    running_mode=mp_vision.RunningMode.IMAGE,
                    num_faces=1,
                    min_face_detection_confidence=0.5,
                    min_face_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                    output_face_blendshapes=False,
                    output_facial_transformation_matrixes=False,
                )
                self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
            return self._landmarker

    def detect(self, mp_image, timeout=0.6):
        """Runs detection with a reasonable timeout so requests never hang or deadlock."""
        lm = self.get()
        if lm is None:
            return None
        acquired = self._lock.acquire(timeout=timeout)
        if not acquired:
            return None
        try:
            return lm.detect(mp_image)
        except Exception as e:
            print("[LandmarkerManager] Detect error:", e)
            return None
        finally:
            self._lock.release()

landmarker_mgr = LandmarkerManager()


# ─── Detection State ────────────────────────────────────────────────────────
class DetectionState:
    def __init__(self):
        self.running           = False
        self.cap               = None
        self.face_detected     = False
        self.ear               = 0.0
        self.status            = "idle"
        self.eyes_closed_start = None
        self.closed_duration   = 0.0
        self.alert_count       = 0
        self.session_start     = None
        self.frame_bytes       = None
        self.frame_id          = 0
        self.lock              = threading.Lock()
        self.thread            = None
        self.error             = None
        self.last_face_time    = 0.0
        # Adjustable thresholds
        self.EAR_THRESHOLD     = 0.22
        self.ALERT_SECONDS     = 2.0
        self.is_https          = False

state = DetectionState()


# ─── EAR Calculation ────────────────────────────────────────────────────────
def compute_ear(landmarks, eye_indices, img_w, img_h):
    """
    Eye Aspect Ratio (EAR):
        EAR = (||P2 - P6|| + ||P3 - P5||) / (2 * ||P1 - P4||)
    """
    def pt(idx):
        lm = landmarks[idx]
        return np.array([lm.x * img_w, lm.y * img_h])

    p1, p2, p3, p4, p5, p6 = [pt(i) for i in eye_indices]
    ear = (np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (
        2.0 * np.linalg.norm(p1 - p4) + 1e-6
    )
    return float(ear)


# ─── Draw Overlay ───────────────────────────────────────────────────────────
def draw_overlay(frame, face_detected, ear, status, closed_duration, alert_count):
    h, w = frame.shape[:2]

    colour_map = {
        "alert":       (0,   220,  80),
        "eyes_closed": (0,   200, 255),
        "drowsy":      (0,    0,  220),
        "idle":        (120, 120, 120),
    }
    colour = colour_map.get(status, (120, 120, 120))

    # Top status bar
    cv2.rectangle(frame, (0, 0), (w, 46), (8, 12, 24), -1)

    label_map = {
        "alert":       "DRIVER ALERT",
        "eyes_closed": "EYES CLOSED",
        "drowsy":      "DROWSINESS WARNING",
        "idle":        "MONITORING...",
    }
    label = label_map.get(status, "MONITORING...")
    cv2.putText(frame, label, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2, cv2.LINE_AA)

    if face_detected:
        cv2.putText(frame, f"EAR:{ear:.3f}", (w - 120, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (200, 210, 225), 1, cv2.LINE_AA)

    if closed_duration > 0:
        cv2.putText(frame, f"Closed: {closed_duration:.1f}s", (12, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, colour, 2, cv2.LINE_AA)

    if alert_count > 0:
        cv2.putText(frame, f"Alerts: {alert_count}", (w - 135, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 220), 2, cv2.LINE_AA)

    cv2.circle(frame, (w - 16, 23), 7, colour, -1)
    return frame


# ─── Camera Loop ────────────────────────────────────────────────────────────
def camera_loop():
    """Main camera loop with bulletproof exception handling and guaranteed resource cleanup."""
    cap = None
    try:
        # Check model exists
        if not os.path.exists(MODEL_PATH):
            with state.lock:
                state.running = False
                state.error = "Model face_landmarker.task not found on server"
            return

        # Attempt opening camera: DirectShow first for Windows fast startup, fallback to CAP_ANY
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            with state.lock:
                state.running = False
                state.error = "Could not open local camera (device index 0). Please check permissions."
            return

        # ── Step 1: Open at LOW resolution first so the camera auto-exposes correctly
        # Some webcams initialize with wrong exposure when forced straight to 720p.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        # ── Step 2: Enable auto-exposure, auto-focus, auto white-balance
        try:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE,   0.75)   # 0.75 = auto on most drivers
            cap.set(cv2.CAP_PROP_AUTOFOCUS,       1)
            cap.set(cv2.CAP_PROP_AUTO_WB,         1)
        except Exception:
            pass

        # ── Step 3: Drain stale frames so auto-exposure kicks in (removes focus lag)
        for _ in range(15):
            cap.grab()

        # ── Step 4: Switch to 720p AFTER auto-exposure has stabilised
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # Drain a few more frames at 720p to flush the resolution change
        for _ in range(5):
            cap.grab()

        with state.lock:
            state.cap           = cap
            state.session_start = time.time()
            state.status        = "alert"
            state.error         = None

        inference_lock = threading.Lock()
        latest_frame = {"img": None, "new": False}
        cached_result = {
            "face_detected": False,
            "ear": 0.0,
            "lms": None,
            "status": "alert",
            "closed_duration": 0.0,
            "alert_count": 0
        }

        # Background worker runs AI inference so video capture stays 100% fluid & zero-latency
        def worker():
            nonlocal cached_result
            while True:
                with state.lock:
                    if not state.running:
                        break

                raw = None
                with inference_lock:
                    if latest_frame["new"] and latest_frame["img"] is not None:
                        raw = latest_frame["img"]
                        latest_frame["new"] = False

                if raw is None:
                    time.sleep(0.008)
                    continue

                try:
                    h, w = raw.shape[:2]
                    small = cv2.resize(raw, (160, 90), interpolation=cv2.INTER_LINEAR)
                    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                    res = landmarker_mgr.detect(mp_img, timeout=0.08)
                    now = time.time()

                    face_detected = False
                    ear = 0.0
                    closed_dur = 0.0
                    lms_pts = None

                    if res and res.face_landmarks:
                        face_detected = True
                        lms = res.face_landmarks[0]
                        left_ear  = compute_ear(lms, LEFT_EYE_EAR,  w, h)
                        right_ear = compute_ear(lms, RIGHT_EYE_EAR, w, h)
                        ear       = float((left_ear + right_ear) / 2.0)
                        lms_pts   = [(int(lms[idx].x * w), int(lms[idx].y * h)) for idx in (LEFT_EYE_CONTOUR + RIGHT_EYE_CONTOUR)]

                        with state.lock:
                            state.last_face_time = now
                            state.ear = ear
                            thresh = state.EAR_THRESHOLD
                            alert_sec = state.ALERT_SECONDS

                            if ear < thresh:
                                if state.eyes_closed_start is None:
                                    state.eyes_closed_start = now
                                closed_dur = now - state.eyes_closed_start
                                state.closed_duration = closed_dur

                                if closed_dur >= alert_sec:
                                    if state.status != "drowsy":
                                        state.alert_count += 1
                                    state.status = "drowsy"
                                else:
                                    state.status = "eyes_closed"
                            else:
                                state.eyes_closed_start = None
                                state.closed_duration = 0.0
                                state.status = "alert"
                    else:
                        with state.lock:
                            # 400ms grace window so brief tracking jitters do not wipe out active drowsiness
                            if now - state.last_face_time > 0.4:
                                state.face_detected = False
                                state.eyes_closed_start = None
                                state.closed_duration = 0.0
                                state.ear = 0.0
                                state.status = "idle"

                    with state.lock:
                        cur_status = state.status
                        cur_alerts = state.alert_count
                        state.face_detected = face_detected

                    with inference_lock:
                        cached_result["face_detected"]   = face_detected
                        cached_result["ear"]             = ear
                        cached_result["lms"]             = lms_pts
                        cached_result["status"]          = cur_status
                        cached_result["closed_duration"] = closed_dur
                        cached_result["alert_count"]     = cur_alerts

                except Exception as ex:
                    print("[inference_worker] error:", ex)
                    time.sleep(0.02)

        infer_thread = threading.Thread(target=worker, daemon=True)
        infer_thread.start()

        # Capture loop – hard capped at 30 FPS to prevent CPU spin and keep frames fresh
        TARGET_FPS  = 30
        FRAME_DELAY = 1.0 / TARGET_FPS
        last_frame_time = 0.0

        while True:
            with state.lock:
                if not state.running:
                    break

            now = time.perf_counter()
            elapsed = now - last_frame_time
            if elapsed < FRAME_DELAY:
                # Sleep for the remaining time so we don't busy-spin
                time.sleep(FRAME_DELAY - elapsed)

            # Drain any buffered frames so we always get the freshest one
            cap.grab()
            cap.grab()  # double-grab flushes OS buffer (eliminates 1-2 frame lag)
            ret, frame = cap.retrieve()
            last_frame_time = time.perf_counter()

            if not ret or frame is None:
                time.sleep(0.02)
                continue

            frame = cv2.flip(frame, 1)

            # ── Brightness boost for dark/low-light cameras ──────────────────
            # Only enhance if the mean brightness is very low (< 80/255)
            mean_brightness = cv2.mean(frame)[0]
            if mean_brightness < 80:
                # CLAHE on the L channel of LAB – boosts detail without blowing out highlights
                lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
                l = clahe.apply(l)
                frame = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
            # ─────────────────────────────────────────────────────────────────

            with inference_lock:
                latest_frame["img"] = frame.copy()
                latest_frame["new"] = True
                res_snap = dict(cached_result)

            if res_snap["lms"]:
                for (cx, cy) in res_snap["lms"]:
                    cv2.circle(frame, (cx, cy), 1, (0, 220, 80), -1)

            frame = draw_overlay(
                frame,
                res_snap["face_detected"],
                res_snap["ear"],
                res_snap["status"],
                res_snap["closed_duration"],
                res_snap["alert_count"]
            )

            # Adaptive quality: smaller size on slow-start, normal after 2 s
            session_age = time.time() - state.session_start
            quality = 55 if session_age < 2 else 65
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])

            # Also encode a small 480p version for external/tunnel clients (saves ~80% bandwidth)
            small_frame = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_LINEAR)
            _, small_buf = cv2.imencode(".jpg", small_frame, [cv2.IMWRITE_JPEG_QUALITY, 50])

            with state.lock:
                state.frame_bytes       = buf.tobytes()
                state.frame_bytes_small = small_buf.tobytes()
                state.frame_id += 1

    except Exception as exc:
        print("[camera_loop] Unexpected error:", exc)
        with state.lock:
            state.error = str(exc)
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        with state.lock:
            state.cap         = None
            state.frame_bytes = None
            state.status      = "idle"
            state.running     = False


# ─── MJPEG Stream Generator ─────────────────────────────────────────────────
def generate_frames(low_bandwidth=False):
    """
    MJPEG stream generator.
    low_bandwidth=True  →  10 FPS, 640x360, quality 50  (for tunnels / external networks)
    low_bandwidth=False →  25 FPS, 1280x720, quality 65  (for local LAN connections)
    """
    boundary     = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    last_sent_id = -1
    TARGET_FPS   = 10 if low_bandwidth else 25
    MIN_INTERVAL = 1.0 / TARGET_FPS
    last_send_ts = 0.0

    while True:
        with state.lock:
            if not state.running:
                break
            frame_bytes = state.frame_bytes_small if low_bandwidth else state.frame_bytes
            frame_id    = state.frame_id

        now = time.perf_counter()
        if frame_bytes and frame_id != last_sent_id and (now - last_send_ts) >= MIN_INTERVAL:
            last_sent_id = frame_id
            last_send_ts = now
            try:
                yield boundary + frame_bytes + b"\r\n"
            except (GeneratorExit, ConnectionResetError, BrokenPipeError):
                break
        else:
            time.sleep(0.010)   # short sleep – never busy-spin


# ─── Routes ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    """
    Serve MJPEG stream.
    Auto-detects tunnel/external connections by inspecting the Host header:
      - Requests via localhost.run (*.lhr.life) or any non-LAN host → low-bandwidth 10 FPS 480p
      - Requests from localhost / LAN IP → full 720p 25 FPS
    """
    host = request.headers.get("Host", "")
    # Local if host is localhost, 127.x, 10.x, 192.168.x, 172.16-31.x, or plain LAN IP
    import re
    is_local = bool(re.match(
        r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)|(:\d+)?$",
        host
    ))
    low_bw = not is_local   # external / tunnel connection gets low-bandwidth stream

    return Response(
        generate_frames(low_bandwidth=low_bw),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/start_detection", methods=["POST"])
def start_detection():
    with state.lock:
        if state.running:
            return jsonify({"status": "already_running"})
        state.running          = True
        state.alert_count      = 0
        state.session_start    = time.time()
        state.eyes_closed_start = None
        state.closed_duration  = 0.0
        state.face_detected    = False
        state.status           = "idle"
        state.ear              = 0.0
        state.frame_bytes      = None
        state.frame_id         = 0
        state.error            = None

    t = threading.Thread(target=camera_loop, daemon=True)
    t.start()
    with state.lock:
        state.thread = t

    return jsonify({"status": "started"})


@app.route("/stop_detection", methods=["POST"])
def stop_detection():
    with state.lock:
        state.running = False

    thread = state.thread
    if thread and thread.is_alive():
        thread.join(timeout=2.0)

    with state.lock:
        state.status          = "idle"
        state.face_detected   = False
        state.closed_duration = 0.0
        state.ear             = 0.0
        state.frame_bytes     = None

    return jsonify({"status": "stopped"})


@app.route("/detection_status")
def detection_status():
    with state.lock:
        running       = state.running
        face_detected = state.face_detected
        status        = state.status
        ear           = round(state.ear, 4)
        closed_dur    = round(state.closed_duration, 2)
        alert_count   = state.alert_count
        session_start = state.session_start
        error         = state.error

    session_duration = 0
    if session_start:
        session_duration = round(time.time() - session_start, 1)

    return jsonify({
        "running":          running,
        "face_detected":    face_detected,
        "status":           status,
        "ear":              ear,
        "closed_duration":  closed_dur,
        "alert_count":      alert_count,
        "session_duration": session_duration,
        "error":            error,
    })


@app.route("/update_settings", methods=["POST"])
def update_settings():
    data = request.get_json(silent=True) or {}
    with state.lock:
        if "ear_threshold" in data:
            val = float(data["ear_threshold"])
            if 0.10 <= val <= 0.40:
                state.EAR_THRESHOLD = val
        if "alert_seconds" in data:
            val = float(data["alert_seconds"])
            if 0.5 <= val <= 10.0:
                state.ALERT_SECONDS = val
    return jsonify({"status": "ok"})


@app.route("/network_info")
def network_info():
    ip = get_local_ip()
    port = 5000
    scheme = "https" if state.is_https else "http"
    return jsonify({
        "ip": ip,
        "port": port,
        "is_https": state.is_https,
        "local_url": f"{scheme}://127.0.0.1:{port}",
        "network_url": f"{scheme}://{ip}:{port}",
        "http_network_url": f"http://{ip}:{port}",
        "https_network_url": f"https://{ip}:{port}"
    })


@app.route("/process_frame", methods=["POST"])
def process_frame():
    """Ultra-responsive frame inference for client/mobile devices on any network."""
    data = request.get_json(silent=True) or {}
    img_b64 = data.get("image")
    frame = None

    if img_b64:
        if "," in img_b64:
            img_b64 = img_b64.split(",", 1)[1]
        try:
            raw_bytes = base64.b64decode(img_b64)
            nparr = np.frombuffer(raw_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400
    else:
        # Binary raw JPEG fallback
        raw_bytes = request.get_data()
        if raw_bytes:
            nparr = np.frombuffer(raw_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({"error": "No valid frame received"}), 400

    h, w = frame.shape[:2]
    if w > 320:
        new_w = 320
        new_h = int(h * (320.0 / w))
        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        h, w = new_h, new_w

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    with state.lock:
        ear_thresh = state.EAR_THRESHOLD
        alert_sec = state.ALERT_SECONDS

    result = landmarker_mgr.detect(mp_image, timeout=0.15)

    face_detected = False
    ear = 0.0
    landmarks_data = []

    if result and result.face_landmarks:
        face_detected = True
        lms = result.face_landmarks[0]
        left_ear  = compute_ear(lms, LEFT_EYE_EAR,  w, h)
        right_ear = compute_ear(lms, RIGHT_EYE_EAR, w, h)
        ear = float((left_ear + right_ear) / 2.0)

        # Eye contours for client canvas overlay
        for idx in LEFT_EYE_CONTOUR + RIGHT_EYE_CONTOUR:
            landmarks_data.append({"x": round(lms[idx].x, 4), "y": round(lms[idx].y, 4)})

    return jsonify({
        "status": "ok",
        "face_detected": face_detected,
        "ear": round(ear, 4),
        "ear_threshold": ear_thresh,
        "alert_seconds": alert_sec,
        "is_closed": bool(face_detected and ear < ear_thresh),
        "landmarks": landmarks_data
    })


# ─── Entry Point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not os.path.exists(MODEL_PATH):
        print("ERROR: face_landmarker.task model not found!")
        print("Run this once to download it:")
        print("  python -c \"import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', 'face_landmarker.task')\"")
        exit(1)

    local_ip = get_local_ip()
    port = 5000

    # HTTP by default enables full compatibility with public HTTPS tunnels (localhost.run, pinggy, etc.)
    # Use --ssl flag for direct local self-signed HTTPS
    use_https = ("--ssl" in sys.argv)
    ssl_context = None

    if use_https:
        has_ssl = ensure_ssl_certs()
        if has_ssl and os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
            ssl_context = (CERT_FILE, KEY_FILE)
            state.is_https = True

    scheme = "https" if state.is_https else "http"

    print("=" * 64)
    print("  DriveAlert - AI Driver Drowsiness Detection System")
    print(f"  • Local PC:           {scheme}://127.0.0.1:{port}")
    print(f"  • Local Wi-Fi:        {scheme}://{local_ip}:{port}")
    print("  • External Networks:  Run share_mobile.bat to get a public HTTPS link")
    print("=" * 64)

    app.run(
        debug=False,
        threaded=True,
        host="0.0.0.0",
        port=port,
        ssl_context=ssl_context
    )
