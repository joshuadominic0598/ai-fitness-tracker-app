/* An app-owned Monday-first date picker; ISO inputs keep existing form contracts. */
(function (root) {
  "use strict";
  const MIN = "1900-01-01",
    MAX = "2050-12-31";
  const parse = (value) => new Date(value + "T12:00:00Z");
  const iso = (value) => value.toISOString().slice(0, 10);
  const shift = (value, days) => {
    const result = parse(value);
    result.setUTCDate(result.getUTCDate() + days);
    return iso(result);
  };
  const clamp = (value, min = MIN, max = MAX) =>
    value < min ? min : value > max ? max : value;
  function monthDays(month, min = MIN, max = MAX) {
    const first = month + "-01",
      start = shift(first, -(parse(first).getUTCDay() + 6) % 7);
    return Array.from({ length: 42 }, (_, i) => {
      const day = shift(start, i);
      return {
        day,
        number: Number(day.slice(-2)),
        outside: day.slice(0, 7) !== month,
        disabled: day < min || day > max,
      };
    });
  }
  function moveMonth(value, amount) {
    const old = parse(value),
      year = old.getUTCFullYear(),
      month = old.getUTCMonth() + amount;
    const end = new Date(Date.UTC(year, month + 1, 0, 12)).getUTCDate();
    return iso(
      new Date(Date.UTC(year, month, Math.min(old.getUTCDate(), end), 12)),
    );
  }
  function attach(doc) {
    const dialog = doc.createElement("dialog");
    dialog.className = "monday-datepicker";
    dialog.id = "monday-datepicker";
    dialog.setAttribute("aria-label", "Choose date");
    doc.body.append(dialog);
    let active = null,
      selected = "",
      focused = "",
      month = "",
      min = MIN,
      max = MAX;
    const months = Array.from({ length: 12 }, (_, i) =>
      new Intl.DateTimeFormat("en", { month: "long", timeZone: "UTC" }).format(
        new Date(Date.UTC(2026, i, 1)),
      ),
    );
    const fullDate = (day) =>
      new Intl.DateTimeFormat("en", {
        dateStyle: "full",
        timeZone: "UTC",
      }).format(parse(day));
    const displayDate = (day) =>
      day ? day.split("-").reverse().join("/") : "Choose date";
    const today = () => {
      const now = new Date();
      return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    };
    const previousMonth = () => moveMonth(month + "-01", -1).slice(0, 7);
    const nextMonth = () => moveMonth(month + "-01", 1).slice(0, 7);
    function position() {
      if (!active?.trigger.isConnected) return close();
      const anchor = active.trigger.getBoundingClientRect(),
        rect = dialog.getBoundingClientRect();
      const width = doc.documentElement.clientWidth,
        height = doc.documentElement.clientHeight;
      dialog.style.left =
        Math.max(12, Math.min(anchor.left, width - rect.width - 12)) + "px";
      dialog.style.top =
        Math.max(12, Math.min(anchor.bottom + 6, height - rect.height - 12)) +
        "px";
    }
    function draw(focusDay = true) {
      const year = Number(month.slice(0, 4)),
        monthIndex = Number(month.slice(5)) - 1;
      dialog.innerHTML = `<div class="monday-picker-heading"><h2>Choose date</h2><button type="button" data-picker="cancel" aria-label="Close date picker">×</button></div><div class="monday-picker-controls"><button type="button" data-picker="prev" aria-label="Previous month" ${previousMonth() < min.slice(0, 7) ? "disabled" : ""}>←</button><select aria-label="Calendar month">${months.map((label, i) => `<option value="${i + 1}" ${i === monthIndex ? "selected" : ""}>${label}</option>`).join("")}</select><select aria-label="Calendar year">${Array.from(
        { length: Number(max.slice(0, 4)) - Number(min.slice(0, 4)) + 1 },
        (_, i) => Number(min.slice(0, 4)) + i,
      )
        .map((y) => `<option ${y === year ? "selected" : ""}>${y}</option>`)
        .join(
          "",
        )}</select><button type="button" data-picker="next" aria-label="Next month" ${nextMonth() > max.slice(0, 7) ? "disabled" : ""}>→</button></div><div class="monday-picker-weekdays" aria-hidden="true">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => `<span>${d}</span>`).join("")}</div><div class="monday-picker-days" role="group" aria-label="Dates, Monday to Sunday">${monthDays(
        month,
        min,
        max,
      )
        .map(
          (d) =>
            `<button type="button" data-day="${d.day}" aria-label="${fullDate(d.day)}" ${d.day === selected ? 'aria-pressed="true"' : 'aria-pressed="false"'} ${d.day === today() ? 'aria-current="date"' : ""} class="${d.outside ? "outside-month " : ""}${d.day === selected ? "selected" : ""}" tabindex="${d.day === focused ? 0 : -1}" ${d.disabled ? "disabled" : ""}>${d.number}</button>`,
        )
        .join(
          "",
        )}</div><div class="monday-picker-footer">${active.input.required ? "" : '<button type="button" data-picker="clear">Clear</button>'}<button type="button" data-picker="today">Today</button><button type="button" data-picker="cancel">Cancel</button></div>`;
      if (dialog.open) position();
      if (focusDay) dialog.querySelector(`[data-day="${focused}"]`)?.focus();
    }
    function close() {
      if (dialog.open) dialog.close();
      active?.trigger.setAttribute("aria-expanded", "false");
      active?.trigger.focus();
      active = null;
    }
    function select(value) {
      if (!active) return;
      const item = active;
      item.input.value = value;
      update(item);
      close();
      item.input.dispatchEvent(new Event("input", { bubbles: true }));
      item.input.dispatchEvent(new Event("change", { bubbles: true }));
      // A date change may replace the whole page. Restore focus to its new trigger.
      queueMicrotask(() => {
        upgrade();
        doc
          .getElementById(item.input.id)
          ?.parentElement.querySelector(".monday-date-trigger")
          ?.focus();
      });
    }
    function update(item) {
      item.trigger.querySelector("span").textContent = displayDate(
        item.input.value,
      );
      item.trigger.setAttribute(
        "aria-label",
        `${item.label}: ${displayDate(item.input.value)}. Choose date`,
      );
      item.trigger.disabled = item.input.disabled;
    }
    function open(item) {
      active = item;
      item.trigger.setAttribute("aria-expanded", "true");
      min = item.input.min || MIN;
      max = item.input.max || MAX;
      selected = item.input.value;
      focused = clamp(selected || today(), min, max);
      month = focused.slice(0, 7);
      draw(false);
      if (!dialog.open) dialog.showModal();
      position();
      dialog.querySelector(`[data-day="${focused}"]`)?.focus();
    }
    dialog.addEventListener("click", (event) => {
      const day = event.target.closest("[data-day]");
      if (day && !day.disabled) return select(day.dataset.day);
      const action = event.target.closest("[data-picker]")?.dataset.picker;
      if (action === "cancel") return close();
      if (action === "today") return select(clamp(today(), min, max));
      if (action === "clear") return select("");
      if (action === "prev" || action === "next") {
        focused = clamp(
          moveMonth(focused, action === "prev" ? -1 : 1),
          min,
          max,
        );
        month = focused.slice(0, 7);
        draw();
      }
      if (event.target === dialog) {
        const r = dialog.getBoundingClientRect();
        if (
          event.clientX < r.left ||
          event.clientX > r.right ||
          event.clientY < r.top ||
          event.clientY > r.bottom
        )
          close();
      }
    });
    dialog.addEventListener("change", (event) => {
      if (!(event.target instanceof HTMLSelectElement)) return;
      const y = dialog.querySelector('[aria-label="Calendar year"]').value;
      const m = dialog
        .querySelector('[aria-label="Calendar month"]')
        .value.padStart(2, "0");
      focused = clamp(`${y}-${m}-01`, min, max);
      month = focused.slice(0, 7);
      draw();
    });
    dialog.addEventListener("keydown", (event) => {
      if (!event.target.matches("[data-day]")) return;
      let next;
      const offset = (parse(focused).getUTCDay() + 6) % 7;
      if (event.key === "ArrowLeft") next = shift(focused, -1);
      if (event.key === "ArrowRight") next = shift(focused, 1);
      if (event.key === "ArrowUp") next = shift(focused, -7);
      if (event.key === "ArrowDown") next = shift(focused, 7);
      if (event.key === "Home") next = shift(focused, -offset);
      if (event.key === "End") next = shift(focused, 6 - offset);
      if (event.key === "PageUp")
        next = moveMonth(focused, event.shiftKey ? -12 : -1);
      if (event.key === "PageDown")
        next = moveMonth(focused, event.shiftKey ? 12 : 1);
      if (next) {
        event.preventDefault();
        focused = clamp(next, min, max);
        month = focused.slice(0, 7);
        draw();
      }
    });
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      close();
    });
    function upgrade() {
      for (const input of doc.querySelectorAll(
        'input[type="date"]:not([data-monday-date])',
      )) {
        input.dataset.mondayDate = "true";
        const label =
          input.getAttribute("aria-label") ||
          input.labels?.[0]?.textContent.trim() ||
          "Date";
        const wrapper = doc.createElement("span");
        wrapper.className = "monday-date-field";
        input.before(wrapper);
        wrapper.append(input);
        input.classList.add("monday-date-source");
        input.tabIndex = -1;
        input.setAttribute("aria-hidden", "true");
        const trigger = doc.createElement("button");
        trigger.type = "button";
        trigger.className = "monday-date-trigger";
        trigger.setAttribute("aria-haspopup", "dialog");
        trigger.setAttribute("aria-controls", "monday-datepicker");
        trigger.setAttribute("aria-expanded", "false");
        trigger.innerHTML =
          '<span></span><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M7 2v4m10-4v4M3 9h18M4 4h16a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z"/></svg>';
        wrapper.append(trigger);
        const item = { input, trigger, label };
        update(item);
        trigger.addEventListener("click", () => open(item));
        input.addEventListener("change", () => update(item));
        input.addEventListener("focus", () => trigger.focus());
        input.addEventListener("invalid", (event) => {
          event.preventDefault();
          open(item);
        });
      }
      if (dialog.open && !active?.input.isConnected) close();
    }
    const observer = new MutationObserver(upgrade);
    observer.observe(doc.body, { childList: true, subtree: true });
    root.addEventListener("resize", () => {
      if (dialog.open) position();
    });
    root.addEventListener("hashchange", close);
    upgrade();
  }
  const api = { monthDays, moveMonth, shift, clamp };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else {
    root.MondayDatePicker = api;
    attach(document);
  }
})(globalThis);
