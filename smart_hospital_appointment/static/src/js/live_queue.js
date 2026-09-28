/** @odoo-module **/

const REFRESH_MS = 10000;

const STATE_CLASS = {
    draft: "o_s_upcoming",
    confirmed: "o_s_upcoming",
    in_progress: "o_s_in_progress",
    completed: "o_s_completed",
    released: "o_s_completed",
    cancelled: "o_s_cancelled",
};

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML;
}

function setField(root, name, value) {
    const el = root.querySelector(`[data-field="${name}"]`);
    if (el) {
        el.textContent = value;
    }
}

function render(root, data) {
    const active = ["draft", "confirmed", "in_progress"].includes(data.my_state);

    setField(root, "my_number", data.my_number ? `#${data.my_number}` : "-");
    if (data.my_state === "in_progress") {
        setField(root, "my_hint", "It's your turn, please go in");
    } else if (active) {
        setField(root, "my_hint", data.ahead ? "Please wait for your turn" : "You are next");
    } else {
        setField(root, "my_hint", data.my_state_label);
    }

    setField(root, "now_serving", data.now_serving ? `#${data.now_serving}` : "-");
    let servingHint = "No patients waiting";
    if (data.now_serving_in_progress) {
        servingHint = "In consultation";
    } else if (data.now_serving) {
        servingHint = "Up next";
    }
    setField(root, "serving_hint", servingHint);

    setField(root, "ahead", active ? data.ahead : "-");
    setField(root, "wait_hint", active ? `≈ ${data.estimated_wait} min estimated wait` : "");

    const updated = root.querySelector(".o_live_updated");
    if (updated) {
        updated.textContent = data.updated_at;
    }

    for (const [key, value] of Object.entries(data.counts)) {
        const el = root.querySelector(`[data-count="${key}"]`);
        if (el) {
            el.textContent = value;
        }
    }

    const grid = root.querySelector(".o_live_grid");
    if (!data.tiles.length) {
        grid.innerHTML = '<p class="text-muted mb-0">No appointments today.</p>';
        return;
    }
    grid.innerHTML = data.tiles
        .map((tile) => {
            const classes = ["o_live_tile", STATE_CLASS[tile.state] || ""];
            if (tile.is_mine) {
                classes.push("o_live_tile_mine");
            }
            const number = tile.queue_number ? `#${escapeHtml(tile.queue_number)}` : "&ndash;";
            return `
                <div class="${classes.join(" ")}">
                    ${tile.is_mine ? '<span class="o_live_you">You</span>' : ""}
                    <div class="o_live_tile_num">${number}</div>
                    <div class="o_live_tile_ref">${escapeHtml(tile.name)}</div>
                    <div class="o_live_tile_meta">${escapeHtml(tile.time)} · ${escapeHtml(tile.state_label)}</div>
                </div>`;
        })
        .join("");
}

function start(root) {
    const url = root.dataset.url;
    const refresh = () => {
        fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
            .then((response) => (response.ok ? response.json() : Promise.reject(response)))
            .then((data) => render(root, data))
            .catch(() => {});
    };
    refresh();
    setInterval(() => {
        if (!document.hidden) {
            refresh();
        }
    }, REFRESH_MS);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            refresh();
        }
    });
}

function init() {
    const root = document.querySelector(".o_live_queue[data-url]");
    if (root) {
        start(root);
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}
