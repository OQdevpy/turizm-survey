/**
 * Django admin'da SurveyResponse uchun Leaflet xarita.
 * `.gps-map[data-lat][data-lon][data-accuracy]` divlarini topib, har birida xarita yaratadi.
 */
(function () {
  'use strict';

  function initMap(el) {
    if (el.dataset.inited === '1') return;
    var lat = parseFloat(el.dataset.lat);
    var lon = parseFloat(el.dataset.lon);
    var accuracy = parseFloat(el.dataset.accuracy) || 0;
    if (isNaN(lat) || isNaN(lon)) return;

    // Agar div hali 0 enlikda bo'lsa — biroz kutamiz
    var rect = el.getBoundingClientRect();
    if (rect.width < 50 || rect.height < 50) {
      setTimeout(function () { initMap(el); }, 200);
      return;
    }
    el.dataset.inited = '1';

    var map = L.map(el, { scrollWheelZoom: true }).setView([lat, lon], 15);

    // OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Marker
    var marker = L.marker([lat, lon]).addTo(map);
    var gmapsUrl = 'https://www.google.com/maps?q=' + lat + ',' + lon;

    var popupHtml =
      '<div style="font-family:system-ui,sans-serif;font-size:13px;line-height:1.5">' +
      '<b style="font-size:14px">📍 Joylashuv</b><br>' +
      'Lat: <code>' + lat.toFixed(6) + '</code><br>' +
      'Lon: <code>' + lon.toFixed(6) + '</code><br>' +
      (accuracy > 0 ? 'Aniqlik: ~' + Math.round(accuracy) + ' m<br>' : '') +
      '<a href="' + gmapsUrl + '" target="_blank" rel="noopener" ' +
      'style="display:inline-block;margin-top:10px;padding:6px 12px;background:#4285f4;' +
      'color:white;border-radius:6px;text-decoration:none;font-weight:600;font-size:12px">' +
      '🌐 Google Maps\'da ochish ↗</a></div>';

    marker.bindPopup(popupHtml, { maxWidth: 280 }).openPopup();

    // Aniqlik doirasi
    if (accuracy > 0 && accuracy < 5000) {
      L.circle([lat, lon], {
        radius: accuracy,
        color: '#4285f4',
        fillColor: '#4285f4',
        fillOpacity: 0.12,
        weight: 1.5
      }).addTo(map);
    }

    // Layout o'rnashgandan keyin xaritani qayta hisoblash (bir necha martta)
    [100, 300, 800, 1500].forEach(function (delay) {
      setTimeout(function () { map.invalidateSize(); }, delay);
    });

    // Window resize'da ham qayta hisoblash
    window.addEventListener('resize', function () { map.invalidateSize(); });
  }

  function initAllMaps() {
    if (typeof L === 'undefined') {
      // Leaflet hali yuklanmagan — kutib turamiz
      setTimeout(initAllMaps, 150);
      return;
    }
    document.querySelectorAll('.gps-map').forEach(initMap);
  }

  // DOM tayyor bo'lganda
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAllMaps);
  } else {
    initAllMaps();
  }
})();
