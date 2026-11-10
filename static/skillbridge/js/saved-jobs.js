// Persist saved status without navigation or losing the user's scroll position.
(() => {
    let feedback;
    let hideFeedback;
    const announce = (message) => {
        if (!feedback) {
            feedback = document.createElement("div");
            feedback.className = "save-feedback";
            feedback.setAttribute("role", "status");
            document.body.append(feedback);
        }
        clearTimeout(hideFeedback);
        feedback.textContent = message;
        feedback.hidden = false;
        hideFeedback = setTimeout(() => { feedback.hidden = true; }, 4500);
    };

    document.addEventListener("submit", async (event) => {
        const form = event.target.closest("form[data-job-save]");
        if (!form) return;
        event.preventDefault();
        const forms = [...document.querySelectorAll("form[data-job-save]")]
            .filter((item) => item.dataset.jobSave === form.dataset.jobSave);
        const buttons = forms.map((item) => item.querySelector("button[type=submit]"));
        if (buttons.some((button) => button.disabled)) return;
        buttons.forEach((button) => { button.disabled = true; });
        try {
            // The input named "action" shadows the form.action DOM property.
            const response = await fetch(form.getAttribute("action"), {
                method: "POST", body: new FormData(form), credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
            });
            if (response.redirected) throw new Error("Your session may have expired. Sign in again before saving.");
            if (response.status === 403) throw new Error("The security token was rejected. Reload the page and try again.");
            if (!response.ok) throw new Error(`Could not save this job (server response ${response.status}). Please try again.`);
            const data = await response.json();
            if (typeof data.is_saved !== "boolean") throw new Error("Invalid saved status");
            forms.forEach((item) => {
                item.querySelector("input[name=action]").value = data.is_saved ? "unsave" : "save";
                const button = item.querySelector("button[type=submit]");
                const label = data.is_saved ? "Remove saved job" : "Save job";
                button.classList.toggle("saved", data.is_saved);
                button.setAttribute("aria-pressed", String(data.is_saved));
                button.setAttribute("aria-label", label);
                button.title = label;
                const text = button.querySelector("[data-save-label]");
                if (text) text.textContent = data.is_saved ? "Remove from saved jobs" : "Save job";
            });
            document.querySelectorAll("[data-saved-count]").forEach((item) => { item.textContent = data.saved_count; });
            const savedList = form.closest("[data-saved-job-list]");
            if (savedList && !data.is_saved) {
                const card = form.closest("[data-job-card]");
                const nextButton = card.nextElementSibling?.querySelector("button") || card.previousElementSibling?.querySelector("button");
                card.remove();
                nextButton?.focus({ preventScroll: true });
                if (!savedList.querySelector("[data-job-card]")) {
                    const empty = document.createElement("p");
                    empty.className = "card";
                    empty.textContent = "No saved jobs yet. Save a job from Find Jobs to add it here.";
                    savedList.append(empty);
                }
            }
            announce(data.is_saved ? "Job saved." : "Job removed from saved jobs.");
        } catch (error) {
            announce(error instanceof TypeError || error instanceof SyntaxError
                ? "Could not reach the save service or read its response. Please try again."
                : error.message);
        } finally {
            buttons.forEach((button) => { button.disabled = false; });
        }
    });
})();
