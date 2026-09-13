/** Demo UI: URL stub hint, staging preload, progress polling, dictionary/summary stubs, chapter edit chrome. */
(function () {
  const urlInput = document.getElementById("url-input");
  const urlHint = document.getElementById("url-hint");
  if (urlInput && urlHint) {
    urlInput.addEventListener("input", () => {
      const v = urlInput.value.trim();
      if (!v) {
        urlHint.textContent = "Сейчас принимается только файл.";
        return;
      }
      const params = new URLSearchParams({ url: v });
      fetch("/url-stub?" + params.toString())
        .then((r) => r.json())
        .then((data) => {
          urlHint.textContent = data.message || "";
        })
        .catch(() => {
          urlHint.textContent = "Не удалось классифицировать ссылку.";
        });
    });
  }

  const uploadForm = document.getElementById("upload-form");
  const audioInput = document.getElementById("audio-input");
  const stagingIdInput = document.getElementById("staging-id");
  const stagingStatus = document.getElementById("staging-status");
  const stagingTrack = document.getElementById("staging-track");
  const stagingBar = document.getElementById("staging-bar");
  const uploadSubmit = document.getElementById("upload-submit");
  let stagingXhr = null;
  let stagingReady = false;

  function setStagingUi(pct, text) {
    if (stagingStatus) stagingStatus.textContent = text || "";
    if (stagingTrack) {
      if (pct == null) {
        stagingTrack.classList.add("hidden");
      } else {
        stagingTrack.classList.remove("hidden");
        if (stagingBar) stagingBar.style.width = Math.max(0, Math.min(100, pct)) + "%";
      }
    }
  }

  function clearStagingToken() {
    stagingReady = false;
    if (stagingIdInput) stagingIdInput.value = "";
    if (audioInput) audioInput.required = true;
  }

  function abortStaging() {
    if (stagingXhr) {
      try {
        stagingXhr.abort();
      } catch (_) {}
      stagingXhr = null;
    }
  }

  function preloadFile(file) {
    abortStaging();
    const prevId = stagingIdInput && stagingIdInput.value;
    clearStagingToken();
    if (prevId) {
      fetch("/staging/" + prevId, { method: "DELETE" }).catch(() => {});
    }
    if (!file) {
      setStagingUi(null, "");
      return;
    }
    setStagingUi(0, "Загрузка файла на сервер…");
    if (uploadSubmit) uploadSubmit.disabled = true;
    const fd = new FormData();
    fd.append("audio", file);
    const xhr = new XMLHttpRequest();
    stagingXhr = xhr;
    xhr.open("POST", "/staging");
    xhr.upload.onprogress = function (ev) {
      if (!ev.lengthComputable) return;
      const pct = Math.round((ev.loaded / ev.total) * 100);
      setStagingUi(pct, "Загрузка файла… " + pct + "%");
    };
    xhr.onload = function () {
      stagingXhr = null;
      if (uploadSubmit) uploadSubmit.disabled = false;
      let data = null;
      try {
        data = JSON.parse(xhr.responseText || "{}");
      } catch (_) {}
      if (xhr.status >= 200 && xhr.status < 300 && data && data.staging_id) {
        if (stagingIdInput) stagingIdInput.value = data.staging_id;
        stagingReady = true;
        if (audioInput) audioInput.required = false;
        setStagingUi(100, "Файл на сервере — можно запускать обработку.");
        return;
      }
      clearStagingToken();
      const msg =
        (data && (data.detail || data.message || data.error)) ||
        "Не удалось загрузить файл. Попробуйте ещё раз.";
      setStagingUi(null, typeof msg === "string" ? msg : "Не удалось загрузить файл.");
    };
    xhr.onerror = function () {
      stagingXhr = null;
      if (uploadSubmit) uploadSubmit.disabled = false;
      clearStagingToken();
      setStagingUi(null, "Не удалось загрузить файл. Проверьте сеть.");
    };
    xhr.send(fd);
  }

  if (audioInput) {
    audioInput.addEventListener("change", () => {
      const file = audioInput.files && audioInput.files[0];
      preloadFile(file || null);
    });
  }

  if (uploadForm) {
    uploadForm.addEventListener("submit", (ev) => {
      if (!stagingReady || !stagingIdInput || !stagingIdInput.value) {
        return; // native multipart submit
      }
      ev.preventDefault();
      if (uploadSubmit) uploadSubmit.disabled = true;
      setStagingUi(100, "Запускаем обработку…");
      const fd = new FormData();
      fd.append("staging_id", stagingIdInput.value);
      const urlField = uploadForm.querySelector('input[name="url"]');
      if (urlField && urlField.value) fd.append("url", urlField.value);
      fetch("/jobs", {
        method: "POST",
        body: fd,
        headers: { Accept: "application/json" },
        redirect: "follow",
      })
        .then(async (r) => {
          if (r.redirected && r.url) {
            window.location.href = r.url;
            return;
          }
          const data = await r.json().catch(() => ({}));
          if (r.ok && data.job_id) {
            let loc = "/jobs/" + data.job_id;
            if (data.trim && data.trim.will_trim) loc += "?trim=1";
            window.location.href = loc;
            return;
          }
          if (uploadSubmit) uploadSubmit.disabled = false;
          const msg =
            (data && (data.detail || data.message || data.error)) ||
            "Не удалось создать задачу.";
          setStagingUi(null, typeof msg === "string" ? msg : "Не удалось создать задачу.");
        })
        .catch(() => {
          if (uploadSubmit) uploadSubmit.disabled = false;
          setStagingUi(null, "Не удалось создать задачу. Попробуйте ещё раз.");
        });
    });
  }

  const progressRoot = document.querySelector("[data-progress]");
  if (progressRoot) {
    const jobId = progressRoot.getAttribute("data-job-id");
    const createdRaw = progressRoot.getAttribute("data-created");
    const bar = document.getElementById("progress-bar");
    const statusEl = document.getElementById("status-label");
    const etaEl = document.getElementById("eta-label");
    const errEl = document.getElementById("job-error");
    const block = document.getElementById("progress-block");
    const elapsedEl = document.getElementById("elapsed-label");
    const pollMs = 1500;
    let timer = null;
    let elapsedTimer = null;
    let failed = false;
    let freezeElapsed = progressRoot.getAttribute("data-state") === "failed"
      || progressRoot.getAttribute("data-state") === "done";

    function formatElapsed(sec) {
      sec = Math.max(0, Math.floor(sec));
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = sec % 60;
      if (h) return h + " ч " + m + " мин " + s + " с";
      if (m) return m + " мин " + s + " с";
      return s + " с";
    }

    function tickElapsed() {
      if (freezeElapsed || !elapsedEl || !createdRaw) return;
      const start = Date.parse(createdRaw);
      if (Number.isNaN(start)) return;
      elapsedEl.textContent = formatElapsed((Date.now() - start) / 1000);
    }

    function stopElapsedTick() {
      freezeElapsed = true;
      if (elapsedTimer) {
        window.clearInterval(elapsedTimer);
        elapsedTimer = null;
      }
    }

    function render(data) {
      const pct = Math.max(0, Math.min(100, Math.round(data.pct || 0)));
      if (bar) bar.style.width = pct + "%";
      if (statusEl && data.status_label) {
        statusEl.textContent = data.status_label;
      }
      if (etaEl) {
        etaEl.textContent = data.eta_label || "";
      }
      if (typeof data.elapsed_sec === "number" && elapsedEl) {
        elapsedEl.textContent = formatElapsed(data.elapsed_sec);
      }
      if (data.elapsed_running === false) {
        stopElapsedTick();
      }
      if (errEl) {
        if (data.error) {
          errEl.textContent = data.error;
          errEl.classList.remove("hidden");
          if (block) block.classList.add("hidden");
        } else {
          errEl.classList.add("hidden");
          if (block) block.classList.remove("hidden");
        }
      }
      if (data.early_ready || data.state === "done") {
        stopElapsedTick();
        window.location.href = "/jobs/" + jobId + "/result";
        return;
      }
      if (data.state === "failed") {
        failed = true;
        stopElapsedTick();
        if (timer) window.clearInterval(timer);
      }
    }

    function tick() {
      if (failed) return;
      fetch("/jobs/" + jobId + "/events")
        .then((r) => r.json())
        .then(render)
        .catch(() => {});
    }
    tick();
    timer = window.setInterval(tick, pollMs);
    if (!freezeElapsed) {
      elapsedTimer = window.setInterval(tickElapsed, 1000);
      tickElapsed();
    }
  }

  const resultRoot = document.querySelector("[data-result-poll]");
  if (resultRoot && resultRoot.getAttribute("data-state") === "running") {
    const jobId = resultRoot.getAttribute("data-job-id");
    const pollMs = 2000;
    const liveStatus = document.getElementById("live-status-label");
    const liveEta = document.getElementById("live-eta-label");
    let speakersFinal = resultRoot.getAttribute("data-speakers-finalized") === "1";
    let timer = null;
    let lastLabel = "";
    function tickResult() {
      fetch("/jobs/" + jobId + "/events")
        .then((r) => r.json())
        .then((data) => {
          if (liveStatus && data.status_label) {
            liveStatus.textContent = data.status_label;
            lastLabel = data.status_label;
          } else if (liveStatus && !lastLabel) {
            liveStatus.textContent = "Обработка следующих фрагментов…";
          }
          if (liveEta) {
            liveEta.textContent = data.eta_label || "";
          }
          const nowFinal = data.speakers_finalized === true;
          if (data.state === "done" || (nowFinal && !speakersFinal)) {
            if (timer) window.clearInterval(timer);
            window.location.reload();
          }
        })
        .catch(() => {});
    }
    tickResult();
    timer = window.setInterval(tickResult, pollMs);
  }

  const btnDict = document.getElementById("btn-dict");
  if (btnDict) {
    btnDict.addEventListener("click", () => {
      const parts = window.location.pathname.split("/");
      const jobId = parts[2];
      fetch("/jobs/" + jobId + "/actions/dictionary", { method: "POST" })
        .then((r) => r.json())
        .then((data) => {
          const el = document.getElementById("dict-msg");
          if (el) el.textContent = data.message || "";
        });
    });
  }

  const btnSummary = document.getElementById("btn-summary");
  if (btnSummary) {
    btnSummary.addEventListener("click", () => {
      const parts = window.location.pathname.split("/");
      const jobId = parts[2];
      const body = new URLSearchParams();
      const select = document.getElementById("summary-template");
      body.set("template", select && select.value ? select.value : "meeting_report/v1");
      const msg = document.getElementById("summary-msg");
      const original = btnSummary.textContent;
      btnSummary.disabled = true;
      btnSummary.textContent = "Собираем саммари…";
      if (msg) msg.textContent = "Это может занять около минуты.";
      fetch("/jobs/" + jobId + "/actions/summary", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      })
        .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
        .then(({ ok, data }) => {
          if (data && data.reload) {
            window.location.href = "/jobs/" + jobId + "/result?summary=1";
            return;
          }
          btnSummary.disabled = false;
          btnSummary.textContent = original;
          if (msg) msg.textContent = (data && (data.message || data.error)) || "Не удалось собрать саммари, попробуйте позже.";
          if (!ok && msg && data && data.error) msg.textContent = data.error;
        })
        .catch(() => {
          btnSummary.disabled = false;
          btnSummary.textContent = original;
          if (msg) msg.textContent = "Не удалось собрать саммари, попробуйте позже.";
        });
    });
  }

  const view = document.getElementById("chapter-view");
  const edit = document.getElementById("chapter-edit");
  const btnEdit = document.getElementById("btn-edit");
  const btnSave = document.getElementById("btn-save");
  const btnCancel = document.getElementById("btn-cancel");
  const msg = document.getElementById("edit-msg");
  if (view && edit && btnEdit && btnSave && btnCancel) {
    function editAreas() {
      return Array.from(edit.querySelectorAll("textarea[name='seg_text']"));
    }
    function editSpeakers() {
      return Array.from(edit.querySelectorAll("select[name='seg_speaker']"));
    }
    let snapshot = editAreas().map((el) => el.value);
    let snapshotSpeakers = editSpeakers().map((el) => el.value);
    function setEditing(on) {
      view.classList.toggle("hidden", on);
      edit.classList.toggle("hidden", !on);
      btnEdit.classList.toggle("hidden", on);
      btnSave.classList.toggle("hidden", !on);
      btnCancel.classList.toggle("hidden", !on);
    }
    btnEdit.addEventListener("click", () => {
      snapshot = editAreas().map((el) => el.value);
      snapshotSpeakers = editSpeakers().map((el) => el.value);
      setEditing(true);
      if (msg) msg.textContent = "";
    });
    btnCancel.addEventListener("click", () => {
      editAreas().forEach((el, i) => {
        el.value = snapshot[i] ?? "";
      });
      editSpeakers().forEach((el, i) => {
        if (snapshotSpeakers[i] != null) el.value = snapshotSpeakers[i];
      });
      setEditing(false);
      if (msg) msg.textContent = "Изменения отменены.";
    });
  }
})();
