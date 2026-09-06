/** Shared stub audio player: current time + seek (no media until data-src is set). */
(function () {
  function fmt(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }

  function mount(root) {
    const src = root.getAttribute("data-src") || "";
    root.innerHTML =
      '<div class="row">' +
      '<button type="button" class="btn" data-act="play">Play</button>' +
      '<span data-cur>00:00</span><span>/</span><span data-dur>00:00</span>' +
      '<input type="range" min="0" max="0" value="0" step="0.1" data-seek />' +
      "</div>" +
      (src
        ? ""
        : '<p class="hint">Плеер-заглушка: аудиофайл задачи ещё не подключён.</p>');

    const audio = document.createElement("audio");
    audio.preload = "metadata";
    if (src) audio.src = src;

    const cur = root.querySelector("[data-cur]");
    const dur = root.querySelector("[data-dur]");
    const seek = root.querySelector("[data-seek]");
    const playBtn = root.querySelector('[data-act="play"]');

    function sync() {
      cur.textContent = fmt(audio.currentTime);
      if (Number.isFinite(audio.duration)) {
        dur.textContent = fmt(audio.duration);
        seek.max = String(audio.duration);
      }
      seek.value = String(audio.currentTime || 0);
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
    });
    seek.addEventListener("input", () => {
      audio.currentTime = Number(seek.value);
      sync();
    });
    audio.addEventListener("timeupdate", sync);
    audio.addEventListener("loadedmetadata", sync);
    root.appendChild(audio);
  }

  document.querySelectorAll("#player-root, .player[data-src]").forEach(mount);
})();
