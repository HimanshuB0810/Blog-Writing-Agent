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
const resultActions = document.getElementById("result-actions");
const reviewPanel = document.getElementById("review-panel");
const reviewQuestion = document.getElementById("review-question");
const reviewInstruction = document.getElementById("review-instruction");
const reviewFeedback = document.getElementById("review-feedback");
const reviewStatus = document.getElementById("review-status");
const approveButton = document.getElementById("approve-btn");
const reviseButton = document.getElementById("revise-btn");

const stageOrder = ["planning", "research", "writing", "images", "finalizing", "review"];
const stageIndex = Object.fromEntries(stageOrder.map((stage, index) => [stage, index]));
let currentJobId = null;
let reviewSubmissionInProgress = false;

function updateCharCount() {
  charCount.textContent = `${topicInput.value.length} / 500`;
}

function resetUI() {
  progressSection.classList.remove("hidden");
  resultSection.classList.add("hidden");
  reviewPanel.classList.add("hidden");
  resultActions.classList.add("hidden");
  errorSection.classList.add("hidden");
  eventLog.innerHTML = "";
  reviewFeedback.value = "";
  reviewStatus.textContent = "";
  currentJobId = null;
  reviewSubmissionInProgress = false;

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
  time.textContent = `[${payload.timestamp || "--:--:--"}]`;

  const message = document.createElement("span");
  message.className = "event-message";
  message.textContent = payload.message || "";

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

function renderMarkdown(jobId, markdown) {
  const prepared = prepareMarkdown(markdown || "", jobId);
  const rendered = marked.parse(prepared, {
    gfm: true,
    breaks: false,
  });

  blogPreview.innerHTML = DOMPurify.sanitize(rendered);
}

function markWorkflowComplete() {
  runStatus.textContent = "Completed";

  document.querySelectorAll(".workflow-step").forEach((step) => {
    step.classList.remove("active");
    step.classList.add("done");
    step.querySelector(".step-icon").textContent = "✓";
  });
}

function renderResult(jobId, data) {
  currentJobId = jobId;
  renderMarkdown(jobId, data.markdown || "");

  if (data.download_url) downloadMd.href = data.download_url;
  if (data.package_url) downloadPackage.href = data.package_url;

  reviewPanel.classList.add("hidden");
  resultActions.classList.remove("hidden");
  resultSection.classList.remove("hidden");
  reviewStatus.textContent = "";
  markWorkflowComplete();
}

function showReview(jobId, data) {
  currentJobId = jobId;
  renderMarkdown(jobId, data.blog || data.markdown || "");

  reviewQuestion.textContent = data.question || "Do you approve this blog?";
  reviewInstruction.textContent = data.instruction || "Review the content. Approve it or request specific changes.";
  reviewFeedback.value = "";
  reviewStatus.textContent = "";

  resultSection.classList.remove("hidden");
  reviewPanel.classList.remove("hidden");
  resultActions.classList.add("hidden");
  runStatus.textContent = "Awaiting review";
  setStage("review");
}

async function showResult(jobId) {
  const response = await fetch(`/api/blog/${encodeURIComponent(jobId)}`);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Unable to load generated blog.");
  }

  if (data.status === "awaiting_review") {
    showReview(jobId, data);
    return;
  }

  renderResult(jobId, data);
}

function connectToStream(streamUrl, jobId) {
  return new Promise((resolve, reject) => {
    const source = new EventSource(streamUrl);

    source.onmessage = async (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch (error) {
        source.close();
        reject(new Error("The server sent an invalid progress event."));
        return;
      }

      appendEvent(payload);

      if (payload.stage === "review" && payload.status === "awaiting_review") {
        source.close();
        showReview(jobId, payload.data || {});
        resolve();
        return;
      }

      if (payload.stage === "complete" && payload.status === "completed") {
        source.close();
        try {
          if (payload.data && payload.data.markdown) {
            renderResult(jobId, {
              markdown: payload.data.markdown,
              download_url: payload.data.download_url,
              package_url: payload.data.package_url,
            });
          } else {
            await showResult(jobId);
          }
          resolve();
        } catch (error) {
          reject(error);
        }
        return;
      }

      if (payload.stage === "error" || payload.status === "failed") {
        source.close();
        reject(new Error(payload.message || "Blog generation failed."));
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

async function submitReview(approved) {
  if (!currentJobId || reviewSubmissionInProgress) return;

  const feedback = reviewFeedback.value.trim();

  if (!approved && !feedback) {
    reviewStatus.textContent = "Enter revision suggestions before requesting changes.";
    reviewFeedback.focus();
    return;
  }

  reviewSubmissionInProgress = true;
  approveButton.disabled = true;
  reviseButton.disabled = true;
  reviewStatus.textContent = approved
    ? "Submitting approval..."
    : "Revising the blog with your feedback...";

  try {
    const response = await fetch(
      `/api/blog/${encodeURIComponent(currentJobId)}/review`,
      {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({approved, feedback}),
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Unable to submit review.");
    }

    if (data.status === "awaiting_review") {
      showReview(currentJobId, data);
      reviewStatus.textContent = "Revised blog ready. Review the new version.";
    } else if (data.status === "completed") {
      renderResult(currentJobId, data);
    } else {
      throw new Error("Unexpected response from the review endpoint.");
    }
  } catch (error) {
    reviewStatus.textContent = error.message || "Unable to submit review.";
  } finally {
    reviewSubmissionInProgress = false;
    approveButton.disabled = false;
    reviseButton.disabled = false;
  }
}

approveButton.addEventListener("click", () => submitReview(true));
reviseButton.addEventListener("click", () => submitReview(false));

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

    currentJobId = data.id;
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
