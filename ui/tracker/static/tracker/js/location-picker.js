(() => {
  // The Location field in item forms: click the map or search an address to place a pin.
  // The latitude, longitude and address inputs stay visible, so everything still works by
  // keyboard, and when the map or the search can't load (for example offline).
  const BUCHAREST = [44.4268, 26.1025];
  const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const SEARCH = "https://nominatim.openstreetmap.org/search";
  const CREDIT = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  // OpenStreetMap asks every request to say which site it comes from. Django's default policy
  // sends nothing to other sites, so map tiles and searches send just this site's address.
  const REFERRER = "strict-origin-when-cross-origin";
  const OFFLINE = "The map couldn’t load (are you offline?). You can still type the address or the coordinates.";

  function pinIcon() {
    return L.divIcon({ className: "map-pin", html: "<span></span>", iconSize: [22, 22], iconAnchor: [11, 22] });
  }

  function setup(box) {
    const lat = box.querySelector('input[name$="__lat"]');
    const lon = box.querySelector('input[name$="__lon"]');
    const address = box.querySelector('input[name$="__address"]');
    const mapNode = box.querySelector("[data-location-map]");
    const note = box.querySelector("[data-location-note]");
    const query = box.querySelector("[data-location-query]");
    const searchButton = box.querySelector("[data-location-search]");
    const results = box.querySelector("[data-location-results]");
    const status = box.querySelector("[data-location-status]");
    let map = null;
    let marker = null;
    let searching = false;

    const point = () => {
      const la = parseFloat(lat.value);
      const lo = parseFloat(lon.value);
      return Number.isFinite(la) && Number.isFinite(lo) && Math.abs(la) <= 90 && Math.abs(lo) <= 180 ? [la, lo] : null;
    };

    function showPin(latlng) {
      if (!map) return;
      if (marker) {
        marker.setLatLng(latlng);
      } else {
        marker = L.marker(latlng, { icon: pinIcon(), draggable: true, keyboard: false }).addTo(map);
        marker.on("dragend", () => setPoint(marker.getLatLng(), false));
      }
    }

    function setPoint(latlng, moveMap) {
      const la = Array.isArray(latlng) ? latlng[0] : latlng.lat;
      const lo = Array.isArray(latlng) ? latlng[1] : latlng.lng;
      lat.value = la.toFixed(6);
      lon.value = lo.toFixed(6);
      showPin([la, lo]);
      if (map && moveMap) map.setView([la, lo], Math.max(map.getZoom(), 16));
    }

    function startMap() {
      if (map) {
        map.invalidateSize();
        return;
      }
      if (box.closest("[hidden]")) return; // drawn when its category is chosen
      if (!window.L) {
        note.textContent = OFFLINE;
        return;
      }
      mapNode.hidden = false;
      const start = point();
      map = L.map(mapNode).setView(start || BUCHAREST, start ? 16 : 11);
      const tiles = L.tileLayer(TILES, { maxZoom: 19, attribution: CREDIT, referrerPolicy: REFERRER }).addTo(map);
      tiles.once("tileerror", () => { note.textContent = OFFLINE; });
      map.on("click", (event) => setPoint(event.latlng, false));
      if (start) showPin(start);
    }

    async function search() {
      const text = query.value.trim();
      if (!text || searching) return;
      searching = true; // one search at a time: OpenStreetMap allows at most one per second
      searchButton.disabled = true;
      status.textContent = "Searching…";
      results.replaceChildren();
      results.hidden = true;
      const url = new URL(SEARCH);
      url.search = new URLSearchParams({ q: text, format: "jsonv2", countrycodes: "ro", limit: "5", "accept-language": "ro,en" });
      try {
        const response = await fetch(url, { referrerPolicy: REFERRER });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const found = await response.json();
        if (!found.length) {
          status.textContent = "No results. Try a shorter address, e.g. the street and the city.";
          return;
        }
        status.textContent = `${found.length} result${found.length === 1 ? "" : "s"}: choose one.`;
        found.forEach((place) => {
          const item = document.createElement("li");
          const button = document.createElement("button");
          button.type = "button";
          button.className = "btn btn-sm btn-light text-start w-100";
          button.textContent = place.display_name; // text, never HTML
          button.addEventListener("click", () => {
            address.value = place.display_name.slice(0, 200);
            startMap();
            setPoint([parseFloat(place.lat), parseFloat(place.lon)], true);
            results.hidden = true;
            status.textContent = "Pin placed. Drag it to adjust.";
          });
          item.append(button);
          results.append(item);
        });
        results.hidden = false;
      } catch (error) {
        status.textContent = "The address search isn’t reachable right now. Click the map or type the coordinates instead.";
      } finally {
        setTimeout(() => { searching = false; searchButton.disabled = false; }, 1000);
      }
    }

    searchButton.addEventListener("click", search);
    query.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { // search, don't submit the whole item form
        event.preventDefault();
        search();
      }
    });
    [lat, lon].forEach((input) => input.addEventListener("change", () => {
      const typed = point();
      if (typed) showPin(typed);
    }));
    box.querySelector("[data-location-clear]").addEventListener("click", () => {
      lat.value = "";
      lon.value = "";
      address.value = "";
      if (marker) { marker.remove(); marker = null; }
      status.textContent = "Location cleared.";
    });
    box.addEventListener("location:show", startMap);
    startMap();
  }

  const boxes = document.querySelectorAll("[data-location-input]");
  boxes.forEach(setup);
  document.addEventListener("customfields:shown", (event) => {
    event.target.querySelectorAll("[data-location-input]").forEach((box) => box.dispatchEvent(new Event("location:show")));
  });
})();
