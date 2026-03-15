// Cadenza — Minimal JS helpers for HTMX

// Auto-dismiss flash messages after 5 seconds
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".flash").forEach(function (el) {
        setTimeout(function () {
            el.style.transition = "opacity 0.5s";
            el.style.opacity = "0";
            setTimeout(function () { el.remove(); }, 500);
        }, 5000);
    });
});

// HTMX: Show loading state on buttons that trigger requests
document.body.addEventListener("htmx:beforeRequest", function (event) {
    var trigger = event.detail.elt;
    if (trigger.tagName === "BUTTON") {
        trigger.setAttribute("aria-busy", "true");
    }
});

document.body.addEventListener("htmx:afterRequest", function (event) {
    var trigger = event.detail.elt;
    if (trigger.tagName === "BUTTON") {
        trigger.removeAttribute("aria-busy");
    }
});
