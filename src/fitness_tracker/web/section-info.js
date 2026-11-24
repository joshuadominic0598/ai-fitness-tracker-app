/* Section explanations: hover the heading, focus the icon, or tap to keep it open. */
(() => {
  "use strict";
  const content = document.getElementById("content");
  if (!content) return;
  const descriptions = {
    "Gym workouts": "Log gym exercises, sets, reps, added weight or timed holds. Gym days count once per date toward your gym goal. Home workouts and cardio have their own trackers.",
    "Gym days": "Set your gym-day target and timeframe. Multiple gym sessions on one date count as one gym day. Home workouts contribute to training records without adding gym days.",
    "Home workouts": "Bodyweight or weights, before or after the gym, or on another day. Adds to your body training and strength records without counting as a gym day. A quick set counts too: log push-ups, sit-ups, curls, presses and other strength exercises. Keep cardio separate.",
    "Cardio": "Choose a sport or aerobic activity and log minutes plus overall felt intensity. Weekly goal credit combines moderate minutes with twice your high-intensity minutes. Cardio stays separate from strength training.",
    "Food & nutrition": "Log meals and protein in grams. Calories in kcal are optional; leave them blank when unknown. Your AI coach can estimate both from foods and portions, with a preview to approve before saving.",
    "Protein": "Track protein grams against your chosen target. Daily, weekly and monthly totals show quantity; the completed-day average includes missing days as zero logged intake and excludes today.",
    "Calories consumed": "See recorded meal calories in kcal. Meals without calories stay unknown, and totals identify missing values. Completed-day averages are unavailable when a meal in that window is missing calories.",
    "Creatine": "Log creatine in grams and follow your personal target. It is tracked separately from protein and other supplements; no dose is prescribed by the app.",
    "Supplements": "Log your vitamins and other supplements using the amount and unit actually taken. Each selected supplement has its own goal; creatine uses its separate tracker.",
    "Your sleep": "Log total rest, night sleep and naps against the day you rested from. Uninterrupted night sleep is optional and tracked separately from total night hours.",
    "Sleep": "Choose total-rest and night-sleep targets, plus an optional uninterrupted-stretch target. Naps add to total rest; the uninterrupted target does not affect consistency.",
    "Your activity calendar": "Switch between tracking categories, browse months and open a day in Track. Gym days, cardio, food, supplements and sleep keep their own progress rules.",
    "The habit of showing up": "Review gym and home training days over the last 12 weeks. Hover or focus a day for details, or select it to open the journal. Home-only days have their own color.",
    "Your weekly goals": "Review saved quantities against the full Monday–Sunday targets. Missing and future days add zero logged intake; change the review date to inspect another week.",
    "Your weekly cardio": "See actual moderate and high-intensity minutes alongside combined goal credit. One high-intensity minute counts as two moderate minutes, and either intensity can meet your weekly target.",
    "Your intake, in perspective": "Compare daily, weekly and monthly protein, creatine and calorie totals. Completed-day averages exclude today, while quantity totals include saved entries through today.",
    "Your consistency": "These scores describe logging against your saved goals, with allowance for short breaks. They do not measure fitness or strength. Categories without data remain unscored.",
    "Your consistency, over time": "Follow historical consistency using your current goals. Editing records or changing goals recalculates earlier points.",
    "Your latest training day, mapped": "Explore body areas involved in your latest gym and home strength sessions. Select a body area to see the exercises behind its logged training volume.",
    "This day’s strength training, on your body": "Gym and home strength sets both contribute to this body map. Select an area to review its exercises. Shading represents logged training volume, not measured growth or muscle activation.",
    "Your strength, over time": "Compare monthly best logged load, reps or timed holds for an exercise. Gym and home sessions both contribute to your records; months without records remain gaps.",
    "Your training balance": "Review logged sets by body area over the last 28 days. Gym and home sessions both count, including assisting muscle groups where mapped.",
    "Your intake rhythm": "Switch between daily and weekly protein, creatine or calorie totals. The chart shows up to 20 recorded points. Unknown calorie values are excluded rather than filled with invented estimates.",
    "Exercises you come back to": "See how often each exercise appeared in gym or home sessions over the last 28 days.",
    "Body weight journal": "Review your optional body-weight measurements and their trend. Edit or delete a measurement from its original entry.",
    "Supplements you take": "Select the supplements you want to track or add a custom name. Configure their amounts, units and timeframes in the supplement goal cards.",
    "Supplement goals": "Choose a quantity or frequency target for each selected supplement. Days taken counts dates; doses counts entries. Quantity goals use compatible units.",
  };
  const popup = document.createElement("div");
  popup.id = "section-info-tooltip";
  popup.className = "section-info-tooltip";
  popup.setAttribute("role", "tooltip");
  popup.hidden = true;
  document.body.append(popup);
  let owner = null, pinned = false, closing;
  function hide() {
    clearTimeout(closing);
    owner?.setAttribute("aria-expanded", "false");
    owner?.removeAttribute("aria-describedby");
    owner = null;
    pinned = false;
    popup.hidden = true;
  }
  function show(button, keepOpen = false) {
    clearTimeout(closing);
    if (owner !== button) hide();
    owner = button;
    pinned = keepOpen;
    popup.textContent = button.dataset.sectionDescription;
    popup.hidden = false;
    button.setAttribute("aria-expanded", String(keepOpen));
    button.setAttribute("aria-describedby", popup.id);
    const anchor = button.getBoundingClientRect(), box = popup.getBoundingClientRect();
    popup.style.left = `${Math.max(12, Math.min(anchor.left, innerWidth - box.width - 12))}px`;
    popup.style.top = `${Math.max(12, anchor.bottom + box.height + 20 <= innerHeight ? anchor.bottom + 8 : anchor.top - box.height - 8)}px`;
  }
  function annotate() {
    if (owner && !owner.isConnected) hide();
    for (const heading of content.querySelectorAll(".card-head h2, .card-head h3, .intake-metric-card > h3")) {
      if (heading.querySelector(".section-info-trigger")) continue;
      const title = heading.textContent.trim();
      const supplement = heading.closest("[data-supplement-goal]");
      const description = supplement
        ? `Set your ${supplement.dataset.supplementGoal} target, measurement unit and timeframe. The saved-target summary compares your recorded intake with that goal. Save goals to apply changes.`
        : descriptions[title] || heading.nextElementSibling?.matches("p") && heading.nextElementSibling.textContent.trim();
      if (!description) continue;
      heading.classList.add("has-section-info");
      if (!heading.hasAttribute("aria-label")) heading.setAttribute("aria-label", title);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "section-info-trigger";
      button.dataset.sectionDescription = description;
      button.setAttribute("aria-label", `About ${title}`);
      button.setAttribute("aria-expanded", "false");
      button.textContent = "i";
      heading.append(button);
    }
  }
  document.addEventListener("mouseover", event => {
    if (popup.contains(event.target)) clearTimeout(closing);
    const heading = event.target.closest(".has-section-info");
    if (heading && !pinned) show(heading.querySelector(".section-info-trigger"));
  });
  document.addEventListener("mouseout", event => {
    if (pinned) return;
    const heading = event.target.closest(".has-section-info");
    if ((heading || popup.contains(event.target)) && !heading?.contains(event.relatedTarget) && !popup.contains(event.relatedTarget))
      closing = setTimeout(hide, 120);
  });
  document.addEventListener("focusin", event => {
    if (event.target.matches(".section-info-trigger")) show(event.target);
  });
  document.addEventListener("focusout", event => {
    if (event.target === owner && !pinned) hide();
  });
  document.addEventListener("click", event => {
    const button = event.target.closest(".section-info-trigger");
    if (button) {
      if (owner === button && pinned) hide();
      else show(button, true);
    } else if (!popup.contains(event.target)) hide();
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") hide(); });
  window.addEventListener("resize", hide);
  window.addEventListener("scroll", event => {
    if (event.target !== popup) hide();
  }, true);
  new MutationObserver(annotate).observe(content, { childList: true, subtree: true });
  annotate();
})();
