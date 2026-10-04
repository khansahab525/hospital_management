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

const STATE_ICON = {
    draft: "fa-clock-o",
    confirmed: "fa-clock-o",
    in_progress: "fa-stethoscope",
    completed: "fa-check",
    released: "fa-check",
    cancelled: "fa-times",
};

const FINISHED_STATES = ["completed", "released", "cancelled"];

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML;
}

function setField(root, name, value) {
    const el = root.querySelector(`[data-field="${name}"]`);
    if (!el) {
        return;
    }
    const text = String(value ?? "");
    if (el.textContent === text) {
        return;
    }
    el.textContent = text;
    el.classList.remove("o_lq_bump");
    void el.offsetWidth;
    el.classList.add("o_lq_bump");
}

function restartAnimation(el, className) {
    if (!el) {
        return;
    }
    el.classList.remove(className);
    void el.offsetWidth;
    el.classList.add(className);
}

function renderStats(root, data) {
    const status = data.my_status;
    root.dataset.status = status;
    root.dataset.serving = data.now_serving_in_progress ? "in_progress" : data.now_serving ? "next" : "idle";

    setField(root, "my_number", data.my_number ? `#${data.my_number}` : "-");
    const myHints = {
        in_progress: "It's your turn",
        waiting: data.ahead ? "Waiting for your turn" : "You are next",
        done: "Visit complete",
        cancelled: "Cancelled",
    };
    setField(root, "my_hint", myHints[status] || data.my_state_label);

    setField(root, "now_serving", data.now_serving ? `#${data.now_serving}` : "-");
    let servingHint = "No patients waiting";
    if (data.now_serving_in_progress) {
        servingHint = "In consultation";
    } else if (data.now_serving) {
        servingHint = "Up next";
    }
    setField(root, "serving_hint", servingHint);

    if (status === "waiting") {
        setField(root, "ahead", data.ahead);
        setField(root, "wait_hint", `About ${data.estimated_wait} min estimated wait`);
    } else if (status === "cancelled") {
        setField(root, "ahead", "-");
        setField(root, "wait_hint", "Not in today's queue");
    } else {
        setField(root, "ahead", 0);
        setField(root, "wait_hint", status === "done" ? "No more waiting" : "You are with the doctor");
    }

    const updated = root.querySelector(".o_live_updated");
    if (updated) {
        updated.textContent = data.updated_at;
    }
}

function renderProgress(root, tiles) {
    const total = tiles.length;
    const finished = tiles.filter((tile) => FINISHED_STATES.includes(tile.state)).length;
    const percent = total ? Math.round((finished / total) * 100) : 0;
    const bar = root.querySelector(".o_lq_progress_bar");
    if (bar) {
        bar.style.width = `${percent}%`;
    }
    setField(
        root,
        "progress_text",
        total ? `${finished} of ${total} patients done · ${percent}% complete` : "No appointments today"
    );
}

function renderGrid(root, tiles) {
    const grid = root.querySelector(".o_live_grid");
    const signature = JSON.stringify(tiles);
    if (grid.dataset.signature === signature) {
        return;
    }
    const firstRender = !grid.dataset.signature;
    grid.dataset.signature = signature;

    if (!tiles.length) {
        grid.innerHTML = '<p class="o_lq_empty"><i class="fa fa-calendar-o" aria-hidden="true"></i> No appointments today.</p>';
        return;
    }
    grid.innerHTML = tiles
        .map((tile, index) => {
            const classes = ["o_live_tile", STATE_CLASS[tile.state] || ""];
            if (tile.is_mine) {
                classes.push("o_live_tile_mine");
            }
            if (firstRender) {
                classes.push("o_lq_tile_enter");
            }
            const number = tile.token_number ? `#${escapeHtml(tile.token_number)}` : "&ndash;";
            const icon = STATE_ICON[tile.state] || "fa-circle-o";
            return `
                <div class="${classes.join(" ")}" style="--i:${index}">
                    ${tile.is_mine ? '<span class="o_live_you">You</span>' : ""}
                    <span class="o_lq_tile_icon"><i class="fa ${icon}" aria-hidden="true"></i></span>
                    <div class="o_live_tile_num">${number}</div>
                </div>`;
        })
        .join("");
}

function render(root, data) {
    renderStats(root, data);
    renderProgress(root, data.tiles);
    renderGrid(root, data.tiles);
}

function start(root) {
    const url = root.dataset.url;
    const refreshBar = root.querySelector(".o_lq_refresh_bar");
    const refresh = () => {
        fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
            .then((response) => (response.ok ? response.json() : Promise.reject(response)))
            .then((data) => {
                root.classList.remove("o_lq_offline");
                render(root, data);
                restartAnimation(refreshBar, "o_lq_refresh_run");
            })
            .catch(() => root.classList.add("o_lq_offline"));
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
