const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const sampleBtn = document.getElementById("sampleBtn");
const fileNameEl = document.getElementById("fileName");
const statusEl = document.getElementById("status");
const resultWrap = document.getElementById("resultWrap");
const resultEl = document.getElementById("result");

function setStatus(message, { error = false, busy = false } = {}) {
  if (!message) {
    statusEl.hidden = true;
    statusEl.textContent = "";
    return;
  }
  statusEl.hidden = false;
  statusEl.classList.toggle("error", error);
  statusEl.innerHTML = "";
  if (busy) {
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    statusEl.appendChild(spinner);
  }
  statusEl.appendChild(document.createTextNode(message));
}

function showResult(text) {
  resultWrap.hidden = false;
  resultEl.textContent = text && text.length ? text : "(no speech detected)";
}

function setBusy(busy) {
  sampleBtn.disabled = busy;
  dropzone.style.pointerEvents = busy ? "none" : "";
}

async function postAudio(url, formData) {
  setBusy(true);
  resultWrap.hidden = true;
  setStatus("Transcribing audio…", { busy: true });
  try {
    const response = await fetch(url, { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Transcription failed.");
    }
    setStatus(data.message || "Done.", { error: false });
    showResult(data.transcript);
  } catch (err) {
    setStatus(err.message || "Something went wrong.", { error: true });
  } finally {
    setBusy(false);
  }
}

function handleFile(file) {
  if (!file) return;
  fileNameEl.textContent = file.name;
  const formData = new FormData();
  formData.append("audio", file);
  postAudio("/transcribe", formData);
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});
fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  handleFile(file);
});

sampleBtn.addEventListener("click", () => {
  fileNameEl.textContent = "go-forward.wav (demo)";
  postAudio("/transcribe-sample", new FormData());
});
