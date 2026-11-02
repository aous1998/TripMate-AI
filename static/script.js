// -----------------------------------------------------------------------------
// static/script.js - everything the web page does in the browser.
//
// Flow:
//   user types a request -> sendMessage() -> POST /api/travel
//   server answers with status "complete"     -> showResult()  (the travel plan)
//                   or with status "needs_review" -> showReview() (approve / change)
//   review buttons -> submitReview() -> POST /api/travel/review -> same two cases
//
// The functions are called from onclick="..." attributes in templates/index.html.
// -----------------------------------------------------------------------------

// The conversation id. Saved in the browser's localStorage so a page reload
// keeps the same conversation; null means "ask the server for a new one".
let currentThreadId = localStorage.getItem("travel_thread_id") || null;
// The last answer as Markdown text (used to check a plan exists before making a PDF).
let latestAnswerMarkdown = "";

// Display names for node names that the generic rule in formatAgentName()
// would not write nicely.
const AGENT_LABELS = {
    human_review: "Your review",
    local_guide_agent: "Local guide",
};

// Put an example prompt into the text box (used by the example chips).
function setPrompt(text) {
    document.getElementById("userInput").value = text;
}

// Show or hide the "working" state: disable the buttons and swap the button
// text for a spinner while a request is running.
function setLoading(isLoading) {
    // Find the elements by their id="..." in index.html.
    const sendBtn = document.getElementById("sendBtn");
    const btnText = document.getElementById("btnText");
    const btnLoader = document.getElementById("btnLoader");

    // A disabled button cannot be clicked twice.
    sendBtn.disabled = isLoading;

    // The CSS class "hidden" (style.css) sets display: none.
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
        // Remember the original label once (data-label attribute), so it can be restored.
        button.dataset.label = button.dataset.label || button.textContent.trim();
        button.disabled = isLoading;
        button.textContent = isLoading ? "Working..." : button.dataset.label;
    }
}

// Show a red error box with the given message.
function showError(message) {
    const errorBox = document.getElementById("errorBox");

    // textContent (not innerHTML): the message is shown as plain text, never as HTML.
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
}

// Hide and empty the error box.
function hideError() {
    const errorBox = document.getElementById("errorBox");

    errorBox.classList.add("hidden");
    errorBox.textContent = "";
}

// "flight_agent" -> "Flight", "local_guide_agent" -> "Local guide" (from AGENT_LABELS).
function formatAgentName(name) {
    if (AGENT_LABELS[name]) {
        return AGENT_LABELS[name];
    }
    // Remove the "_agent" ending, then turn underscores into spaces.
    const label = name.replace(/_agent$/, "").replace(/_/g, " ");
    // Capital first letter + the rest unchanged.
    return label.charAt(0).toUpperCase() + label.slice(1);
}

// Turn Markdown text into HTML inside the given element.
function renderMarkdown(element, markdown) {
    // Answers can quote web content, so rendered HTML is sanitised before display.
    // marked (Markdown -> HTML) and DOMPurify (removes scripts etc.) are loaded from a CDN in index.html.
    if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
        element.innerHTML = DOMPurify.sanitize(marked.parse(markdown));
        // Libraries did not load: show the raw text instead (safe, but unformatted).
    } else {
        element.innerText = markdown;
    }
}

// One short line describing the trip, e.g. "Berlin → Paris · 5 days · budget 1500 EUR".
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

// Show the final answer (status "complete").
function showResult(data) {
    // Keep the Markdown for downloadPDF().
    latestAnswerMarkdown = data.answer;

    // Hide the review panel in case it was open.
    document.getElementById("reviewSection").classList.add("hidden");

    const resultSection = document.getElementById("resultSection");
    const resultBox = document.getElementById("resultBox");
    const threadInfo = document.getElementById("threadInfo");
    const agentsInfo = document.getElementById("agentsInfo");

    renderMarkdown(resultBox, data.answer);

    threadInfo.textContent = `Thread ID: ${data.thread_id}`;

    // Blocked requests: say which guardrail stopped them instead of listing agents.
    if (data.guardrail && data.guardrail.blocked) {
        agentsInfo.textContent = `Stopped by guardrail: ${data.guardrail.reason.replace(/_/g, " ")}`;
    } else {
        // agents_run comes from the server (the agents that finished, in order).
        const agentsRun = data.agents_run || [];
        // e.g. " (after 1 change request)" / " (after 2 change requests)"; empty if none.
        const revisions = data.revisions
            ? ` (after ${data.revisions} change request${data.revisions === 1 ? "" : "s"})`
            : "";

        // e.g. "Agents used: Supervisor → Flight → Hotel → Responder"
        agentsInfo.textContent = agentsRun.length
            ? `Agents used: Supervisor → ${agentsRun.map(formatAgentName).join(" → ")} → Responder${revisions}`
            : "Agents used: Supervisor → Responder";
    }

    resultSection.classList.remove("hidden");

    // Scroll the page so the result is visible.
    resultSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

// Show the review panel (status "needs_review"): research results + approve / change.
function showReview(data) {
    const review = data.review;
    // How many more change requests the user may make (the server allows 3).
    const remaining = review.max_revisions - review.revision;

    document.getElementById("resultSection").classList.add("hidden");

    document.getElementById("reviewInfo").textContent =
        `${describeTrip(review.trip)} — approve these results or ask for changes ` +
        `(${remaining} change request${remaining === 1 ? "" : "s"} left).`;

    // Raw tool output is shown as plain text, never as HTML.
    // Remove the Markdown bold markers (**) so the plain text reads cleanly.
    const plain = text => (text || "Not researched for this request.").replace(/\*\*/g, "");
    document.getElementById("reviewFlights").textContent = plain(review.flight_results);
    document.getElementById("reviewHotels").textContent = plain(review.hotel_results);
    // Clear any old feedback text.
    document.getElementById("reviewFeedback").value = "";

    const reviewSection = document.getElementById("reviewSection");
    reviewSection.classList.remove("hidden");

    reviewSection.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

// Called with every successful server answer.
function handleResponse(data) {
    // Remember the conversation id (also across page reloads).
    currentThreadId = data.thread_id;
    localStorage.setItem("travel_thread_id", currentThreadId);

    // Paused for review, or finished?
    if (data.status === "needs_review") {
        showReview(data);
    } else {
        showResult(data);
    }
}

// Send a JSON body to the server with POST and return the parsed JSON answer.
// Throws an Error (with the server's message) if the request failed.
// `async` functions can use `await` to wait for the network without freezing the page.
async function postJSON(url, body) {
    // fetch() is the browser's built-in function for HTTP requests.
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        // JavaScript object -> JSON text
        body: JSON.stringify(body)
    });

    // JSON text -> JavaScript object
    const data = await response.json();

    // HTTP error code (e.g. 400, 500) or {"success": false}: throw the server's message.
    if (!response.ok || !data.success) {
        throw new Error(data.error || "Something went wrong.");
    }

    return data;
}

// The "Plan My Trip" button (and Ctrl+Enter).
async function sendMessage() {
    hideError();

    const input = document.getElementById("userInput");
    const message = input.value.trim();

    // Nothing typed: show an error and stop.
    if (!message) {
        showError("Please enter your travel request first.");
        return;
    }

    setLoading(true);

    // try / catch / finally: catch shows any error; finally always runs (stop the spinner).
    try {
        const data = await postJSON("/api/travel", {
            // thread_id null on the first request -> the server creates a new one.
            message: message,
            thread_id: currentThreadId,
            // true if the "review flights & hotels" checkbox is ticked
            human_review: document.getElementById("reviewToggle").checked
        });

        handleResponse(data);

    } catch (error) {
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

// The review buttons: submitReview(true) = Approve, submitReview(false) = Request changes.
async function submitReview(approved) {
    hideError();

    const feedback = document.getElementById("reviewFeedback").value.trim();

    // "Request changes" needs a description of the changes.
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

// The "Copy" button: copy the answer as plain text to the clipboard.
function copyResult() {
    const resultBox = document.getElementById("resultBox");
    // innerText = the visible text without HTML tags.
    const text = resultBox.innerText;

    if (!text) {
        return;
    }

    // The clipboard API returns a Promise: .then runs on success, .catch on failure.
    navigator.clipboard.writeText(text)
        .then(() => {
            const copyBtn = document.querySelector(".copy-btn");
            const oldText = copyBtn.textContent;

            copyBtn.textContent = "Copied!";

            // Change the label back after 1.4 seconds.
            setTimeout(() => {
                copyBtn.textContent = oldText;
            }, 1400);
        })
        .catch(() => {
            showError("Could not copy result.");
        });
}

// The "Download PDF" button: turn the answer area into a PDF file with html2pdf.js.
function downloadPDF() {
    // The element to print (the answer box, see index.html).
    const pdfContent = document.getElementById("pdfContent");

    if (!latestAnswerMarkdown || !pdfContent) {
        showError("No travel plan available to download.");
        return;
    }

    const downloadBtn = document.querySelector(".download-btn");
    const oldText = downloadBtn.textContent;

    // Show progress and block double clicks while the PDF is built.
    downloadBtn.textContent = "Preparing PDF...";
    downloadBtn.disabled = true;

    // html2pdf settings: page margins (inches), file name, image quality,
    // how to screenshot the page, and the PDF page format.
    const options = {
        margin: 0.5,
        filename: "ai-travel-plan.pdf",
        image: {
            type: "jpeg",
            quality: 0.98
        },
        // html2canvas takes a "screenshot" of the element; scale 2 = sharper text.
        html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: "#ffffff"
        },
        // jsPDF builds the PDF: A4 portrait.
        jsPDF: {
            unit: "in",
            format: "a4",
            orientation: "portrait"
        },
        // Try not to cut elements in half across pages.
        pagebreak: {
            mode: ["avoid-all", "css", "legacy"]
        }
    };

    // Build the PDF and save it; restore the button whatever happens.
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

// Keyboard shortcut: Ctrl+Enter anywhere on the page sends the request.
document.addEventListener("keydown", function(event) {
    if (event.ctrlKey && event.key === "Enter") {
        sendMessage();
    }
});