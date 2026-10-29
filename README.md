# DriveAlert – AI Driver Drowsiness Detection System

> **Disclaimer:** This project is an **educational prototype** and is **not** a certified automotive safety system. Never rely on it as a substitute for adequate rest or safe driving practices.

---

## Overview

DriveAlert is a web-based driver monitoring system that uses your webcam and AI computer vision to detect prolonged eye closure in real time. Built with **Python / Flask** on the backend and vanilla **HTML / CSS / JavaScript** on the frontend, it runs entirely locally — no cloud, no subscriptions, no data uploads.

### Key Features

| Feature | Details |
|---|---|
| Real-time webcam stream | MJPEG stream over Flask |
| Face detection | MediaPipe Face Mesh (478 3D landmarks) |
| Eye tracking | Eye Aspect Ratio (EAR) algorithm |
| Smart alert logic | Ignores normal blinks; alerts after sustained closure |
| Audible alarm | Web Audio API three-beep pattern |
| Live dashboard | EAR gauge, session stats, configurable thresholds |
| Dark UI | Automotive safety dashboard aesthetic |

---

## Project Structure

```
mini project github/
├── app.py                  # Flask backend + OpenCV + MediaPipe
├── setup.py                # One-click setup & launcher
├── run.bat                 # Windows double-click launcher
├── requirements.txt        # Python dependencies
├── face_landmarker.task    # MediaPipe model (auto-downloaded by setup.py)
├── README.md
├── .gitignore
├── templates/
│   └── index.html          # Single-page frontend
└── static/
    ├── style.css           # Dashboard stylesheet
    └── script.js           # Frontend logic
```

---

## Requirements

- **Python 3.10 – 3.13** (all supported, Python 3.13 patch applied automatically)
- A **webcam** connected to the computer running the server
- Windows 10/11, macOS, or Linux

---

## Quick Start (Any System)

### Option A – Double-click (Windows only)

Simply double-click **`run.bat`** in the project folder.  
It will automatically set everything up and open the server.

### Option B – Command line (Windows / macOS / Linux)

```bash
# 1. Clone or copy the project folder to the target machine

# 2. Create a virtual environment (first time only)
python -m venv venv

# 3. Activate it
#    Windows:
venv\Scripts\activate
#    macOS / Linux:
source venv/bin/activate

# 4. Run the one-click setup (installs packages, patches MediaPipe, downloads model)
python setup.py
```

The server starts automatically. Open the URL shown in the terminal.

### Option C – Manual (if setup.py fails)

```bash
# Install dependencies
pip install -r requirements.txt

# Download the face landmark model
python -c "import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', 'face_landmarker.task')"

# Start the server
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

---

## Accessing From Mobiles & Other Computers

The server listens on **all interfaces** (`0.0.0.0:5000`).  
When `run.bat` or `app.py` starts, it displays both the local and network URLs:

```
  Local (this PC):           http://127.0.0.1:5000
  Network (Mobiles & Other): http://<Your-IP>:5000
```

### Method 1 – Same Wi-Fi Network (Local Access)

1. Connect your phone or secondary laptop to the **same Wi-Fi network**.
2. Open the **Network URL** shown in the terminal (or scan the QR code in the web app under **Connect Phone**).
3. If the page does not load, Windows Firewall is blocking inbound connections:
   - Double-click **`allow_firewall.bat`** (Run as Administrator) to unblock port 5000 and Python automatically!

### Method 2 – Instant Secure HTTPS Tunnel (Recommended for Mobiles & Camera)

Modern mobile browsers (Chrome on Android, Safari on iOS) block camera access (`getUserMedia`) on plain HTTP unless accessed over **HTTPS**.

To get an instant, secure public HTTPS link that works on **any phone** anywhere (even on mobile data 4G/5G):

1. Double-click **`share_mobile.bat`** in the project folder.
2. It launches a secure tunnel and prints an **`https://...a.pinggy.link`** URL.
3. Open this link on your phone.
4. Select **Phone / Browser Cam** to use your phone's front camera for driver drowsiness monitoring!

---

## Dual Camera Support (PC Webcam vs Phone Camera)

DriveAlert supports two camera modes directly from the UI:
- **PC Webcam**: Streams video from the webcam physically attached to the host computer running Flask.
- **Phone / Browser Cam**: Captures the mobile device's front-facing camera and sends frames to `/process_frame` for server-side MediaPipe analysis, with zero lag and real-time landmark overlays directly on the phone!

---

## How to Use

1. Go to the **Live Detection** section (or click "Start Detection" in the hero).
2. Choose your camera mode: **PC Webcam** or **Phone / Browser Cam**.
3. Click **Start Camera**.
4. The feed appears in the browser with real-time eye tracking overlaid.
5. If your eyes stay closed for more than **2 seconds** (default), a red alert flashes and an audible beep plays.
6. Click **Stop Camera** to end the session and release the webcam.

### Adjustable Settings

| Setting | Default | Range | Description |
|---|---|---|---|
| EAR Threshold | 0.22 | 0.10–0.40 | EAR below this = eyes closed |
| Alert Delay | 2.0 s | 0.5–10.0 s | Seconds before drowsy alert triggers |

---

## How It Works

1. **Webcam Capture** – OpenCV reads frames from the host camera (or browser captures mobile front camera via `getUserMedia`).
2. **Face Mesh** – MediaPipe FaceLandmarker detects 478 facial landmarks per frame.
3. **EAR Calculation** – For each eye, 6 landmark points are used:

   ```
   EAR = (|P2-P6| + |P3-P5|) / (2 * |P1-P4|)
   ```

   When the eye is open, EAR ≈ 0.25–0.35. When closed, EAR < 0.20.

4. **Alert Logic** – If `EAR < threshold` for `alert_delay` seconds continuously, the drowsy state triggers. Normal blinks (~150–200 ms) are ignored.
5. **MJPEG / REST Stream** – Server streams annotated MJPEG video or processes client frames via `/process_frame`.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Web not opening on mobile / other PC | 1) Run `allow_firewall.bat` as Administrator. 2) Make sure both devices are on the same Wi-Fi. 3) Or run `share_mobile.bat` for an instant HTTPS link. |
| Camera blocked on mobile browser | Mobile browsers require **HTTPS**! Double-click `share_mobile.bat` to access over HTTPS. |
| Camera feed is black | Run `python setup.py` — it applies the Python 3.13 MediaPipe patch |
| `No module named mediapipe` | Activate your venv first, then `pip install -r requirements.txt` |
| `face_landmarker.task` missing | Run `python setup.py` — it downloads the model automatically |
| Camera not opening on PC | Ensure no other app (Teams, Zoom, Camera) is using the webcam |
| Port already in use | Change `port=5000` to `port=5001` in `app.py` |
| Python 3.13 `AttributeError: free not found` | Run `python setup.py` — it patches MediaPipe automatically |


---

## Technologies Used

- **Python 3.x** – Core language
- **Flask** – Web framework and HTTP server
- **Flask-CORS** – Cross-Origin Resource Sharing
- **OpenCV** – Camera capture and image processing
- **MediaPipe** – FaceLandmarker Tasks API (478-point model)
- **NumPy** – Vector math for EAR computation
- **JavaScript ES6+** – Frontend interactivity
- **Web Audio API** – In-browser audible alerts

---

## License

MIT License – Free to use for educational and non-commercial purposes.


## 🎯 Project Objective

To develop an AI-based driver monitoring system that detects driver drowsiness using computer vision and provides alerts.

## 🛠️ Technologies Used

- Python
- Flask
- OpenCV
- HTML
- CSS
- JavaScript

## 🔮 Future Enhancements

- Improve drowsiness detection accuracy.
- Enhance alerts and notifications.
- Improve performance in different lighting conditions.

## 👨‍💻 Developer

**Dharnidharan SS**

B.Tech Artificial Intelligence and Data Science

## ⚠️ Disclaimer

This project is developed for educational purposes only. It is not a certified automotive safety system.
