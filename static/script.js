let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";

const AGENT_LABELS = {
    human_review: "Your review",
    local_guide_agent: "Local guide",
};

function setPrompt(text) {
    document.getElementById("userInput").value = text;
}

function setLoading(isLoading) {
    const sendBtn = document.getElementById("sendBtn");
    const btnText = document.getElementById("btnText");
    const btnLoader = document.getElementById("btnLoader");

    sendBtn.disabled = isLoading;

    if (isLoading) {
        btnText.classList.add("hidden");
        btnLoader.classList.remove("hidden");
    } else {
        btnText.classList.remove("hidden");
        btnLoader.classList.add("hidden");
    }

    // The review buttons share the loading state.
    for (const id of ["approveBtn", "changesBtn"]) {
        const button = document.getElementById(id);
        button.dataset.label = button.dataset.label || button.textContent.trim();
        button.disabled = isLoading;
        button.textContent = isLoading ? "Working..." : button.dataset.label;
    }
}

function showError(message) {
    const errorBox = document.getElementById("errorBox");

    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
}

function hideError() {
    const errorBox = document.getElementById("errorBox");

    errorBox.classList.add("hidden");
    errorBox.textContent = "";
}

function formatAgentName(name) {
    if (AGENT_LABELS[name]) {
        return AGENT_LABELS[name];
    }
    const label = name.replace(/_agent$/, "").replace(/_/g, " ");
    return label.charAt(0).toUpperCase() + label.slice(1);
}

function renderMarkdown(element, markdown) {
    // Answers can quote web content, so rendered HTML is sanitised before display.
    if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
        element.innerHTML = DOMPurify.sanitize(marked.parse(markdown));
    } else {
        element.innerText = markdown;
    }
}

function describeTrip(trip) {
    if (!trip) {
        return "";
    }

    const parts = [];

    if (trip.origin && trip.destination) {
        parts.push(`${trip.origin} → ${trip.destination}`);
    } else if (trip.destination) {
        parts.push(trip.destination);
    }
    if (trip.duration_days) {
        parts.push(`${trip.duration_days} days`);
    }
    if (trip.budget) {
        parts.push(`budget ${trip.budget} ${trip.currency || "EUR"}`);
    }
    if (trip.travelers > 1) {
        parts.push(`${trip.travelers} travelers`);
    }
    if (trip.hotel_preferences) {
        parts.push(`hotels: ${trip.hotel_preferences}`);
    }

    return parts.join(" · ");
}

function showResult(data) {
    latestAnswerMarkdown = data.answer;

    document.getElementById("reviewSection").classList.add("hidden");

    const resultSection = document.getElementById("resultSection");
    const resultBox = document.getElementById("resultBox");
    const threadInfo = document.getElementById("threadInfo");
    const agentsInfo = document.getElementById("agentsInfo");

    renderMarkdown(resultBox, data.answer);

    threadInfo.textContent = `Thread ID: ${data.thread_id}`;

    if (data.guardrail && data.guardrail.blocked) {
        agentsInfo.textContent = `Stopped by guardrail: ${data.guardrail.reason.replace(/_/g, " ")}`;
    } else {
        const agentsRun = data.agents_run || [];
        const revisions = data.revisions
            ? ` (after ${data.revisions} change request${data.revisions === 1 ? "" : "s"})`
            : "";

        agentsInfo.textContent = agentsRun.length
            ? `Agents used: Supervisor → ${agentsRun.map(formatAgentName).join(" → ")} → Responder${revisions}`
            : "Agents used: Supervisor → Responder";
    }

    resultSection.classList.remove("hidden");

    resultSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

function showReview(data) {
    const review = data.review;
    const remaining = review.max_revisions - review.revision;

    document.getElementById("resultSection").classList.add("hidden");

    document.getElementById("reviewInfo").textContent =
        `${describeTrip(review.trip)} — approve these results or ask for changes ` +
        `(${remaining} change request${remaining === 1 ? "" : "s"} left).`;

    // Raw tool output is shown as plain text, never as HTML.
    const plain = text => (text || "Not researched for this request.").replace(/\*\*/g, "");
    document.getElementById("reviewFlights").textContent = plain(review.flight_results);
    document.getElementById("reviewHotels").textContent = plain(review.hotel_results);
    document.getElementById("reviewFeedback").value = "";

    const reviewSection = document.getElementById("reviewSection");
    reviewSection.classList.remove("hidden");

    reviewSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

function handleResponse(data) {
    currentThreadId = data.thread_id;
    localStorage.setItem("travel_thread_id", currentThreadId);

    if (data.status === "needs_review") {
        showReview(data);
    } else {
        showResult(data);
    }
}

async function postJSON(url, body) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        throw new Error(data.error || "Something went wrong.");
    }

    return data;
}

async function sendMessage() {
    hideError();

    const input = document.getElementById("userInput");
    const message = input.value.trim();

    if (!message) {
        showError("Please enter your travel request first.");
        return;
    }

    setLoading(true);

    try {
        const data = await postJSON("/api/travel", {
            message: message,
            thread_id: currentThreadId,
            human_review: document.getElementById("reviewToggle").checked
        });

        handleResponse(data);

    } catch (error) {
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

async function submitReview(approved) {
    hideError();

    const feedback = document.getElementById("reviewFeedback").value.trim();

    if (!approved && !feedback) {
        showError("Describe what you'd like to change, then click Request changes.");
        return;
    }

    setLoading(true);

    try {
        const data = await postJSON("/api/travel/review", {
            thread_id: currentThreadId,
            approved: approved,
            feedback: feedback
        });

        handleResponse(data);

    } catch (error) {
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

function copyResult() {
    const resultBox = document.getElementById("resultBox");
    const text = resultBox.innerText;

    if (!text) {
        return;
    }

    navigator.clipboard.writeText(text)
        .then(() => {
            const copyBtn = document.querySelector(".copy-btn");
            const oldText = copyBtn.textContent;

            copyBtn.textContent = "Copied!";

            setTimeout(() => {
                copyBtn.textContent = oldText;
            }, 1400);
        })
        .catch(() => {
            showError("Could not copy result.");
        });
}

function downloadPDF() {
    const pdfContent = document.getElementById("pdfContent");

    if (!latestAnswerMarkdown || !pdfContent) {
        showError("No travel plan available to download.");
        return;
    }

    const downloadBtn = document.querySelector(".download-btn");
    const oldText = downloadBtn.textContent;

    downloadBtn.textContent = "Preparing PDF...";
    downloadBtn.disabled = true;

    const options = {
        margin: 0.5,
        filename: "ai-travel-plan.pdf",
        image: {
            type: "jpeg",
            quality: 0.98
        },
        html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: "#ffffff"
        },
        jsPDF: {
            unit: "in",
            format: "a4",
            orientation: "portrait"
        },
        pagebreak: {
            mode: ["avoid-all", "css", "legacy"]
        }
    };

    html2pdf()
        .set(options)
        .from(pdfContent)
        .save()
        .then(() => {
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
        })
        .catch(() => {
            downloadBtn.textContent = oldText;
            downloadBtn.disabled = false;
            showError("Could not download PDF.");
        });
}

document.addEventListener("keydown", function(event) {
    if (event.ctrlKey && event.key === "Enter") {
        sendMessage();
    }
});