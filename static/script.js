/* ---------------- dark/light mode ---------------- */

const themeToggle = document.getElementById("themeToggle");

function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);

    if (themeToggle) {
        const isDark = theme === "dark";

        themeToggle.innerHTML = isDark ? "☀️ Light" : "🌙 Dark";

        themeToggle.setAttribute(
            "aria-label",
            isDark ? "Switch to light mode" : "Switch to dark mode"
        );

        themeToggle.setAttribute(
            "title",
            isDark ? "Light mode" : "Dark mode"
        );
    }
}

const savedTheme = localStorage.getItem("theme");

const preferredTheme =
    savedTheme ||
    (
        window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light"
    );

applyTheme(preferredTheme);

if (themeToggle) {
    themeToggle.addEventListener("click", () => {

        const currentTheme =
            document.documentElement.getAttribute("data-theme");

        const nextTheme =
            currentTheme === "dark" ? "light" : "dark";

        localStorage.setItem("theme", nextTheme);

        applyTheme(nextTheme);
    });
}


/* ---------------- API ---------------- */

const API = "/api/reports";


/* ---------------- elements ---------------- */

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
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    }[c]));

}


function formatDate(iso) {

    const d = new Date(iso);

    return isNaN(d)
        ? iso
        : d.toLocaleString();

}


/* ---------------- rendering ---------------- */

function renderReports(reports) {

    if (!reports.length) {

        list.innerHTML =
            `<div class="empty">
                No reports found. Be the first to report a local issue.
            </div>`;

        return;
    }


    list.innerHTML = reports.map(r => `

        <article class="report-item" data-id="${r.id}">

            ${
                r.photo
                    ? `<img
                        src="${escapeHTML(r.photo)}"
                        alt="${escapeHTML(r.category)} report"
                        loading="lazy"
                    >`
                    : ""
            }

            <div class="report-body">

                <span class="badge">
                    ${escapeHTML(r.category)}
                </span>

                <h3>
                    ${escapeHTML(r.location)}
                </h3>

                <p>
                    ${escapeHTML(r.description)}
                </p>

                <div class="report-meta">
                    Reported by
                    ${escapeHTML(r.name)}
                    •
                    ${escapeHTML(formatDate(r.date))}
                </div>

            </div>

        </article>

    `).join("");

}


/* ---------------- loading ---------------- */

async function loadReports() {

    const selected = filter.value;

    const url =
        selected === "All"
            ? API
            : `${API}?category=${encodeURIComponent(selected)}`;


    list.innerHTML =
        `<div class="empty">
            Loading reports…
        </div>`;


    try {

        const res = await fetch(url, {
            headers: {
                Accept: "application/json"
            }
        });


        if (!res.ok) {
            throw new Error(`Server responded ${res.status}`);
        }


        renderReports(await res.json());

    } catch (err) {

        list.innerHTML =
            `<div class="empty">
                Could not load reports.
                ${escapeHTML(err.message)}
            </div>`;

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

        message.textContent =
            "Please choose an image smaller than 2 MB.";

        return;
    }


    message.textContent = "";


    const reader = new FileReader();


    reader.onload = e => {

        preview.innerHTML =
            `<img
                src="${e.target.result}"
                alt="Selected photo preview"
            >`;

        preview.classList.remove("hidden");

    };


    reader.readAsDataURL(file);

});


/* ---------------- category shortcuts ---------------- */

document.querySelectorAll(".issue-card").forEach(card => {

    card.addEventListener("click", () => {

        category.value = card.dataset.category;

        document
            .getElementById("report")
            .scrollIntoView({
                behavior: "smooth"
            });

    });

});


/* ---------------- GPS ---------------- */

document
    .getElementById("locateBtn")
    .addEventListener("click", () => {

        if (!navigator.geolocation) {

            message.textContent =
                "Geolocation is not supported by this browser.";

            return;
        }


        message.textContent =
            "Getting your location...";


        navigator.geolocation.getCurrentPosition(

            pos => {

                locationInput.value =
                    `Lat ${pos.coords.latitude.toFixed(6)}, Long ${pos.coords.longitude.toFixed(6)}`;

                message.textContent =
                    "Location added.";

            },

            () => {

                message.textContent =
                    "Could not access location. Please enter it manually.";

            },

            {
                enableHighAccuracy: true,
                timeout: 10000
            }

        );

    });


/* ---------------- submit ---------------- */

form.addEventListener("submit", async e => {

    e.preventDefault();


    const submitBtn =
        form.querySelector('button[type="submit"]');


    submitBtn.disabled = true;

    message.textContent =
        "Submitting…";


    try {

        const res = await fetch(API, {

            method: "POST",

            body: new FormData(form)

        });


        const payload =
            await res.json().catch(() => ({}));


        if (!res.ok) {

            const errs =
                payload.errors ||
                [payload.error] ||
                ["Something went wrong."];


            message.textContent =
                errs.join(" ");

            return;
        }


        form.reset();

        preview.classList.add("hidden");
        preview.innerHTML = "";

        message.textContent =
            "Report submitted successfully!";


        filter.value = "All";


        await loadReports();


        document
            .getElementById("reports")
            .scrollIntoView({
                behavior: "smooth"
            });


    } catch (err) {

        message.textContent =
            "Network error — could not submit the report.";

    } finally {

        submitBtn.disabled = false;

    }

});


/* ---------------- filter & clear ---------------- */

filter.addEventListener(
    "change",
    loadReports
);


document
    .getElementById("clearReports")
    .addEventListener("click", async () => {

        if (
            !confirm(
                "Delete all reports? This cannot be undone."
            )
        ) {
            return;
        }


        try {

            const res =
                await fetch(API, {
                    method: "DELETE"
                });


            if (!res.ok) {

                throw new Error(
                    `Server responded ${res.status}`
                );

            }


            filter.value = "All";


            await loadReports();


        } catch (err) {

            alert(
                "Could not clear reports: " +
                err.message
            );

        }

    });


/* ---------------- init ---------------- */

loadReports();


/* ---------------- chat widget ---------------- */
(() => {
    const toggle = document.getElementById("chatToggle");
    const panel = document.getElementById("chatPanel");
    const closeBtn = document.getElementById("chatClose");
    const msgBox = document.getElementById("chatMessages");
    const chatForm = document.getElementById("chatForm");
    const input = document.getElementById("chatInput");

    if (!toggle || !panel || !chatForm) return;   // widget not present → no-op

    const history = [];

    const addMsg = (role, text) => {
        const el = document.createElement("div");
        el.className = `chat-msg ${role}`;
        el.textContent = text;
        msgBox.appendChild(el);
        msgBox.scrollTop = msgBox.scrollHeight;
        return el;
    };

    toggle.addEventListener("click", () => {
        panel.classList.toggle("hidden");
        if (!panel.classList.contains("hidden")) input.focus();
    });

    closeBtn.addEventListener("click", () => panel.classList.add("hidden"));

    chatForm.addEventListener("submit", async e => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;

        addMsg("user", text);
        history.push({ role: "user", content: text });
        input.value = "";
        input.disabled = true;

        const thinking = addMsg("assistant", "…");

        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ messages: history }),
            });
            const data = await res.json();

            if (!res.ok) {
                thinking.remove();
                addMsg("error", (data.errors || ["Something went wrong."]).join(" "));
                history.pop();
                return;
            }

            thinking.textContent = data.reply;
            history.push({ role: "assistant", content: data.reply });
        } catch (err) {
            thinking.remove();
            addMsg("error", "Network error — could not reach the assistant.");
            history.pop();
        } finally {
            input.disabled = false;
            input.focus();
        }
    });
})();


/* ---------------- speech to text via Sarvam (30s max) ---------------- */
(() => {
    const micBtn    = document.getElementById("micBtn");
    const micLabel  = document.getElementById("micLabel");
    const micStatus = document.getElementById("micStatus");
    const descBox   = document.getElementById("description");

    if (!micBtn || !descBox) return;

    const MAX_SECONDS = 30;
    const LANG = "en-IN";   // Hindi ke liye "hi-IN"

    if (!navigator.mediaDevices || !window.MediaRecorder) {
        micBtn.disabled = true;
        micBtn.title = "Recording not supported in this browser";
        micStatus.textContent = "⚠️ Ye browser recording support nahi karta";
        return;
    }

    let mediaRecorder = null;
    let chunks        = [];
    let stream        = null;
    let isRecording   = false;
    let timeLeft      = MAX_SECONDS;
    let timerId       = null;

    const pickMime = () => {
        const opts = [
            "audio/webm;codecs=opus",
            "audio/webm",
            "audio/ogg;codecs=opus",
            "audio/mp4",
        ];
        return opts.find((m) => MediaRecorder.isTypeSupported(m)) || "";
    };

    async function transcribeBlob(blob) {
        const fd = new FormData();
        const ext = blob.type.includes("ogg") ? "ogg"
                  : blob.type.includes("mp4") ? "mp4"
                  : "webm";

        fd.append("file", blob, `speech.${ext}`);
        fd.append("model", "saarika:v2");
        fd.append("language_code", LANG);

        const res = await fetch("/api/stt-proxy", {
            method: "POST",
            body: fd,
        });

        if (!res.ok) {
            let msg = `STT failed (${res.status})`;
            try {
                const j = await res.json();
                if (j.errors) msg = j.errors.join(" ");
            } catch { /* ignore */ }
            throw new Error(msg);
        }

        const data = await res.json();
        return (data.transcript || "").trim();
    }

    async function startRecording() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                },
            });
        } catch (err) {
            micStatus.textContent = "❌ Mic permission denied ya mic nahi mila";
            return;
        }

        const mime = pickMime();
        mediaRecorder = mime
            ? new MediaRecorder(stream, { mimeType: mime })
            : new MediaRecorder(stream);

        chunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) chunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach((t) => t.stop());
            stream = null;

            if (!chunks.length) {
                micStatus.textContent = "Koi audio record nahi hua.";
                return;
            }

            const blob = new Blob(chunks, {
                type: mediaRecorder.mimeType || "audio/webm",
            });

            micStatus.textContent = "⏳ Transcribe ho raha hai…";

            try {
                const text = await transcribeBlob(blob);

                if (!text) {
                    micStatus.textContent = "Kuch samajh nahi aaya, dobara try karein.";
                    return;
                }

                const existing = descBox.value.trim();
                const sep = existing ? " " : "";
                descBox.value = (existing + sep + text).slice(0, 500);

                micStatus.textContent = "✔ Text add ho gaya";
                setTimeout(() => {
                    if (!isRecording) micStatus.textContent = "";
                }, 2500);

            } catch (err) {
                console.error(err);
                micStatus.textContent = "❌ " + err.message;
            }
        };

        mediaRecorder.start();

        isRecording = true;
        micBtn.classList.add("recording");
        micLabel.textContent = "Stop";
        micStatus.classList.add("live");

        timeLeft = MAX_SECONDS;
        micStatus.textContent = `🔴 Recording… ${timeLeft}s bache`;

        timerId = setInterval(() => {
            timeLeft--;
            if (isRecording) micStatus.textContent = `🔴 Recording… ${timeLeft}s bache`;
            if (timeLeft <= 0) stopRecording(true);
        }, 1000);
    }

    function stopRecording(auto) {
        if (!isRecording) return;
        isRecording = false;

        if (timerId) { clearInterval(timerId); timerId = null; }

        if (mediaRecorder && mediaRecorder.state !== "inactive") {
            mediaRecorder.stop();
        }

        micBtn.classList.remove("recording");
        micLabel.textContent = "Speak";
        micStatus.classList.remove("live");

        if (auto) micStatus.textContent = "⏱ 30s poore — transcribe ho raha hai…";
    }

    micBtn.addEventListener("click", () => {
        if (isRecording) stopRecording(false);
        else startRecording();
    });
})();