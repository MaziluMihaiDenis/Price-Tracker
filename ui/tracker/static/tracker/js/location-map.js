(() => {
  // Read-only maps: one pin on an item page, numbered pins on a comparison page.
  // The addresses are also written on the page, so nothing is lost if the map can't load.
  const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const CREDIT = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  const REFERRER = "strict-origin-when-cross-origin"; // see location-picker.js
  const OFFLINE = "The map couldn’t load (are you offline?). The address is listed instead.";

  const escape = (text) => String(text).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);

  document.querySelectorAll("[data-static-map]").forEach((node) => {
    const dataNode = document.getElementById(node.dataset.staticMap);
    const note = node.parentElement.querySelector("[data-map-note]");
    const points = dataNode ? JSON.parse(dataNode.textContent).points : [];
    if (!points.length) return;
    if (!window.L) {
      if (note) note.textContent = OFFLINE;
      return;
    }
    node.hidden = false;
    const map = L.map(node, { scrollWheelZoom: false });
    const tiles = L.tileLayer(TILES, { maxZoom: 19, attribution: CREDIT, referrerPolicy: REFERRER }).addTo(map);
    tiles.once("tileerror", () => { if (note) note.textContent = OFFLINE; });
    const markers = points.map((point) => {
      const icon = point.number
        ? L.divIcon({ className: "", html: `<span class="map-pin-number">${point.number}</span>`, iconSize: [26, 26], iconAnchor: [13, 13] })
        : L.divIcon({ className: "map-pin", html: "<span></span>", iconSize: [22, 22], iconAnchor: [11, 22] });
      const lines = [`<strong>${point.number ? `${point.number}. ` : ""}${escape(point.name)}</strong>`];
      if (point.price) lines.push(escape(point.price));
      if (point.address) lines.push(`<small>${escape(point.address)}</small>`);
      return L.marker([point.lat, point.lon], { icon, title: point.name }).bindPopup(lines.join("<br>")).addTo(map);
    });
    if (markers.length === 1) {
      map.setView(markers[0].getLatLng(), 15);
    } else {
      map.fitBounds(L.featureGroup(markers).getBounds().pad(0.2), { maxZoom: 16 });
    }
  });
})();
