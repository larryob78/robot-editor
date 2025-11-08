const state = {
  projects: [],
  selectedId: null,
  poll: null,
};

const uploadForm = document.getElementById("upload-form");
const projectsList = document.getElementById("projects-list");
const projectTemplate = document.getElementById("project-item-template");
const previewEl = document.getElementById("preview");
const instructionInput = document.getElementById("instruction-input");
const applyButton = document.getElementById("apply-instruction");
const refreshButton = document.getElementById("refresh-preview");
const exportMp4Button = document.getElementById("export-mp4");
const exportMovButton = document.getElementById("export-mov");
const operationsList = document.getElementById("operations");
const statusEl = document.getElementById("status");
const editorTitle = document.getElementById("editor-title");
const previewToggle = document.getElementById("preview-toggle");
const trimFirstButton = document.getElementById("trim-first");
const trimLastButton = document.getElementById("trim-last");
const trimRangeButton = document.getElementById("trim-range");
const splitClipButton = document.getElementById("split-clip");
const quickButtons = [trimFirstButton, trimLastButton, trimRangeButton, splitClipButton];

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || response.statusText);
  }
  return response.headers.get("content-type")?.includes("application/json")
    ? response.json()
    : response;
}

function setStatus(message) {
  statusEl.textContent = message ?? "";
}

function stopPolling() {
  if (state.poll) {
    clearInterval(state.poll);
    state.poll = null;
  }
}

function renderOperations(project) {
  operationsList.innerHTML = "";
  if (!project || !project.operations.length) {
    const li = document.createElement("li");
    li.textContent = "No operations applied yet.";
    operationsList.appendChild(li);
    return;
  }
  project.operations.forEach((op) => {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${op.type}</strong> — ${op.description}`;
    operationsList.appendChild(li);
  });
}

function renderProjects() {
  projectsList.innerHTML = "";
  state.projects.forEach((project) => {
    const node = projectTemplate.content.firstElementChild.cloneNode(true);
    const button = node.querySelector("button");
    const pill = node.querySelector(".status-pill");
    button.textContent = project.name;
    pill.textContent = project.status;
    if (project.id === state.selectedId) {
      button.classList.add("active");
    }
    button.addEventListener("click", () => selectProject(project.id));
    projectsList.appendChild(node);
  });
}

function setEditorEnabled(project) {
  const hasProject = Boolean(project);
  const busy = project?.status === "processing" || project?.status === "queued";
  applyButton.disabled = !hasProject || busy;
  refreshButton.disabled = !hasProject || !project?.preview_url;
  exportMp4Button.disabled = !hasProject;
  exportMovButton.disabled = !hasProject;
  quickButtons.forEach((button) => {
    button.disabled = !hasProject || busy;
  });
}

async function refreshProjects(selectLatest = false) {
  try {
    const data = await fetchJSON("/api/projects");
    state.projects = data.projects;
    renderProjects();
    if (selectLatest && state.projects.length) {
      await selectProject(state.projects[state.projects.length - 1].id);
    } else if (state.selectedId) {
      const existing = state.projects.find((p) => p.id === state.selectedId);
      if (existing) {
        updateEditor(existing);
      }
    }
  } catch (err) {
    setStatus(err.message || "Unable to load projects.");
  }
}

function updateEditor(project) {
  if (!project) {
    editorTitle.textContent = "Editor";
    previewEl.removeAttribute("src");
    setEditorEnabled(null);
    renderOperations(null);
    return;
  }

  editorTitle.textContent = `Editing: ${project.name}`;
  setEditorEnabled(project);
  if (project.preview_url) {
    const cacheBust = Date.now();
    previewEl.src = `${project.preview_url}?t=${cacheBust}`;
  } else {
    previewEl.removeAttribute("src");
  }
  renderOperations(project);
  if (project.status === "processing" || project.status === "queued") {
    setStatus("Processing...");
  } else if (project.status === "error") {
    setStatus("Last instruction failed. Try again.");
  } else {
    setStatus("Ready");
  }
}

async function selectProject(projectId) {
  stopPolling();
  state.selectedId = projectId;
  renderProjects();
  try {
    const data = await fetchJSON(`/api/projects/${projectId}`);
    const index = state.projects.findIndex((p) => p.id === projectId);
    if (index !== -1) {
      state.projects[index] = data.project;
      renderProjects();
    }
    updateEditor(data.project);
  } catch (err) {
    setStatus(err.message || "Unable to load project details.");
  }
}

async function handleUpload(event) {
  event.preventDefault();
  const formData = new FormData(uploadForm);
  if (!formData.get("file")) {
    setStatus("Select a video file first.");
    return;
  }
  setStatus("Uploading...");
  try {
    await fetchJSON("/api/projects", {
      method: "POST",
      body: formData,
    });
    uploadForm.reset();
    await refreshProjects(true);
    setStatus("Upload complete.");
  } catch (err) {
    setStatus(err.message);
  }
}

async function sendInstructionPrompt(prompt, preview) {
  if (!state.selectedId) {
    setStatus("Select a project first.");
    return;
  }
  const payload = {
    prompt,
    preview: typeof preview === "boolean" ? preview : previewToggle.checked,
  };
  setStatus("Submitting instruction...");
  try {
    const response = await fetchJSON(`/api/projects/${state.selectedId}/instructions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus("Processing instruction...");
    if (response.job?.job_id) {
      pollJob(response.job.job_id, state.selectedId);
    }
    if (response.project) {
      updateEditor(response.project);
    }
  } catch (err) {
    setStatus(err.message);
  }
}

async function applyInstruction() {
  if (!state.selectedId) {
    setStatus("Select a project first.");
    return;
  }
  const prompt = instructionInput.value.trim();
  if (!prompt) {
    setStatus("Enter an instruction to apply.");
    return;
  }
  instructionInput.value = "";
  await sendInstructionPrompt(prompt, previewToggle.checked);
}

function pollJob(jobId, projectId) {
  stopPolling();
  state.poll = setInterval(async () => {
    try {
      const status = await fetchJSON(`/api/jobs/${jobId}`);
      if (status.status === "completed" || status.status === "failed") {
        stopPolling();
        if (status.status === "completed") {
          setStatus("Instruction applied.");
          await refreshProjects();
          if (projectId === state.selectedId) {
            const latest = state.projects.find((p) => p.id === projectId);
            if (latest) {
              updateEditor(latest);
            }
          }
        } else {
          setStatus(status.error || "Instruction failed.");
        }
      }
    } catch (err) {
      stopPolling();
      setStatus(err.message);
    }
  }, 1500);
}

async function refreshPreview() {
  if (!state.selectedId) return;
  const cacheBust = Date.now();
  const project = state.projects.find((p) => p.id === state.selectedId);
  if (project?.preview_url) {
    previewEl.src = `${project.preview_url}?t=${cacheBust}`;
  } else {
    previewEl.src = `/api/projects/${state.selectedId}/preview?t=${cacheBust}`;
  }
}

async function exportProject(format) {
  if (!state.selectedId) return;
  setStatus(`Exporting ${format.toUpperCase()}...`);
  try {
    const response = await fetch(`/api/projects/${state.selectedId}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `project-${state.selectedId}.${format}`;
    link.click();
    URL.revokeObjectURL(url);
    setStatus("Export ready.");
  } catch (err) {
    setStatus(err.message);
  }
}

function promptSeconds(message) {
  const input = window.prompt(message);
  if (input === null) {
    return null;
  }
  const value = Number.parseFloat(input.trim());
  if (Number.isNaN(value) || value <= 0) {
    setStatus("Enter a positive number of seconds.");
    return null;
  }
  return value;
}

async function handleTrimFirst() {
  const seconds = promptSeconds("Keep the first how many seconds?");
  if (seconds === null) return;
  await sendInstructionPrompt(`Trim the video to first ${seconds} seconds.`, previewToggle.checked);
}

async function handleTrimLast() {
  const seconds = promptSeconds("Keep the last how many seconds?");
  if (seconds === null) return;
  await sendInstructionPrompt(`Trim the video to last ${seconds} seconds.`, previewToggle.checked);
}

async function handleTrimRange() {
  const start = promptSeconds("Trim range start (seconds)");
  if (start === null) return;
  const end = promptSeconds("Trim range end (seconds)");
  if (end === null) return;
  if (start === end) {
    setStatus("Start and end must be different.");
    return;
  }
  await sendInstructionPrompt(`Trim between ${start} and ${end} seconds.`, previewToggle.checked);
}

async function handleSplitClip() {
  const seconds = promptSeconds("Split the clip at which second?");
  if (seconds === null) return;
  await sendInstructionPrompt(`Split the clip at ${seconds} seconds.`, previewToggle.checked);
}

uploadForm.addEventListener("submit", handleUpload);
applyButton.addEventListener("click", applyInstruction);
refreshButton.addEventListener("click", refreshPreview);
exportMp4Button.addEventListener("click", () => exportProject("mp4"));
exportMovButton.addEventListener("click", () => exportProject("mov"));
trimFirstButton.addEventListener("click", handleTrimFirst);
trimLastButton.addEventListener("click", handleTrimLast);
trimRangeButton.addEventListener("click", handleTrimRange);
splitClipButton.addEventListener("click", handleSplitClip);

refreshProjects();
