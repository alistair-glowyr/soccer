const tabs = [...document.querySelectorAll("[data-tab]")];
const panels = [...document.querySelectorAll(".panel")];

function showPanel(id, updateHash = true) {
  tabs.forEach((tab) => {
    const active = tab.dataset.tab === id;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  panels.forEach((panel) => {
    const active = panel.id === id;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });
  if (updateHash) history.replaceState(null, "", `#${id}`);
}

tabs.forEach((tab) => tab.addEventListener("click", () => showPanel(tab.dataset.tab)));
if (["schedule", "standings"].includes(location.hash.slice(1))) {
  showPanel(location.hash.slice(1), false);
}
