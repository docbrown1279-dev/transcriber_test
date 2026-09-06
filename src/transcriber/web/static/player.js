/** Shared audio player: current time + seek; position persists across pages of the same job. */
(function () {
  function fmt(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }

  function storageKey(jobId) {
    return "transcriber.player." + jobId;
  }

  function readState(jobId) {
    if (!jobId) return null;
    try {
      const raw = sessionStorage.getItem(storageKey(jobId));
      if (!raw) return null;
      const data = JSON.parse(raw);
      const t = Number(data.t);
      if (!Number.isFinite(t) || t < 0) return null;
      return { t: t, playing: Boolean(data.playing) };
    } catch (err) {
      return null;
    }
  }

  function writeState(jobId, audio) {
    if (!jobId || !audio) return;
    try {
      sessionStorage.setItem(
        storageKey(jobId),
        JSON.stringify({ t: audio.currentTime || 0, playing: !audio.paused && !audio.ended })
      );
    } catch (err) {
      /* ignore quota / private mode */
    }
  }

  function mount(root) {
    const src = root.getAttribute("data-src") || "";
    const jobId = root.getAttribute("data-job-id") || "";
    root.innerHTML =
      '<div class="row">' +
      '<button type="button" class="btn" data-act="play">Play</button>' +
      '<span data-cur>00:00</span><span>/</span><span data-dur>00:00</span>' +
      '<input type="range" min="0" max="0" value="0" step="0.1" data-seek />' +
      "</div>" +
      (src
        ? ""
        : '<p class="hint">Плеер: аудиофайл задачи ещё не подключён.</p>');

    const audio = document.createElement("audio");
    audio.preload = "metadata";
    if (src) audio.src = src;

    const cur = root.querySelector("[data-cur]");
    const dur = root.querySelector("[data-dur]");
    const seek = root.querySelector("[data-seek]");
    const playBtn = root.querySelector('[data-act="play"]');
    let restored = false;
    let lastSave = 0;

    function persist() {
      const now = Date.now();
      if (now - lastSave < 400) return;
      lastSave = now;
      writeState(jobId, audio);
    }

    function sync() {
      cur.textContent = fmt(audio.currentTime);
      if (Number.isFinite(audio.duration)) {
        dur.textContent = fmt(audio.duration);
        seek.max = String(audio.duration);
      }
      seek.value = String(audio.currentTime || 0);
    }

    function applySaved() {
      if (restored) return;
      const saved = readState(jobId);
      if (!saved) {
        restored = true;
        return;
      }
      const cap = Number.isFinite(audio.duration) ? audio.duration : saved.t;
      audio.currentTime = Math.min(saved.t, Math.max(0, cap));
      restored = true;
      sync();
      if (saved.playing && src) {
        audio.play().then(function () {
          playBtn.textContent = "Pause";
        }).catch(function () {
          playBtn.textContent = "Play";
        });
      }
    }

    playBtn.addEventListener("click", () => {
      if (!src) {
        playBtn.textContent = "Нет файла";
        return;
      }
      if (audio.paused) {
        audio.play();
        playBtn.textContent = "Pause";
      } else {
        audio.pause();
        playBtn.textContent = "Play";
      }
      writeState(jobId, audio);
    });
    seek.addEventListener("input", () => {
      audio.currentTime = Number(seek.value);
      sync();
      writeState(jobId, audio);
    });
    audio.addEventListener("timeupdate", function () {
      sync();
      persist();
    });
    audio.addEventListener("pause", function () {
      writeState(jobId, audio);
    });
    audio.addEventListener("play", function () {
      playBtn.textContent = "Pause";
      writeState(jobId, audio);
    });
    audio.addEventListener("loadedmetadata", function () {
      applySaved();
      sync();
    });
    window.addEventListener("pagehide", function () {
      writeState(jobId, audio);
    });
    root.appendChild(audio);
  }

  document.querySelectorAll("#player-root, .player[data-src]").forEach(mount);
})();
