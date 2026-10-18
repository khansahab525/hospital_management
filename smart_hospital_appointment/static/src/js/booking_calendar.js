/** @odoo-module **/

const WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function parseWeekdays(raw) {
    if (!raw) {
        return [];
    }
    try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed.map(Number).filter((n) => n >= 0 && n <= 6) : [];
    } catch {
        return [];
    }
}

function toISODate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

function startOfDay(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function initBookingCalendar(root) {
    const input = root.querySelector('input[name="appointment_date"]');
    const grid = root.querySelector("[data-calendar-grid]");
    const label = root.querySelector("[data-calendar-label]");
    const prev = root.querySelector("[data-calendar-prev]");
    const next = root.querySelector("[data-calendar-next]");
    if (!input || !grid || !label) {
        return;
    }

    const weekdays = parseWeekdays(root.dataset.availableWeekdays || "[]");
    const minDate = startOfDay(root.dataset.minDate ? new Date(`${root.dataset.minDate}T00:00:00`) : new Date());
    let view = input.value ? new Date(`${input.value}T00:00:00`) : new Date(minDate);
    if (Number.isNaN(view.getTime())) {
        view = new Date(minDate);
    }

    const isEnabled = (date) => {
        if (!weekdays.length) {
            return false;
        }
        const day = startOfDay(date);
        if (day < minDate) {
            return false;
        }
        // JS getDay(): 0=Sun … 6=Sat → convert to 0=Mon … 6=Sun
        const mondayBased = (day.getDay() + 6) % 7;
        return weekdays.includes(mondayBased);
    };

    const render = () => {
        const year = view.getFullYear();
        const month = view.getMonth();
        label.textContent = view.toLocaleString(undefined, { month: "long", year: "numeric" });

        const first = new Date(year, month, 1);
        const startOffset = (first.getDay() + 6) % 7; // Monday-first grid
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const selected = input.value;

        let html = WEEKDAY_SHORT.map((name) => `<span class="o_bc_dow">${name}</span>`).join("");
        for (let i = 0; i < startOffset; i++) {
            html += `<span class="o_bc_day o_bc_empty"></span>`;
        }
        for (let day = 1; day <= daysInMonth; day++) {
            const date = new Date(year, month, day);
            const iso = toISODate(date);
            const enabled = isEnabled(date);
            const classes = ["o_bc_day"];
            if (!enabled) {
                classes.push("o_bc_disabled");
            }
            if (iso === selected) {
                classes.push("o_bc_selected");
            }
            if (iso === toISODate(minDate)) {
                classes.push("o_bc_today");
            }
            html += `<button type="button" class="${classes.join(" ")}" data-date="${iso}" ${
                enabled ? "" : "disabled"
            }>${day}</button>`;
        }
        grid.innerHTML = html;
    };

    grid.addEventListener("click", (ev) => {
        const btn = ev.target.closest("button[data-date]");
        if (!btn || btn.disabled) {
            return;
        }
        input.value = btn.dataset.date;
        input.dispatchEvent(new Event("change", { bubbles: true }));
        render();
    });

    if (prev) {
        prev.addEventListener("click", () => {
            view = new Date(view.getFullYear(), view.getMonth() - 1, 1);
            render();
        });
    }
    if (next) {
        next.addEventListener("click", () => {
            view = new Date(view.getFullYear(), view.getMonth() + 1, 1);
            render();
        });
    }

    // Drop a leftover value that is no longer a working day for this doctor.
    if (input.value) {
        const current = new Date(`${input.value}T00:00:00`);
        if (Number.isNaN(current.getTime()) || !isEnabled(current)) {
            input.value = "";
        }
    }

    render();
}

function init() {
    document.querySelectorAll("[data-booking-calendar]").forEach(initBookingCalendar);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}
