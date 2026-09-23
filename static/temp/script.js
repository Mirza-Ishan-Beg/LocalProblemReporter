const STORAGE_KEY = "localProblemReports";

const form = document.getElementById("reportForm");
const photo = document.getElementById("photo");
const preview = document.getElementById("preview");
const message = document.getElementById("formMessage");
const list = document.getElementById("reportList");
const filter = document.getElementById("filter");
const category = document.getElementById("category");
const locationInput = document.getElementById("location");

function getReports() {
  return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
}

function saveReports(reports) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(reports));
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

// Calculate duration between report creation and resolution
function getResolutionTime(createdAt, solvedAt) {
  if (!solvedAt) return "";
  const start = new Date(createdAt);
  const end = new Date(solvedAt);
  const diffInMinutes = Math.floor((end - start) / (1000 * 60));

  if (isNaN(diffInMinutes) || diffInMinutes < 1) return "under a minute";
  if (diffInMinutes < 60) return `${diffInMinutes} mins`;

  const hours = Math.floor(diffInMinutes / 60);
  const mins = diffInMinutes % 60;
  if (hours < 24) return `${hours}h ${mins}m`;

  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return `${days}d ${remainingHours}h`;
}

// Global handler to toggle status between Pending and Resolved
window.toggleReportStatus = function(id) {
  const reports = getReports().map(r => {
    if (r.id === id) {
      const isResolved = r.status === "Resolved";
      return {
        ...r,
        status: isResolved ? "Pending" : "Resolved",
        solvedAt: isResolved ? null : new Date().toISOString()
      };
    }
    return r;
  });
  saveReports(reports);
  renderReports();
};

function renderReports() {
  const selected = filter.value;
  const reports = getReports().filter(r => {
    if (selected === "All") return true;
    if (selected === "Pending" || selected === "Resolved") return (r.status || "Pending") === selected;
    return r.category === selected;
  });

  if (!reports.length) {
    list.innerHTML = `<div class="empty">No reports found. Be the first to report a local issue.</div>`;
    return;
  }

  list.innerHTML = reports.map(r => {
    const status = r.status || "Pending";
    const isResolved = status === "Resolved";
    const createdAt = r.createdAt || r.date;
    const durationText = isResolved ? getResolutionTime(createdAt, r.solvedAt) : "";

    return `
      <article class="report-item ${isResolved ? "is-resolved" : ""}">
        ${r.photo ? `<img src="${r.photo}" alt="${escapeHTML(r.category)} report">` : ""}
        <div class="report-body">
          <div class="badge-group" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span class="badge">${escapeHTML(r.category)}</span>
            <span class="status-badge ${isResolved ? "status-resolved" : "status-pending"}">
              ${isResolved ? `✔ Solved (${durationText})` : "⏳ Pending"}
            </span>
          </div>
          <h3>${escapeHTML(r.location)}</h3>
          <p>${escapeHTML(r.description)}</p>
          <div class="report-meta">
            <div>Reported by ${escapeHTML(r.name)} • ${escapeHTML(r.date)}</div>
            ${isResolved && r.solvedAt ? `<div class="solved-date" style="color:#059669; font-weight:bold; margin-top:4px;">Resolved on: ${escapeHTML(new Date(r.solvedAt).toLocaleString())}</div>` : ""}
          </div>
          <div style="margin-top: 12px;">
            <button class="btn btn-small" onclick="toggleReportStatus(${r.id})">
              ${isResolved ? "Mark as Pending" : "Mark as Solved"}
            </button>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

photo.addEventListener("change", () => {
  const file = photo.files[0];
  if (!file) {
    preview.classList.add("hidden");
    preview.innerHTML = "";
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    photo.value = "";
    preview.classList.add("hidden");
    message.textContent = "Please choose an image smaller than 2 MB.";
    return;
  }
  const reader = new FileReader();
  reader.onload = e => {
    preview.innerHTML = `<img src="${e.target.result}" alt="Selected photo preview">`;
    preview.classList.remove("hidden");
  };
  reader.readAsDataURL(file);
});

document.querySelectorAll(".issue-card").forEach(card => {
  card.addEventListener("click", () => {
    category.value = card.dataset.category;
    document.getElementById("report").scrollIntoView({ behavior: "smooth" });
  });
});

document.getElementById("locateBtn").addEventListener("click", () => {
  if (!navigator.geolocation) {
    message.textContent = "Geolocation is not supported by this browser.";
    return;
  }
  message.textContent = "Getting your location...";
  navigator.geolocation.getCurrentPosition(
    pos => {
      locationInput.value = `Lat ${pos.coords.latitude.toFixed(6)}, Long ${pos.coords.longitude.toFixed(6)}`;
      message.textContent = "Location added.";
    },
    () => {
      message.textContent = "Could not access location. Please enter it manually.";
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
});

form.addEventListener("submit", e => {
  e.preventDefault();

  const file = photo.files[0];
  const reader = new FileReader();

  const createReport = photoData => {
    const reports = getReports();
    const now = new Date();
    reports.unshift({
      id: Date.now(),
      name: document.getElementById("name").value.trim(),
      category: category.value,
      location: locationInput.value.trim(),
      description: document.getElementById("description").value.trim(),
      photo: photoData || "",
      date: now.toLocaleString(),
      createdAt: now.toISOString(),
      status: "Pending",
      solvedAt: null
    });
    saveReports(reports);
    form.reset();
    preview.classList.add("hidden");
    preview.innerHTML = "";
    message.textContent = "Report submitted successfully!";
    renderReports();
    document.getElementById("reports").scrollIntoView({ behavior: "smooth" });
  };

  if (file) {
    reader.onload = e => createReport(e.target.result);
    reader.readAsDataURL(file);
  } else {
    createReport("");
  }
});

filter.addEventListener("change", renderReports);

document.getElementById("clearReports").addEventListener("click", () => {
  if (confirm("Delete all reports stored in this browser?")) {
    localStorage.removeItem(STORAGE_KEY);
    renderReports();
  }
});

renderReports();