// Keep each summary to one line, counting skills that do not fit.
(() => {
    const previews = [...document.querySelectorAll("[data-skill-preview]")];
    if (!previews.length) return;

    const fit = (preview) => {
        const list = preview.querySelector("[data-skill-items]");
        const counter = preview.querySelector("[data-skill-count]");
        const items = [...list.querySelectorAll("[data-skill-item]")];
        items.forEach((item) => { item.hidden = false; });
        counter.hidden = true;
        if (!items.length) return;

        const widths = items.map((item) => item.getBoundingClientRect().width);
        if (widths.reduce((sum, width) => sum + width, 0) <= list.clientWidth) return;

        counter.hidden = false;
        counter.textContent = `+${items.length}`;
        let visible = 0;
        // Recheck after the counter changes width (e.g. +12 becomes +4).
        for (let pass = 0; pass < 3; pass += 1) {
            let used = 0;
            visible = 0;
            for (const width of widths) {
                if (used + width > list.clientWidth) break;
                used += width;
                visible += 1;
            }
            counter.textContent = `+${items.length - visible}`;
        }
        items.forEach((item, index) => { item.hidden = index >= visible; });
        counter.setAttribute("aria-label", `${items.length - visible} more skills; open the job for the full list`);
    };

    let pending;
    const refresh = () => {
        cancelAnimationFrame(pending);
        pending = requestAnimationFrame(() => previews.forEach(fit));
    };
    previews.forEach(fit);
    if (typeof ResizeObserver !== "undefined") {
        const observer = new ResizeObserver(refresh);
        previews.forEach((preview) => observer.observe(preview));
    } else {
        window.addEventListener("resize", refresh);
    }
    document.fonts?.ready.then(refresh);
})();
