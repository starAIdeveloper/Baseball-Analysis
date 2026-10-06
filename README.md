# Baseball Analysis

A working, local baseball video review lab inspired by ball-trajectory, strike-zone and biomechanics visualization references. It combines an actual OpenCV candidate extractor with editable annotations, image-plane measurements and annotated video exports.

## Run

Python 3.12 and FFmpeg are required.

```bash
git clone https://github.com/starAIdeveloper/Baseball-Analysis.git
cd Baseball-Analysis
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Open http://127.0.0.1:8000. Upload a fixed-camera clip, or choose **Try sample**. The sample is original procedural test footage, visibly labeled; all candidate detections are computed from its decoded frames.

## Workflow

1. Upload a video up to 60 seconds / 100 MB. Processing supports 1–120 fps and up to 16 MP decoded input, resized to a maximum dimension of 960 pixels.
2. Create a pitch, seek to its start and end, and import candidates from that interval. Each interval should contain one pitch. Inspect the result, undo unwanted points, or mark ball centers manually on paused frames. A click replaces the annotation at that frame time.
3. Define a manual zone using two corners. The last reviewed point is reported as inside/outside that image rectangle. This is **not** a verified strike call or a known crossing of the home-plate plane.
4. Optionally calibrate two reference points using their known distance. Calibrate in the same image plane as the reviewed motion. This uses a single uniform image scale, not perspective reconstruction.
5. For pitching or swing mechanics, mark three joints on a paused frame. The middle point is the angle vertex. Angles are manual 2D projected observations, not inferred 3D biomechanics.
6. Save the review. Download JSON or pitch CSV, or render an annotated H.264 MP4. Saved recordings and annotations survive a restart.

The navigation switches review context and tools within a shared workspace. Field annotations use a manual image rectangle, not automatic fielder recognition. Reports contain reviewed data, not invented athlete performance statistics.

## Measurement conventions

Coordinates use **image width as the unit for both axes**: x = pixel_x / width, y = pixel_y / width. This preserves Euclidean image geometry across aspect ratios. Frame timestamps are index / source fps. Joint angles are computed from these image points.

Without calibration, speed is image-width units per second. With calibration, speed is an **image-plane km/h estimate**. Mean speed is the arithmetic mean of successive segment speeds. It is not radar-equivalent pitch velocity. A single camera and uniform image scale do not recover depth, perspective, lens distortion, true release speed, spin, launch angle or ball flight in three dimensions.

CSV exports reviewed pitch samples and speed units. Full JSON includes raw unverified candidate observations, review annotations, pose angles and derived pitch metrics. Annotated MP4s show source-time reviewed trajectories, the manual zone and joint points, plus optional orange candidate circles. Audio is omitted. The source frame rate and frame count are retained for validated constant-rate footage; variable-frame-rate inputs are decoded on OpenCV's nominal fps timebase and require conversion to constant frame rate for precision work.

## Detector and limits

The default extractor finds small, approximately circular, bright regions that change between adjacent frames. Selection uses circularity and proximity to the preceding candidate. It does not semantically recognize baseballs, players or bats, and does not fabricate confidence scores. Whites on uniforms, reflections, camera cuts, moving cameras, occlusion, blur and tiny fast-moving balls can yield false detections or misses. Candidate continuity is not a verified track identity. No trained pose model is bundled; joint observations are manual.

The generated sample is a controlled fixture, not an accuracy benchmark on real baseball footage. Production use requires representative labeled recordings and an evaluated trained detector, camera calibration and suitable high-frame-rate capture. Reviews must be checked before making coaching conclusions.

Processing and rendering run in one worker with a bounded three-job queue. Uploads, results and rendered media stay under `data/`, excluded from Git. Bound the service to loopback; this is a single-user local app without authentication or live camera ingestion. Delete recording directories while the server is stopped to reclaim space. Limits cap per-clip processing but total disk retention is manual.

## API

Interactive schema: `/docs`.

| Endpoint | Purpose |
| --- | --- |
| POST /api/upload | Multipart video upload |
| POST /api/sample | Generate and analyze test footage |
| GET /api/recordings | List completed recordings |
| GET /api/jobs/{id} | Processing/rendering status |
| GET /api/jobs/{id}/result | Candidate frames, review and metrics |
| PUT /api/jobs/{id}/review | Validate and persist complete review |
| GET /api/jobs/{id}/video | H.264 source playback, HTTP Range supported |
| GET /api/jobs/{id}/export?format=csv | CSV; omit format for JSON |
| POST /api/jobs/{id}/render | Render the saved annotation snapshot |
| GET /api/jobs/{id}/annotated | Download rendered MP4 |

## Validation

```bash
pip install -r requirements-dev.txt
pytest -q
playwright install chromium
BASEBALL_START_SERVER=1 python scripts/browser_check.py
```

PowerShell: `$env:BASEBALL_START_SERVER='1'; python scripts/browser_check.py`.

`BASEBALL_CHROMIUM` optionally selects a preinstalled Chromium executable; `BASEBALL_URL` sets a running server URL when auto-start is disabled. Auto-start uses the URL's port and a temporary data directory. Backend tests validate known geometric results, actual generated-video detections, empty/corrupt video behavior, export frame timing, review validation, CSV formula escaping, seeking and restart persistence. Browser checks exercise actual uploads, edits, calibration, joint measurements, saved reviews, downloads and desktop/mobile viewports. These are browser viewport checks, not physical phone tests.

GitHub Actions runs backend and browser validation on pushes and pull requests. The Dockerfile is supplied for local deployment but has not been executed in this environment.

## History

Created with AI assistance in successive implementation commits. Imported GitHub commits include their original local SHA. `Baseball-Analysis-history.bundle` retains the exact local commit IDs, authors and timestamps. There are no backdated or fabricated development commits.
