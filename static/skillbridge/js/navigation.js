(function () {
    "use strict";

    var toggle = document.querySelector("[data-sidebar-toggle]");
    if (!toggle) {
        return;
    }

    var storageKey = "skillbridge.sidebar.collapsed-v3";

    function setExpanded(expanded) {
        document.body.classList.toggle("sidebar-expanded", expanded);
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-label", expanded ? "Collapse navigation" : "Expand navigation");
        toggle.setAttribute("title", expanded ? "Collapse navigation" : "Expand navigation");
        var label = toggle.querySelector("span");
        if (label) {
            label.textContent = expanded ? "Collapse" : "Expand";
        }
    }

    var savedState = window.localStorage.getItem(storageKey);
    setExpanded(savedState !== "true");

    toggle.addEventListener("click", function () {
        var expanded = !document.body.classList.contains("sidebar-expanded");
        setExpanded(expanded);
        window.localStorage.setItem(storageKey, String(!expanded));
    });
}());
