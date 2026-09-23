const API = "/api/reports";

const form = document.getElementById("reportForm");
const photo = document.getElementById("photo");
const preview = document.getElementById("preview");
const message = document.getElementById("formMessage");
const list = document.getElementById("reportList");
const filter = document.getElementById("filter");
const category = document.getElementById("category");
const locationInput = document.getElementById("location");

/* ---------------- helpers ---------------- */
function escapeHTML(value) {
        return String(value).replace(/[&<>"']/g, c => ({
                "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
        }[c]));
}

function formatDate(iso) {
        const d = new Date(iso);
        return isNaN(d) ? iso : d.toLocaleString();
}

/* ---------------- rendering ---------------- */
function renderReports(reports) {
        if (!reports.length) {
                list.innerHTML =
                        `<div class="empty">No reports found. Be the first to report a local issue.</div>`;
                return;
        }

        list.innerHTML = reports.map(r => `
    <article class="report-item" data-id="${r.id}">
      ${r.photo
                        ? `<img src="${escapeHTML(r.photo)}" alt="${escapeHTML(r.category)} report" loading="lazy">`
                        : ""}
      <div class="report-body">
        <span class="badge">${escapeHTML(r.category)}</span>
        <h3>${escapeHTML(r.location)}</h3>
        <p>${escapeHTML(r.description)}</p>
        <div class="report-meta">
          Reported by ${escapeHTML(r.name)} • ${escapeHTML(formatDate(r.date))}
        </div>
      </div>
    </article>
  `).join("");
}

/* ---------------- loading ---------------- */
async function loadReports() {
        const selected = filter.value;
        const url = selected === "All"
                ? API
                : `${API}?category=${encodeURIComponent(selected)}`;

        list.innerHTML = `<div class="empty">Loading reports…</div>`;

        try {
                const res = await fetch(url, { headers: { Accept: "application/json" } });
                if (!res.ok) throw new Error(`Server responded ${res.status}`);
                renderReports(await res.json());
        } catch (err) {
                list.innerHTML =
                        `<div class="empty">Could not load reports. ${escapeHTML(err.message)}</div>`;
        }
}

/* ---------------- photo preview ---------------- */
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
                preview.innerHTML = "";
                message.textContent = "Please choose an image smaller than 2 MB.";
                return;
        }
        message.textContent = "";
        const reader = new FileReader();
        reader.onload = e => {
                preview.innerHTML = `<img src="${e.target.result}" alt="Selected photo preview">`;
                preview.classList.remove("hidden");
        };
        reader.readAsDataURL(file);
});

/* ---------------- category shortcuts ---------------- */
document.querySelectorAll(".issue-card").forEach(card => {
        card.addEventListener("click", () => {
                category.value = card.dataset.category;
                document.getElementById("report").scrollIntoView({ behavior: "smooth" });
        });
});

/* ---------------- GPS ---------------- */
document.getElementById("locateBtn").addEventListener("click", () => {
        if (!navigator.geolocation) {
                message.textContent = "Geolocation is not supported by this browser.";
                return;
        }
        message.textContent = "Getting your location...";
        navigator.geolocation.getCurrentPosition(
                pos => {
                        locationInput.value =
                                `Lat ${pos.coords.latitude.toFixed(6)}, Long ${pos.coords.longitude.toFixed(6)}`;
                        message.textContent = "Location added.";
                },
                () => { message.textContent = "Could not access location. Please enter it manually."; },
                { enableHighAccuracy: true, timeout: 10000 }
        );
});

/* ---------------- submit ---------------- */
form.addEventListener("submit", async e => {
        e.preventDefault();

        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        message.textContent = "Submitting…";

        try {
                const res = await fetch(API, {
                        method: "POST",
                        body: new FormData(form)   // name, category, location, description, photo
                });

                const payload = await res.json().catch(() => ({}));

                if (!res.ok) {
                        const errs = payload.errors || [payload.error] || ["Something went wrong."];
                        message.textContent = errs.join(" ");
                        return;
                }

                form.reset();
                preview.classList.add("hidden");
                preview.innerHTML = "";
                message.textContent = "Report submitted successfully!";
                filter.value = "All";
                await loadReports();
                document.getElementById("reports").scrollIntoView({ behavior: "smooth" });
        } catch (err) {
                message.textContent = "Network error — could not submit the report.";
        } finally {
                submitBtn.disabled = false;
        }
});

/* ---------------- filter & clear ---------------- */
filter.addEventListener("change", loadReports);

document.getElementById("clearReports").addEventListener("click", async () => {
        if (!confirm("Delete all reports? This cannot be undone.")) return;
        try {
                const res = await fetch(API, { method: "DELETE" });
                if (!res.ok) throw new Error(`Server responded ${res.status}`);
                filter.value = "All";
                await loadReports();
        } catch (err) {
                alert("Could not clear reports: " + err.message);
        }
});

/* ---------------- init ---------------- */
loadReports();
