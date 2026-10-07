const topicInput = document.getElementById("topic");
const charCount = document.getElementById("char-count");
const generateButton = document.getElementById("generate-btn");
const progressSection = document.getElementById("progress-section");
const resultSection = document.getElementById("result-section");
const errorSection = document.getElementById("error-section");
const errorMessage = document.getElementById("error-message");
const eventLog = document.getElementById("event-log");
const runStatus = document.getElementById("run-status");
const blogPreview = document.getElementById("blog-preview");
const downloadMd = document.getElementById("download-md");
const downloadPackage = document.getElementById("download-package");

const stageOrder = ["planning", "research", "writing", "images", "finalizing"];
const stageIndex = Object.fromEntries(stageOrder.map((stage, index) => [stage, index]));

function updateCharCount() {
  charCount.textContent = `${topicInput.value.length} / 500`;
}

function resetUI() {
  progressSection.classList.remove("hidden");
  resultSection.classList.add("hidden");
  errorSection.classList.add("hidden");
  eventLog.innerHTML = "";

  document.querySelectorAll(".workflow-step").forEach((step) => {
    step.classList.remove("active", "done");
    step.querySelector(".step-icon").textContent = "○";
  });

  runStatus.textContent = "Running";
}

function setStage(stage) {
  const current = stageIndex[stage];
  if (current === undefined) return;

  document.querySelectorAll(".workflow-step").forEach((step) => {
    const index = stageIndex[step.dataset.stage];
    const icon = step.querySelector(".step-icon");
    step.classList.remove("active", "done");

    if (index < current) {
      step.classList.add("done");
      icon.textContent = "✓";
    } else if (index === current) {
      step.classList.add("active");
      icon.textContent = "●";
    }
  });
}

function appendEvent(payload) {
  const row = document.createElement("div");
  row.className = "event";

  const time = document.createElement("span");
  time.className = "event-time";
  time.textContent = `[${payload.timestamp}]`;

  const message = document.createElement("span");
  message.className = "event-message";
  message.textContent = payload.message;

  row.append(time, message);
  eventLog.appendChild(row);
  eventLog.scrollTop = eventLog.scrollHeight;
}

function imageUrl(jobId, src) {
  const clean = src.split("/").pop();
  return window.BLOG_IMAGE_ENDPOINT
    .replace("__JOB_ID__", encodeURIComponent(jobId))
    .replace("__FILE__", encodeURIComponent(clean));
}

function prepareMarkdown(markdown, jobId) {
  return markdown.replace(
    /(!\[[^\]]*\]\()images\/([^\)]+)(\))/g,
    (_, prefix, filename, suffix) => `${prefix}${imageUrl(jobId, filename)}${suffix}`
  );
}

async function showResult(jobId) {
  const response = await fetch(`/api/blog/${jobId}`);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Unable to load generated blog.");
  }

  const prepared = prepareMarkdown(data.markdown || "", jobId);
  const rendered = marked.parse(prepared, {
    gfm: true,
    breaks: false,
  });

  blogPreview.innerHTML = DOMPurify.sanitize(rendered);
  downloadMd.href = data.download_url;
  downloadPackage.href = data.package_url;

  resultSection.classList.remove("hidden");
  runStatus.textContent = "Completed";
  document.querySelectorAll(".workflow-step").forEach((step) => {
    step.classList.remove("active");
    step.classList.add("done");
    step.querySelector(".step-icon").textContent = "✓";
  });
}

function connectToStream(streamUrl, jobId) {
  return new Promise((resolve, reject) => {
    const source = new EventSource(streamUrl);

    source.onmessage = async (event) => {
      const payload = JSON.parse(event.data);
      appendEvent(payload);

      if (payload.stage === "complete" && payload.status === "completed") {
        source.close();
        try {
          await showResult(jobId);
          resolve();
        } catch (error) {
          reject(error);
        }
        return;
      }

      if (payload.stage === "error" || payload.status === "failed") {
        source.close();
        reject(new Error(payload.message));
        return;
      }

      setStage(payload.stage);
    };

    source.onerror = () => {
      source.close();
      reject(new Error("The progress connection was interrupted."));
    };
  });
}

generateButton.addEventListener("click", async () => {
  const topic = topicInput.value.trim();

  if (!topic) {
    errorSection.classList.remove("hidden");
    errorMessage.textContent = "Enter a blog topic first.";
    topicInput.focus();
    return;
  }

  generateButton.disabled = true;
  generateButton.textContent = "Generating...";
  resetUI();

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({topic}),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Unable to start generation.");
    }

    await connectToStream(data.stream_url, data.id);
  } catch (error) {
    errorSection.classList.remove("hidden");
    errorMessage.textContent = error.message || "An unexpected error occurred.";
    runStatus.textContent = "Failed";
  } finally {
    generateButton.disabled = false;
    generateButton.textContent = "Generate Blog";
  }
});

topicInput.addEventListener("input", updateCharCount);
updateCharCount();