// Mountains to Sea: scroll from Mount Mitchell to the Outer Banks over real elevation,
// with the sea moving at the live height and rhythm of NOAA buoy 41025.
import * as THREE from "three";

const phone = matchMedia("(max-width:820px)").matches;
const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
const canvas = document.getElementById("m2s");
const D = await (await fetch("/static/m2s/nc-terrain.json")).json();
let WVHT_FT = 6, DPD = 10;
fetch("/api/buoy").then((r) => r.json()).then((b) => {
  if (b.wave_ft) { WVHT_FT = b.wave_ft; DPD = b.period_s || DPD; }
  document.getElementById("buoy").textContent = b.wave_ft
    ? `≈ ${b.name} buoy · ${b.wave_ft} ft waves every ${Math.round(b.period_s || DPD)} s · ${b.at}`
    : "≈ Diamond Shoals buoy · no reading right now";
}).catch(() => {});

const KM_W = 830, KM_H = 322, EX = 14, STEP = phone ? 2 : 1;
const W = Math.floor(D.w / STEP), H = Math.floor(D.h / STEP);
const lon2x = (l) => (l - D.lon[0]) / (D.lon[1] - D.lon[0]) * KM_W - KM_W / 2;
const lat2z = (l) => (D.lat[1] - l) / (D.lat[1] - D.lat[0]) * KM_H - KM_H / 2;

const r = new THREE.WebGLRenderer({ canvas, antialias: !phone });
r.setPixelRatio(phone ? 1 : Math.min(devicePixelRatio, 2));
r.setSize(innerWidth, innerHeight);
const sc = new THREE.Scene();
sc.background = new THREE.Color("#F2F6F6");
sc.fog = new THREE.Fog("#F2F6F6", 300, 900);
const cam = new THREE.PerspectiveCamera(38, innerWidth / innerHeight, 1, 3000);

const g = new THREE.PlaneGeometry(KM_W, KM_H, W - 1, H - 1);
g.rotateX(-Math.PI / 2);
const pos = g.attributes.position, col = [];
const ink = new THREE.Color("#0B1620"), water = new THREE.Color("#0B6E7A"), mid = new THREE.Color("#3F8F97"), aqua = new THREE.Color("#A9DFDA"), other = new THREE.Color("#E3EBEB");
for (let j = 0; j < H; j++) for (let i = 0; i < W; i++) {
  const k = (j * STEP) * D.w + (i * STEP), e = D.elev[k], nc = D.nc[k], v = j * W + i;
  let y, c;
  if (nc && e > 0) {
    y = e / 1000 * EX;
    c = e > 850 ? water.clone().lerp(ink, Math.min((e - 850) / 700, 1)) : e > 250 ? mid.clone().lerp(water, (e - 250) / 600) : aqua.clone().lerp(mid, e / 250);
  } else if (e > 0) { y = e / 1000 * EX; c = new THREE.Color("#E6EDEE").lerp(new THREE.Color("#D6E0E2"), Math.min(e / 1500, 1)); } // neighbors: real height, quiet color
  else { y = -8; c = water; }
  pos.setY(v, y); col.push(c.r, c.g, c.b);
}
g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
const terr = new THREE.Mesh(g.toNonIndexed(), new THREE.MeshStandardMaterial({ vertexColors: true, flatShading: true, roughness: 0.95 }));
terr.geometry.computeVertexNormals();
sc.add(terr);

const sg = new THREE.PlaneGeometry(1300, 800, phone ? 110 : 220, phone ? 70 : 140);
sg.rotateX(-Math.PI / 2);
const sea = new THREE.Mesh(sg, new THREE.MeshStandardMaterial({ color: "#0B6E7A", flatShading: true, roughness: 0.6 }));
sea.position.set(lon2x(-77.7) + 650, -0.4, lat2z(35.0));
sc.add(sea);
const base = sg.attributes.position.array.slice();
const wet = new Uint8Array(base.length / 3);
for (let i = 0, v = 0; i < base.length; i += 3, v++) {
  const gi = Math.round((base[i] + sea.position.x + KM_W / 2) / KM_W * (D.w - 1)), gj = Math.round((base[i + 2] + sea.position.z + KM_H / 2) / KM_H * (D.h - 1));
  wet[v] = gi < 0 || gi >= D.w || gj < 0 || gj >= D.h ? 1 : D.elev[gj * D.w + gi] <= 0 ? 1 : 0;
}
sc.add(new THREE.HemisphereLight("#ffffff", "#9FB8BC", 1.4));
const sun = new THREE.DirectionalLight("#ffffff", 2.2); sun.position.set(-200, 260, 160); sc.add(sun);

const MIT = new THREE.Vector3(lon2x(-82.2652), 1977 / 1000 * EX, lat2z(35.765)), HAT = new THREE.Vector3(lon2x(-75.53), 0, lat2z(35.25));
const SZ = lat2z(33.2);
const camPath = new THREE.CatmullRomCurve3([new THREE.Vector3(lon2x(-83.6), 95, SZ), new THREE.Vector3(lon2x(-80.6), 105, SZ + 10), new THREE.Vector3(lon2x(-78.2), 80, SZ + 20), new THREE.Vector3(HAT.x - 70, 34, HAT.z + 60)]);
const lookPath = new THREE.CatmullRomCurve3([new THREE.Vector3(lon2x(-82.6), 0, lat2z(35.7)), new THREE.Vector3(lon2x(-79.6), 0, lat2z(35.6)), new THREE.Vector3(lon2x(-77.0), 0, lat2z(35.5)), new THREE.Vector3(HAT.x + 70, 0, HAT.z - 70)]);
const CALM_POS = new THREE.Vector3(lon2x(-79.2), 330, SZ + 120), CALM_LOOK = new THREE.Vector3(lon2x(-79.2), 0, lat2z(35.4));

const hud = document.getElementById("hud"), prog = document.getElementById("prog"), lm = document.getElementById("lm"), lh = document.getElementById("lh");
const fmt = (n) => n.toLocaleString("en-US");
const place = (el, v) => {
  const p = v.clone().project(cam), vis = p.z < 1 && p.x > -0.95 && p.x < 0.95 && p.y > -0.95 && p.y < 0.95;
  el.style.display = vis ? "block" : "none";
  el.style.left = (p.x + 1) / 2 * innerWidth + "px"; el.style.top = (1 - p.y) / 2 * innerHeight + "px";
};
const STOPS = ["MOUNTAINS", "PIEDMONT", "COASTAL PLAIN", "THE SEA"];
function frame(ms) {
  const t = Math.min(scrollY / Math.max(document.documentElement.scrollHeight - innerHeight, 1), 1);
  if (calm) { cam.position.copy(CALM_POS); cam.lookAt(CALM_LOOK); }
  else { cam.position.copy(camPath.getPoint(t)); cam.lookAt(lookPath.getPoint(t)); }
  prog.style.width = t * 100 + "%";
  const L = lookPath.getPoint(t);
  const gi = Math.max(0, Math.min(D.w - 1, Math.round((L.x + KM_W / 2) / KM_W * (D.w - 1)))), gj = Math.max(0, Math.min(D.h - 1, Math.round((L.z + KM_H / 2) / KM_H * (D.h - 1))));
  const lonv = D.lon[0] + gi / (D.w - 1) * (D.lon[1] - D.lon[0]), latv = D.lat[1] - gj / (D.h - 1) * (D.lat[1] - D.lat[0]);
  const ft = t > 0.97 ? 0 : Math.max(0, Math.round(D.elev[gj * D.w + gi] * 3.281 / 10) * 10);
  hud.innerHTML = `<b>${latv.toFixed(2)}°N ${Math.abs(lonv).toFixed(2)}°W</b><br>GROUND ${t < 0.03 ? "6,684" : fmt(ft)} FT · ${STOPS[Math.min(3, Math.floor(t * 4))]}`;
  if (!calm) {
    const a = sg.attributes.position.array, s = (ms || 0) / 1000, amp = Math.min(WVHT_FT / 3.281, 4) * 0.9, k = 2 * Math.PI / (DPD * 2.2);
    for (let i = 0, v = 0; i < a.length; i += 3, v++) {
      if (!wet[v]) { a[i + 1] = -12; continue; }
      a[i + 1] = base[i + 1] + Math.sin(base[i] * k * 0.9 + s * 2 * Math.PI / DPD * 3) * amp * 0.5 + Math.sin(base[i + 2] * 0.07 + s * 1.3) * amp * 0.25;
    }
    sg.attributes.position.needsUpdate = true; sg.computeVertexNormals();
  }
  place(lm, MIT.clone().add(new THREE.Vector3(0, 2, 0))); place(lh, HAT);
  r.render(sc, cam);
  if (!calm || frame.first) { frame.first = false; requestAnimationFrame(frame); }
}
frame.first = true;
if (calm) { for (let i = 0, v = 0; i < sg.attributes.position.array.length; i += 3, v++) if (!wet[v]) sg.attributes.position.array[i + 1] = -12; sg.attributes.position.needsUpdate = true; addEventListener("scroll", () => requestAnimationFrame(frame), { passive: true }); }
requestAnimationFrame(frame);
addEventListener("resize", () => { cam.aspect = innerWidth / innerHeight; cam.updateProjectionMatrix(); r.setSize(innerWidth, innerHeight); if (calm) requestAnimationFrame(frame); });
document.body.classList.add("m2s-ready");
