"use strict";

const API_BASE = document.querySelector('meta[name=api-base]').content.replace(/\/$/, "");
const API_KEY_STORAGE_KEY = "jobQueueApiKey";
const JOBS_POLL_MS = 3000;
const METRICS_POLL_MS = 10000;
const API_REQUEST_TIMEOUT_MS = 90000;

const elements = {
  apiHealth: document.querySelector("#api-health"),
  apiHealthLabel: document.querySelector("#api-health-label"),
  apiKeyButton: document.querySelector("#api-key-button"),
  errorBanner: document.querySelector("#error-banner"),
  form: document.querySelector("#job-form"),
  type: document.querySelector("#job-type"),
  payload: document.querySelector("#job-payload"),
  payloadError: document.querySelector("#payload-error"),
  forceFail: document.querySelector("#force-fail"),
  submitButton: document.querySelector("#submit-button"),
  statusFilter: document.querySelector("#status-filter"),
  refreshButton: document.querySelector("#refresh-button"),
  jobsBody: document.querySelector("#jobs-body"),
  emptyState: document.querySelector("#empty-state"),
  jobsLoading: document.querySelector("#jobs-loading"),
  jobsCount: document.querySelector("#jobs-count"),
  jobsFooter: document.querySelector("#jobs-footer"),
  metricsGrid: document.querySelector("#metrics-grid"),
  queueDepth: document.querySelector("#metric-queue-depth"),
  successRate: document.querySelector("#metric-success-rate"),
  workerAge: document.querySelector("#metric-worker-age"),
  workerCaption: document.querySelector("#metric-worker-caption"),
  workerMetric: document.querySelector("#metric-worker-age").closest(".metric-card"),
  avgDuration: document.querySelector("#metric-avg-duration"),
  metricsUpdated: document.querySelector("#metrics-updated"),
  toast: document.querySelector("#toast"),
};

let jobsTimer = null;
let metricsTimer = null;
let toastTimer = null;
let jobsRequestActive = false;
let metricsRequestActive = false;
let toastSequence = 0;

function getApiKey() {
  try {
    return sessionStorage.getItem(API_KEY_STORAGE_KEY) || "";
  } catch {
    showError("This browser session cannot store the API key. Enable session storage and reload.");
    return "";
  }
}

function askForApiKey() {
  if (getApiKey()) return true;
  const value = window.prompt("Enter the API key for this browser session:");
  if (!value || !value.trim()) {
    showError("An API key is required to load jobs and metrics.");
    return false;
  }
  try {
    sessionStorage.setItem(API_KEY_STORAGE_KEY, value.trim());
    clearError();
    return true;
  } catch {
    showError("This browser session cannot store the API key. Enable session storage and reload.");
    return false;
  }
}

function showError(message) {
  elements.errorBanner.textContent = message;
  elements.errorBanner.hidden = false;
}

function clearError() {
  elements.errorBanner.textContent = "";
  elements.errorBanner.hidden = true;
}

function showToast(message, isError = false) {
  toastSequence += 1;
  const sequence = toastSequence;
  elements.toast.textContent = message;
  elements.toast.classList.toggle("is-error", isError);
  elements.toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    if (sequence === toastSequence) elements.toast.hidden = true;
  }, 5200);
}

function handleHttpError(status) {
  if (status === 401) {
    showError("Invalid API key");
    return;
  }
  if (status === 429) {
    showError("Rate limited — wait 60s");
    return;
  }
  if (status === 503) {
    showError("API unreachable (Render may be waking up)");
    return;
  }
  showError(`The API returned an error (${status}).`);
}

async function requestJson(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.auth !== false) {
    const apiKey = getApiKey();
    if (!apiKey) throw new Error("API_KEY_REQUIRED");
    headers.set("X-API-Key", apiKey);
  }
  if (options.body !== undefined) headers.set("Content-Type", "application/json");

  let response;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), API_REQUEST_TIMEOUT_MS);
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: controller.signal });
  } catch {
    throw new Error("API_UNREACHABLE");
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const error = new Error(`HTTP_${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  try {
    return await response.json();
  } catch {
    throw new Error("INVALID_API_RESPONSE");
  }
}

function presentError(error) {
  if (error?.message === "API_KEY_REQUIRED") {
    showError("An API key is required to load jobs and metrics.");
  } else if (error?.message === "API_UNREACHABLE") {
    showError("API unreachable (Render may be waking up)");
  } else if (error?.status) {
    handleHttpError(error.status);
  } else if (error?.message === "INVALID_API_RESPONSE") {
    showError("The API returned an unreadable response.");
  } else {
    showError("Something went wrong while contacting the API.");
  }
}

function setApiHealth(state, label) {
  elements.apiHealth.classList.toggle("is-online", state === "online");
  elements.apiHealth.classList.toggle("is-offline", state === "offline");
  elements.apiHealthLabel.textContent = label;
}

async function loadHealth() {
  try {
    await requestJson("/health", { auth: false });
    setApiHealth("online", "API online");
  } catch (error) {
    setApiHealth("offline", "API unavailable");
    if (error?.status === 503 || error?.message === "API_UNREACHABLE") {
      showError("API unreachable (Render may be waking up)");
    }
  }
}

function firstDefined(object, keys) {
  for (const key of keys) {
    if (object && object[key] !== undefined && object[key] !== null) return object[key];
  }
  return undefined;
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat().format(number) : "—";
}

function formatRate(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const percent = number <= 1 ? number * 100 : number;
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(percent)}%`;
}

function formatDuration(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (number >= 60) return `${Math.floor(number / 60)}m ${Math.round(number % 60)}s`;
  if (number < 1) return `${Math.round(number * 1000)} ms`;
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(number)} s`;
}

function workerAgeSeconds(metrics) {
  const age = firstDefined(metrics, ["worker_age_seconds", "worker_age", "heartbeat_age_seconds"]);
  if (age !== undefined) {
    const number = Number(age);
    return Number.isFinite(number) ? number : null;
  }
  const lastSeen = firstDefined(metrics, ["worker_last_seen", "last_seen", "last_heartbeat"]);
  if (lastSeen === undefined) return null;
  const timestamp = Date.parse(lastSeen);
  return Number.isFinite(timestamp) ? Math.max(0, (Date.now() - timestamp) / 1000) : null;
}

function renderMetrics(metrics) {
  const data = metrics?.metrics && typeof metrics.metrics === "object" ? metrics.metrics : metrics;
  const queueDepth = firstDefined(data, ["queue_depth", "queued", "queued_jobs"]);
  const successRate = firstDefined(data, ["success_rate", "success_rate_percent", "success_percentage"]);
  const avgDuration = firstDefined(data, ["avg_duration_seconds", "average_duration_seconds", "avg_duration", "average_duration"]);
  const age = workerAgeSeconds(data);

  elements.queueDepth.textContent = formatNumber(queueDepth);
  elements.successRate.textContent = formatRate(successRate);
  elements.avgDuration.textContent = formatDuration(avgDuration);
  elements.workerMetric.classList.toggle("is-stale", age !== null && age > 60);
  if (age === null) {
    elements.workerAge.textContent = "—";
    elements.workerCaption.textContent = "Heartbeat age unavailable";
  } else {
    elements.workerAge.textContent = formatDuration(age);
    elements.workerCaption.textContent = age > 60 ? "Worker may be stale" : "Since last heartbeat";
  }
  elements.metricsUpdated.textContent = `Updated ${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(new Date())}`;
  elements.metricsGrid.setAttribute("aria-busy", "false");
}

async function loadMetrics() {
  if (metricsRequestActive || document.hidden || !getApiKey()) return;
  metricsRequestActive = true;
  try {
    const metrics = await requestJson("/metrics");
    renderMetrics(metrics || {});
    clearError();
  } catch (error) {
    presentError(error);
  } finally {
    metricsRequestActive = false;
  }
}

function safeDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function jobListFromResponse(response) {
  if (Array.isArray(response)) return response;
  if (Array.isArray(response?.jobs)) return response.jobs;
  if (Array.isArray(response?.items)) return response.items;
  if (Array.isArray(response?.results)) return response.results;
  return [];
}

function statusClass(status) {
  const knownStatuses = new Set(["queued", "running", "success", "failed"]);
  return knownStatuses.has(String(status).toLowerCase()) ? `status-${String(status).toLowerCase()}` : "";
}

function appendCell(row, className, text) {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = text;
  row.append(cell);
  return cell;
}

function toggleDetails(row, job, button) {
  const current = row.nextElementSibling;
  if (current?.classList.contains("details-row")) {
    current.remove();
    button.textContent = "Details";
    button.setAttribute("aria-expanded", "false");
    return;
  }

  const detailRow = document.createElement("tr");
  detailRow.className = "details-row";
  const cell = document.createElement("td");
  cell.colSpan = 6;
  const content = document.createElement("div");
  content.className = "details-content";

  const errorBlock = document.createElement("section");
  errorBlock.className = "detail-block";
  const errorHeading = document.createElement("h3");
  errorHeading.textContent = "Last error";
  const errorValue = document.createElement("pre");
  errorValue.textContent = job.last_error ?? "No error recorded.";
  errorBlock.append(errorHeading, errorValue);

  const payloadBlock = document.createElement("section");
  payloadBlock.className = "detail-block";
  const payloadHeading = document.createElement("h3");
  payloadHeading.textContent = "Payload";
  const payloadValue = document.createElement("pre");
  try {
    payloadValue.textContent = JSON.stringify(job.payload ?? {}, null, 2);
  } catch {
    payloadValue.textContent = "Payload could not be displayed.";
  }
  payloadBlock.append(payloadHeading, payloadValue);

  content.append(errorBlock, payloadBlock);
  cell.append(content);
  detailRow.append(cell);
  row.after(detailRow);
  button.textContent = "Hide";
  button.setAttribute("aria-expanded", "true");
}

function renderJob(job) {
  const row = document.createElement("tr");
  row.className = "job-row";
  row.tabIndex = 0;

  const id = String(job.id ?? "—");
  const type = String(job.type ?? "Unknown");
  const status = String(job.status ?? "unknown");
  const idCell = appendCell(row, "job-id", id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id);
  idCell.title = id;
  appendCell(row, "type-cell", type.replaceAll("_", " "));

  const statusCell = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = `status-badge ${statusClass(status)}`.trim();
  badge.textContent = status;
  statusCell.append(badge);
  row.append(statusCell);

  const attempts = job.attempts ?? 0;
  const maxRetries = job.max_retries;
  appendCell(row, "", maxRetries === undefined ? String(attempts) : `${attempts} / ${maxRetries}`);
  appendCell(row, "", safeDate(job.created_at));

  const actionCell = document.createElement("td");
  actionCell.className = "action-cell";
  const detailsButton = document.createElement("button");
  detailsButton.type = "button";
  detailsButton.className = "details-button";
  detailsButton.textContent = "Details";
  detailsButton.setAttribute("aria-expanded", "false");
  detailsButton.setAttribute("aria-label", `Show details for job ${id}`);
  detailsButton.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleDetails(row, job, detailsButton);
  });
  actionCell.append(detailsButton);
  row.append(actionCell);

  row.addEventListener("click", () => toggleDetails(row, job, detailsButton));
  row.addEventListener("keydown", (event) => {
    if (event.target !== row) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggleDetails(row, job, detailsButton);
    }
  });
  return row;
}

async function loadJobs({ showLoading = false } = {}) {
  if (jobsRequestActive || document.hidden || !getApiKey()) return;
  jobsRequestActive = true;
  if (showLoading && elements.jobsBody.childElementCount === 0) {
    elements.jobsLoading.hidden = false;
    elements.emptyState.hidden = true;
  }

  const params = new URLSearchParams({ limit: "100", offset: "0" });
  if (elements.statusFilter.value) params.set("status", elements.statusFilter.value);
  try {
    const response = await requestJson(`/jobs?${params.toString()}`);
    const jobs = jobListFromResponse(response);
    const fragment = document.createDocumentFragment();
    for (const job of jobs) {
      if (job && typeof job === "object") fragment.append(renderJob(job));
    }
    elements.jobsBody.replaceChildren(fragment);
    elements.jobsCount.textContent = formatNumber(jobs.length);
    elements.emptyState.hidden = jobs.length !== 0;
    elements.jobsFooter.textContent = `Updated ${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(new Date())} · Refreshes every 3 seconds`;
    elements.apiHealth.classList.add("is-online");
    clearError();
  } catch (error) {
    presentError(error);
    if (error?.status === 401 || error?.message === "API_UNREACHABLE" || error?.status === 503) {
      elements.apiHealth.classList.remove("is-online");
      elements.apiHealth.classList.add("is-offline");
    }
  } finally {
    elements.jobsLoading.hidden = true;
    jobsRequestActive = false;
  }
}

async function submitJob(event) {
  event.preventDefault();
  elements.payloadError.textContent = "";
  if (!getApiKey() && !askForApiKey()) return;

  let payload;
  try {
    payload = JSON.parse(elements.payload.value);
  } catch {
    elements.payloadError.textContent = "Enter valid JSON before submitting.";
    elements.payload.focus();
    return;
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    elements.payloadError.textContent = "Payload must be a JSON object.";
    elements.payload.focus();
    return;
  }

  const type = elements.type.value;
  if (elements.forceFail.checked) {
    payload[type === "generate_report" ? "force_error" : "force_fail"] = true;
  }

  elements.submitButton.disabled = true;
  elements.submitButton.querySelector("span").textContent = "Submitting…";
  try {
    const response = await requestJson("/jobs", {
      method: "POST",
      body: JSON.stringify({ type, payload }),
    });
    const job = response?.job && typeof response.job === "object" ? response.job : response;
    const jobId = job?.id ? String(job.id) : "created";
    showToast(`Job ${jobId} queued successfully.`);
    elements.payload.value = "{}";
    elements.forceFail.checked = false;
    clearError();
    await loadJobs();
  } catch (error) {
    presentError(error);
    const message = error?.status === 401
      ? "Invalid API key"
      : error?.status === 429
        ? "Rate limited — wait 60s"
        : error?.message === "API_UNREACHABLE"
          ? "API unreachable (Render may be waking up)"
          : "Could not submit the job.";
    showToast(message, true);
  } finally {
    elements.submitButton.disabled = false;
    elements.submitButton.querySelector("span").textContent = "Queue job";
  }
}

function stopPolling() {
  window.clearInterval(jobsTimer);
  window.clearInterval(metricsTimer);
  jobsTimer = null;
  metricsTimer = null;
}

function startPolling() {
  if (document.hidden || !getApiKey()) return;
  if (jobsTimer === null) jobsTimer = window.setInterval(() => loadJobs(), JOBS_POLL_MS);
  if (metricsTimer === null) metricsTimer = window.setInterval(() => loadMetrics(), METRICS_POLL_MS);
}

elements.form.addEventListener("submit", submitJob);
elements.statusFilter.addEventListener("change", () => loadJobs({ showLoading: true }));
elements.refreshButton.addEventListener("click", () => {
  loadJobs({ showLoading: true });
  loadMetrics();
  loadHealth();
});
elements.apiKeyButton.addEventListener("click", () => {
  stopPolling();
  try {
    sessionStorage.removeItem(API_KEY_STORAGE_KEY);
  } catch {
    showError("This browser session cannot update the API key.");
    return;
  }
  if (askForApiKey()) {
    loadJobs({ showLoading: true });
    loadMetrics();
    startPolling();
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopPolling();
  } else {
    loadJobs();
    loadMetrics();
    loadHealth();
    startPolling();
  }
});
window.addEventListener("pagehide", stopPolling);
window.addEventListener("pageshow", startPolling);

loadHealth();
if (getApiKey()) {
  loadJobs({ showLoading: true });
  loadMetrics();
  startPolling();
} else {
  elements.jobsFooter.textContent = "Set an API key to load jobs and metrics";
  elements.metricsUpdated.textContent = "Set an API key to load metrics";
}
