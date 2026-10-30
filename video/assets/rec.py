"""Real browser screen recorder: Chrome screencast frames (1920x1080) -> exact-length 30 fps H.264 clip."""
import base64, os, subprocess, time
from pathlib import Path
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30
BUILD = Path(__file__).parent
WALLET_JS = (BUILD / "wallet_init.js").read_text()

CURSOR_JS = """
(() => {
  if (document.getElementById('__demo_cursor')) return;
  const c = document.createElement('div');
  c.id = '__demo_cursor';
  c.style.cssText = 'position:fixed;left:-50px;top:-50px;width:22px;height:22px;border-radius:50%;' +
    'background:rgba(234,88,12,.35);border:2px solid #ea580c;box-shadow:0 0 18px rgba(234,88,12,.8);' +
    'z-index:2147483647;pointer-events:none;transform:translate(-50%,-50%);transition:left .55s ease,top .55s ease;';
  document.documentElement.appendChild(c);
})();
"""


class Recorder:
    def __init__(self, page, name):
        self.page, self.name = page, name
        self.frames = []  # (t, jpeg bytes)
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)

    def _frame(self, ev):
        self.frames.append((time.monotonic(), base64.b64decode(ev["data"])))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:
            pass

    def start(self):
        self.t0 = time.monotonic()
        # Seed with a real screenshot: Chrome only sends screencast frames when the page repaints.
        self.frames.append((self.t0, self.page.screenshot(type="jpeg", quality=92)))
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1})

    def stop(self):
        self.t1 = time.monotonic()
        self.cdp.send("Page.stopScreencast")

    def encode(self, out: Path, duration: float):
        d = BUILD / "frames" / self.name
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*.jpg"):
            f.unlink()
        frames = [(t, b) for t, b in self.frames if t >= self.t0 - 0.5] or self.frames
        lines = ["ffconcat version 1.0"]
        for i, (t, b) in enumerate(frames):
            p = d / f"{i:06d}.jpg"
            p.write_bytes(b)
            nxt = frames[i + 1][0] if i + 1 < len(frames) else self.t1
            start = max(t, self.t0)
            lines += [f"file '{p}'", f"duration {max(nxt - start, 0.001):.4f}"]
        lines.append(f"file '{d / f'{len(frames)-1:06d}.jpg'}'")
        (d / "list.txt").write_text("\n".join(lines))
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(d / "list.txt"),
                        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0b0b0b,fps={FPS},tpad=stop_mode=clone:stop_duration=30,format=yuv420p",
                        "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", str(out)], check=True)
        return out


def cursor_to(page, locator_or_xy, click=False, pause=0.7):
    page.evaluate(CURSOR_JS)
    if isinstance(locator_or_xy, tuple):
        x, y = locator_or_xy
    else:
        box = locator_or_xy.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.evaluate(f"(() => {{ const c=document.getElementById('__demo_cursor'); c.style.left='{x}px'; c.style.top='{y}px'; }})()")
    time.sleep(pause)
    if click:
        page.evaluate("(() => { const c=document.getElementById('__demo_cursor'); c.animate([{transform:'translate(-50%,-50%) scale(1)'},{transform:'translate(-50%,-50%) scale(.6)'},{transform:'translate(-50%,-50%) scale(1)'}],{duration:300}); })()")
        page.mouse.click(x, y)


def smooth_scroll(page, dy, seconds=1.5, selector=None):
    js = f"""(() => new Promise(r => {{
      const el = {('document.querySelector(' + repr(selector) + ')') if selector else 'null'} || document.scrollingElement;
      const start = el.scrollTop, end = start + {dy}, t0 = performance.now(), dur = {seconds * 1000};
      const step = now => {{ const k = Math.min(1, (now - t0) / dur); const e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k+2, 2)/2;
        el.scrollTop = start + (end - start) * e; if (k < 1) requestAnimationFrame(step); else r(); }};
      requestAnimationFrame(step); }}))()"""
    page.evaluate(js)
