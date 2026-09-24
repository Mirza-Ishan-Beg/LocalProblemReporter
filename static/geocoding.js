/* geocoding.js
 * Leaflet map picker + Nominatim reverse geocoding.
 * Exposes window.MapPicker.create(containerId, options) and
 *         window.MapPicker.reverseGeocode(lat, lon).
 *
 * Nominatim policy respected:
 *   - ≤ 1 request / second (enforced here)
 *   - discrete clicks only (no autocomplete)
 *   - results cached in memory
 */
(function() {
        "use strict";

        const NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse";
        const MIN_INTERVAL = 1100;              // ms between Nominatim calls
        const cache = new Map();
        let lastRequestAt = 0;

        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

        async function reverseGeocode(lat, lon) {
                const key = `${lat.toFixed(6)},${lon.toFixed(6)}`;
                if (cache.has(key)) return cache.get(key);

                const wait = MIN_INTERVAL - (Date.now() - lastRequestAt);
                if (wait > 0) await sleep(wait);
                lastRequestAt = Date.now();

                const params = new URLSearchParams({
                        lat: String(lat),
                        lon: String(lon),
                        format: "jsonv2",
                        addressdetails: "1",
                        // email: "you@example.com",   // optional, recommended for production
                });

                try {
                        const res = await fetch(`${NOMINATIM_URL}?${params}`, {
                                headers: { Accept: "application/json" },
                        });
                        if (!res.ok) throw new Error(`Nominatim ${res.status}`);
                        const data = await res.json();
                        if (data && data.display_name) {
                                cache.set(key, data);
                                return data;
                        }
                        return null;
                } catch (err) {
                        console.warn("Reverse geocoding failed:", err);
                        return null;
                }
        }

        function create(containerId, options) {
                const opts = options || {};
                const onSelect = opts.onSelect;
                const initialLat = opts.initialLat ?? 20.5937;
                const initialLng = opts.initialLng ?? 78.9629;
                const initialZoom = opts.initialZoom ?? 4;
                const markerColor = opts.markerColor ?? "#176b4d";

                const container = document.getElementById(containerId);
                if (!container || typeof L === "undefined") {
                        console.warn("MapPicker: container missing or Leaflet not loaded");
                        return null;
                }

                const map = L.map(containerId)
                        .setView([initialLat, initialLng], initialZoom);

                L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                        maxZoom: 19,
                        attribution:
                                '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                }).addTo(map);

                let marker = null;
                let requestToken = 0;

                function placeMarker(lat, lng) {
                        if (marker) {
                                marker.setLatLng([lat, lng]);
                        } else {
                                marker = L.circleMarker([lat, lng], {
                                        radius: 8,
                                        color: markerColor,
                                        fillColor: markerColor,
                                        fillOpacity: 0.7,
                                        weight: 2,
                                }).addTo(map);
                        }
                }

                async function handleClick(e) {
                        const token = ++requestToken;
                        const { lat, lng } = e.latlng;
                        placeMarker(lat, lng);

                        // 1) Immediate callback — coordinates are ready, address pending.
                        if (onSelect) onSelect({ lat, lng, address: "", pending: true });

                        // 2) Reverse-geocode, then callback again with the address.
                        const data = await reverseGeocode(lat, lng);
                        if (token !== requestToken) return;   // a newer click superseded this one

                        if (onSelect) {
                                onSelect({
                                        lat,
                                        lng,
                                        address: data ? data.display_name : "",
                                        pending: false,
                                });
                        }
                }

                map.on("click", handleClick);

                return {
                        map,
                        setLocation(lat, lng, { fly = true, zoom = 16 } = {}) {
                                placeMarker(lat, lng);
                                if (fly) map.flyTo([lat, lng], zoom);
                        },
                        clear() {
                                if (marker) {
                                        map.removeLayer(marker);
                                        marker = null;
                                }
                                requestToken++;
                        },
                        destroy() {
                                map.off("click", handleClick);
                                map.remove();
                        },
                };
        }

        window.MapPicker = { create, reverseGeocode };
})();
