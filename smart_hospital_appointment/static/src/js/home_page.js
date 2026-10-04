/** @odoo-module **/

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function animateCounter(el) {
    const target = parseInt(el.dataset.target, 10) || 0;
    if (reduceMotion || target === 0) {
        el.textContent = target;
        return;
    }
    const duration = 1600;
    const start = performance.now();
    const step = (now) => {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(target * eased);
        if (progress < 1) {
            requestAnimationFrame(step);
        }
    };
    requestAnimationFrame(step);
}

function reveal(el) {
    el.classList.add("o_hp_in");
    const onEnd = (ev) => {
        if (ev.target !== el || ev.animationName !== "o_hp_reveal_in") {
            return;
        }
        el.removeEventListener("animationend", onEnd);
        el.classList.remove("o_hp_reveal", "o_hp_in");
    };
    el.addEventListener("animationend", onEnd);
}

function initSliderProgress(carousel) {
    const progress = carousel.querySelector(".o_hp_slider_progress");
    if (!progress) {
        return;
    }
    const defaultInterval = parseInt(carousel.dataset.bsInterval, 10) || 6500;
    const restart = (item) => {
        const interval = parseInt(item && item.dataset.bsInterval, 10) || defaultInterval;
        progress.style.setProperty("--hp-slide-interval", `${interval}ms`);
        progress.classList.remove("o_running");
        void progress.offsetWidth;
        progress.classList.add("o_running");
    };
    carousel.addEventListener("slid.bs.carousel", (ev) => restart(ev.relatedTarget));
    restart(carousel.querySelector(".carousel-item.active"));
}

function playSlideMedia(item) {
    const media = item && item.querySelector(".o_hp_slide_media");
    if (!media) {
        return;
    }
    const markReady = () => media.classList.add("o_hp_media_ready");
    if (media.tagName === "VIDEO") {
        media.muted = true;
        if (!media.paused && media.readyState >= 3) {
            markReady();
        }
        media.addEventListener("playing", markReady, { once: true });
        media.play().catch(() => {});
    } else if (!media.getAttribute("src")) {
        // Embedded players flash their own UI while booting; keep the poster up a bit longer.
        media.addEventListener("load", () => setTimeout(markReady, 800), { once: true });
        media.src = media.dataset.src;
    }
}

function stopSlideMedia(item) {
    const media = item.querySelector(".o_hp_slide_media");
    if (!media) {
        return;
    }
    if (media.tagName === "VIDEO") {
        media.pause();
    } else {
        media.classList.remove("o_hp_media_ready");
        media.removeAttribute("src");
    }
}

function initSliderMedia(carousel) {
    if (reduceMotion || !carousel.querySelector(".o_hp_slide_media")) {
        return;
    }
    carousel.closest(".o_hp_slider").classList.add("o_hp_slider_js");
    carousel.addEventListener("slide.bs.carousel", (ev) => playSlideMedia(ev.relatedTarget));
    carousel.addEventListener("slid.bs.carousel", () => {
        carousel.querySelectorAll(".carousel-item:not(.active)").forEach(stopSlideMedia);
    });
    playSlideMedia(carousel.querySelector(".carousel-item.active"));
}

function initSlider(page) {
    const carousel = page.querySelector("#o_hp_carousel");
    if (!carousel) {
        return;
    }
    initSliderMedia(carousel);
    initSliderProgress(carousel);
}

function init() {
    const page = document.querySelector(".o_hospital_homepage");
    if (!page) {
        return;
    }
    initSlider(page);
    const revealEls = page.querySelectorAll(".o_hp_reveal");
    const counters = page.querySelectorAll(".o_hp_counter");

    if (reduceMotion || !("IntersectionObserver" in window)) {
        counters.forEach(animateCounter);
        return;
    }

    // Stagger siblings that enter together, e.g. cards in the same grid.
    revealEls.forEach((el) => {
        const siblings = Array.from(el.parentElement.children).filter((c) => c.classList.contains("o_hp_reveal"));
        let index = siblings.indexOf(el);
        // Cards wrapped one per Bootstrap column stagger by column position instead.
        if (siblings.length === 1 && el.parentElement.parentElement.classList.contains("row")) {
            index = Array.from(el.parentElement.parentElement.children).indexOf(el.parentElement);
        }
        el.style.setProperty("--hp-delay", `${Math.min(index, 6) * 0.08}s`);
    });
    document.documentElement.classList.add("o_hp_js");

    const observer = new IntersectionObserver(
        (entries) => {
            for (const entry of entries) {
                if (!entry.isIntersecting) {
                    continue;
                }
                observer.unobserve(entry.target);
                if (entry.target.classList.contains("o_hp_counter")) {
                    animateCounter(entry.target);
                } else {
                    reveal(entry.target);
                }
            }
        },
        { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach((el) => observer.observe(el));
    counters.forEach((el) => observer.observe(el));
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}
