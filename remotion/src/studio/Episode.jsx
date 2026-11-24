// STUDIO episode renderer: shots exported by engine/export_remotion.py
import React, {useMemo, useState, useEffect} from 'react';
import {AbsoluteFill, Sequence, Img, Audio, staticFile, useCurrentFrame, useVideoConfig, random, delayRender, continueRender} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import gsap from 'gsap';

const YELLOW = '#FFD200', RED = '#C41E24', INK = '#141212', CREAM = '#F3EBDD';
const ez = {
  smooth: gsap.parseEase('power2.inOut'), out: gsap.parseEase('power3.out'), back: gsap.parseEase('back.out(2.2)'),
  elastic: gsap.parseEase('elastic.out(1, 0.45)'), lin: (u) => u,
};
const clamp = (u) => Math.min(1, Math.max(0, u));

export const Fonts = () => (
  <style>{`
    @font-face {font-family: 'Luckiest'; src: url('${staticFile('LuckiestGuy-Regular.ttf')}');}
    @font-face {font-family: 'Marker'; src: url('${staticFile('PermanentMarker-Regular.ttf')}');}
    @font-face {font-family: 'Typewriter'; src: url('${staticFile('SpecialElite-Regular.ttf')}');}
  `}</style>
);

// ---------------------------------------------------------------- background: 3D depth parallax
import {useThree} from '@react-three/fiber';

function useTexture(url) {
  const [tex, setTex] = useState(null);
  useEffect(() => {
    new THREE.TextureLoader().load(staticFile(url), (t) => {
      t.colorSpace = THREE.NoColorSpace; t.anisotropy = 8; t.minFilter = THREE.LinearMipmapLinearFilter; setTex(t);
    });
  }, [url]);
  return tex;
}

const VERT = `uniform sampler2D disp; uniform float scale; varying vec2 vUv;
void main(){ vUv = uv; float d = texture2D(disp, uv).r; vec3 p = position + vec3(0.0, 0.0, d * scale);
gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0); }`;
const FRAG = `uniform sampler2D map; varying vec2 vUv; void main(){ gl_FragColor = texture2D(map, vUv); }`;

const DepthPlane = ({bg, depthScale}) => {
  const [handle] = useState(() => delayRender('depth plane ' + bg.src));
  const map = useTexture(bg.src);
  const disp = useTexture(bg.depth);
  const {advance} = useThree();
  useEffect(() => {
    if (map && disp) { advance(performance.now()); requestAnimationFrame(() => requestAnimationFrame(() => continueRender(handle))); }
  }, [map, disp]);
  const uniforms = useMemo(() => ({map: {value: null}, disp: {value: null}, scale: {value: depthScale}}), []);
  if (!map || !disp) return null;
  uniforms.map.value = map; uniforms.disp.value = disp; uniforms.scale.value = depthScale;
  return (
    <mesh>
      <planeGeometry args={[16 * 1.18, 9 * 1.18, 320, 180]} />
      <shaderMaterial vertexShader={VERT} fragmentShader={FRAG} uniforms={uniforms} />
    </mesh>
  );
};

const CameraRig = ({z, px, py}) => {
  const {camera} = useThree();
  const fov = 30, d = (9 / z) / (2 * Math.tan((fov / 2) * Math.PI / 180));
  const mx = (16 * 1.18 - 16 / z) / 2 * 0.9, my = (9 * 1.18 - 9 / z) / 2 * 0.9;
  camera.fov = fov; camera.near = 0.1; camera.far = 200;
  camera.position.set(px * mx, -py * my, d + 1.0);
  camera.lookAt(px * mx * .6, -py * my * .6, 0);
  camera.updateProjectionMatrix();
  return null;
};


// ---------------------------------------------------------------- 3D globe with a route arc (reusable "globe" shot)
// shot.globe = {tex, from: [lat, lon], to: [lat, lon], t0, dur, view0: [lat, lon], view1: [lat, lon], lift, labels: [a, b]}
const D2R = Math.PI / 180;
const cityVec = (lat, lon) => { const ph = (lon + 180) * D2R, cl = Math.cos(lat * D2R);
  return new THREE.Vector3(-Math.cos(ph) * cl, Math.sin(lat * D2R), Math.sin(ph) * cl); };
const globeRot = (lat, lon) => new THREE.Euler(lat * D2R, (-90 - lon) * D2R, 0, 'XYZ');
const GLOBE_D = 5.2, GLOBE_FOV = 30;
const globeView = (g, t, dur) => {
  const k = ez.smooth(clamp(t / Math.max(dur, .01)));
  const [la0, lo0] = g.view0 || g.from, [la1, lo1] = g.view1 || g.to;
  return [la0 + (la1 - la0) * k, lo0 + (lo1 - lo0) * k];
};
const arcPoints = (g, k) => {
  const a = cityVec(...g.from), b = cityVec(...g.to), pts = [], n = 64, ang = a.angleTo(b), lift = g.lift ?? .22;
  for (let i = 0; i <= n * k; i++) {
    const u = i / n, sa = Math.sin((1 - u) * ang) / Math.sin(ang), sb = Math.sin(u * ang) / Math.sin(ang);
    pts.push(a.clone().multiplyScalar(sa).add(b.clone().multiplyScalar(sb)).normalize().multiplyScalar(1.005 + lift * Math.sin(Math.PI * u)));
  }
  return pts;
};
const GlobeMesh = ({g, t, dur, z}) => {
  const [handle] = useState(() => delayRender('globe ' + g.tex.src));
  const map = useTexture(g.tex.src);
  const {camera, advance} = useThree();
  useEffect(() => { if (map) { advance(performance.now()); requestAnimationFrame(() => requestAnimationFrame(() => continueRender(handle))); } }, [map]);
  camera.fov = GLOBE_FOV; camera.near = .1; camera.far = 100; camera.position.set(0, 0, GLOBE_D / z); camera.lookAt(0, 0, 0); camera.updateProjectionMatrix();
  if (!map) return null;
  const [lat, lon] = globeView(g, t, dur), rot = globeRot(lat, lon);
  const k = ez.inOut ? ez.inOut(clamp((t - (g.t0 || 0)) / (g.dur || 2.5))) : ez.smooth(clamp((t - (g.t0 || 0)) / (g.dur || 2.5)));
  const pts = arcPoints(g, k);
  const pulse = 1 + .3 * Math.sin(t * 6);
  return (
    <group rotation={rot}>
      <mesh><sphereGeometry args={[1, 96, 64]} /><meshLambertMaterial map={map} /></mesh>
      <mesh><sphereGeometry args={[1.035, 64, 48]} /><meshBasicMaterial color="#8FD8FF" transparent opacity={.16} side={THREE.BackSide} /></mesh>
      <mesh><sphereGeometry args={[1.07, 64, 48]} /><meshBasicMaterial color="#8FD8FF" transparent opacity={.07} side={THREE.BackSide} /></mesh>
      {pts.length > 1 ? <mesh><tubeGeometry args={[new THREE.CatmullRomCurve3(pts), 96, .012, 8, false]} /><meshBasicMaterial color="#FFD200" /></mesh> : null}
      {pts.length > 1 ? <mesh><tubeGeometry args={[new THREE.CatmullRomCurve3(pts), 96, .03, 8, false]} /><meshBasicMaterial color="#FFE680" transparent opacity={.28} /></mesh> : null}
      <mesh position={cityVec(...g.from).multiplyScalar(1.01)}><sphereGeometry args={[.028 * pulse, 16, 16]} /><meshBasicMaterial color="#FFFFFF" /></mesh>
      {k >= 1 ? <mesh position={cityVec(...g.to).multiplyScalar(1.01)}><sphereGeometry args={[.028 * pulse, 16, 16]} /><meshBasicMaterial color="#FFFFFF" /></mesh> : null}
    </group>
  );
};
const projectCity = (g, t, dur, z, lat, lon, W, H) => {
  const [vla, vlo] = globeView(g, t, dur), v = cityVec(lat, lon).applyEuler(globeRot(vla, vlo));
  const D = GLOBE_D / z, f = (H / 2) / Math.tan(GLOBE_FOV / 2 * D2R);
  return {x: W / 2 + v.x / (D - v.z) * f, y: H / 2 - v.y / (D - v.z) * f, vis: v.z > .2};
};
const Globe = ({shot, t, W, H, z}) => {
  const g = shot.globe, k = clamp((t - (g.t0 || 0)) / (g.dur || 2.5));
  const A = projectCity(g, t, shot.dur, z, ...g.from, W, H), B = projectCity(g, t, shot.dur, z, ...g.to, W, H);
  const lab = (p, text, show) => show && p.vis ? (
    <div style={{position: 'absolute', left: p.x, top: p.y - H * .055, transform: 'translate(-50%,-100%)', fontFamily: 'Luckiest', fontSize: H * .04, color: RED,
      background: YELLOW, padding: '.25em .6em .12em', borderRadius: 60, border: '4px solid white', whiteSpace: 'nowrap', boxShadow: '0 6px 0 rgba(0,0,0,.25)'}}>{text}</div>) : null;
  return (
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 45%, #1F4E66 0%, #0F2A3A 55%, #08141D 100%)'}}>
      <ThreeCanvas width={W} height={H} linear flat style={{position: 'absolute'}}>
        <ambientLight intensity={1.6} />
        <directionalLight position={[-3, 2, 4]} intensity={1.4} />
        <GlobeMesh g={g} t={t} dur={shot.dur} z={z} />
      </ThreeCanvas>
      {lab(A, (g.labels || [])[0], t > (g.t0 || 0) - .2)}
      {lab(B, (g.labels || [])[1], k >= .98)}
    </AbsoluteFill>
  );
};

const Background = ({shot, u, W, H, t = 0}) => {
  const [z0, z1, p0 = [0, 0], p1 = [0, 0]] = shot.cam;
  const z = z0 + (z1 - z0) * u, px = p0[0] + (p1[0] - p0[0]) * u, py = p0[1] + (p1[1] - p0[1]) * u;
  if (shot.bgColor) return <AbsoluteFill style={{background: shot.bgColor}} />;
  if (shot.globe) return <Globe shot={shot} t={t} W={W} H={H} z={z} />;
  if (shot.parallax && !shot.route) {
    return (
      <ThreeCanvas width={W} height={H} linear flat style={{position: 'absolute'}} camera={{fov: 30, position: [0, 0, 18]}}>
        <CameraRig z={z} px={px} py={py} />
        <DepthPlane bg={shot.bg} depthScale={shot.depthScale ?? 1.0} />
      </ThreeCanvas>
    );
  }
  // flat 2D (maps: the route is drawn in image space and must stay glued to it)
  const m = 1.25;
  const tx = -px * (W * m - W / z) / 2 * z, ty = -py * (H * m - H / z) / 2 * z;
  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <div style={{position: 'absolute', width: W * m, height: H * m, left: (W - W * m) / 2, top: (H - H * m) / 2,
        transform: `translate(${tx}px, ${ty}px) scale(${z})`, transformOrigin: '50% 50%'}}>
        <Img src={staticFile(shot.bg.src)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        {shot.route ? <Route r={shot.route} t={u * shot.dur} /> : null}
      </div>
    </AbsoluteFill>
  );
};

const Route = ({r, t}) => {
  const k = clamp((t - r.t0) / (r.dur || 2)), p = ez.smooth(k);
  const [x0, y0] = r.p0, [x1, y1] = r.p1, lift = r.lift ?? .15;
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2 - lift * 2;
  const d = `M ${x0 * 1000} ${y0 * 562} Q ${cx * 1000} ${cy * 562} ${x1 * 1000} ${y1 * 562}`;
  const pulse = 1 + 0.35 * Math.sin(t * 6);
  return (
    <svg viewBox="0 0 1000 562" preserveAspectRatio="none" style={{position: 'absolute', inset: 0, width: '100%', height: '100%'}}>
      <path d={d} fill="none" stroke={YELLOW} strokeWidth={4} strokeLinecap="round" pathLength={1} strokeDasharray="1" strokeDashoffset={1 - p}
        style={{filter: 'drop-shadow(0 0 6px rgba(255,210,0,.9))'}} />
      <circle cx={x0 * 1000} cy={y0 * 562} r={6 * pulse} fill="white" stroke={YELLOW} strokeWidth={3} />
      {k >= 1 ? <circle cx={x1 * 1000} cy={y1 * 562} r={6 * pulse} fill="white" stroke={YELLOW} strokeWidth={3} /> : null}
    </svg>
  );
};

// ---------------------------------------------------------------- characters
const blinkIndex = (t, seed) => {
  const ph = (t + seed * 1.37) % 3.7;
  if (ph < .05) return 1; if (ph < .11) return 2; if (ph < .16) return 1; return 0;
};


// Rhubarb mouth shape at time t (cues [[t, 'A'..'H'|'X']]) -> mouth index. 3 mouths: closed/mid/open. 6 mouths: A B C D E F.
const MAP3 = {A: 0, X: 0, B: 1, E: 1, F: 1, G: 1, H: 2, C: 2, D: 2}, MAP6 = {A: 0, X: 0, B: 1, G: 1, C: 2, H: 2, D: 3, E: 4, F: 5};
const mouthAt = (cues, t, nM) => {
  if (!cues || !cues.length) return null;
  let k = -1; for (let i = 0; i < cues.length && cues[i][0] <= t; i++) k = i;
  if (k < 0) return null; const sh = cues[k][1];
  return (nM >= 6 ? MAP6 : MAP3)[sh] ?? 0;
};
const Layer = ({L, t, tAbs, shot, env, fps, W, H, z}) => {
  if (t < L.t0 || (L.t1 != null && t > L.t1)) return null;
  const lt = t - L.t0;
  let src, iw, ih;
  let level = 0, prevFi = null, mixK = 1;
  if (L.lineSpan && t >= L.lineSpan[0] && t <= L.lineSpan[1]) level = env[Math.round(tAbs * fps)] || 0;
  if (L.sprite) {
    const n = L.sprite.frames.length, mode = L.mode || 'loop';
    let fi = 0;
    if (mode === 'loop') fi = Math.floor(lt * (L.fps || 10)) % n;
    else if (mode === 'talk') {
      fi = L.closed ?? 0;
      const rm = mouthAt(L.mouth, t, 3);
      if (rm != null && L.lineSpan && t >= L.lineSpan[0] && t <= L.lineSpan[1]) fi = [L.closed ?? 0, L.mid ?? 1, L.open ?? 2][rm];
      else if (level > 0) fi = level > .42 ? (L.open ?? 2) : level > .14 ? (L.mid ?? 1) : (L.closed ?? 0);
      else if (L.blink != null && blinkIndex(tAbs, L.x ?? .5) === 2) fi = L.blink;
    } else if (mode === 'gtalk') {
      if (level > 0) fi = level > .42 ? L.to : level > .14 ? L.tm : L.tc;
      else fi = L.gN > 0 ? Math.floor((tAbs + (L.x ?? .5) * 2) / 2.2) % L.gN : L.tc;
    } else if (mode === 'ptalk') {
      // pose from the schedule (changes only on the character's own words), mouth from the voice level
      const pa = L.poseAt || [[0, 0]]; let k = 0; while (k + 1 < pa.length && pa[k + 1][0] <= t) k++;
      const nM = L.nMouth || 3, rm = mouthAt(L.mouth, t, nM);
      const m = rm != null ? rm : (level > .42 ? 2 : level > .14 ? 1 : 0);
      fi = pa[k][1] * nM + m;
      const since = t - pa[k][0];
      if (k > 0 && since < .16 && pa[k - 1][1] !== pa[k][1]) { prevFi = pa[k - 1][1] * nM + m; mixK = since / .16; }
    } else if (typeof mode === 'number' || /^[0-9]+$/.test(String(mode))) {
      fi = Number(mode);
    } else if (mode === 'blink') {
      const b = blinkIndex(tAbs, L.x ?? .5); fi = [L.open ?? 0, L.half ?? 1, L.closed ?? 2][b];
      if (L.alt != null && Math.floor(tAbs / 5.3) % 3 === 1 && (tAbs % 5.3) < .5) fi = L.alt;
    }
    src = L.sprite.frames[fi]; iw = L.sprite.w; ih = L.sprite.h;
  } else { src = L.image.src; iw = L.image.w; ih = L.image.h; }
  let x = L.x ?? .5, y = L.y ?? .95;
  if (L.move) {
    const mv = L.move; let k = clamp((t - mv.t0) / Math.max(mv.t1 - mv.t0, .01));
    k = mv.ease === 'ease' ? ez.out(k) : k;
    x = mv.x0 + (mv.x1 - mv.x0) * k; if (mv.y0 != null) y = mv.y0 + (mv.y1 - mv.y0) * k;
  }
  const par = .6, zz = 1 + (z - 1) * par;
  let h = (L.h ?? .6) * H * zz, scale = 1, rot = 0, dy = 0, op = 1;
  const idle = L.idle ?? 'breathe';
  if (idle === 'bob') dy += Math.sin((tAbs + x * 3) * 2.2) * H * .006;
  if (idle === 'breathe') scale *= 1 + .008 * Math.sin((tAbs + x) * 2);
  if (L.sprite && (L.mode || 'loop') === 'loop' && L.move) dy -= Math.abs(Math.sin(lt * (L.fps || 10) * Math.PI / L.sprite.frames.length * 2)) * H * .006;
  if (level > 0) { dy -= level * H * .012; rot += (level - .3) * 2.5; }
  const enter = L.enter ?? 'pop';
  if (enter === 'pop') { scale *= Math.max(.01, ez.back(clamp(lt / .35))); op = clamp(lt / .12); }
  if (enter === 'fade') op = clamp(lt / .35);
  if (enter === 'slide_l') x -= (1 - ez.out(clamp(lt / .5))) * .6;
  if (enter === 'slide_r') x += (1 - ez.out(clamp(lt / .5))) * .6;
  if (L.t1 != null && L.t1 - t < .2) op *= clamp((L.t1 - t) / .2);
  if (L.scroll) {
    const sw = W * (L.w || .9), sh = sw * ih / iw, k = clamp(t / Math.max(shot.dur, .01));
    const top = (L.scroll[0] + (L.scroll[1] - L.scroll[0]) * k) * H;
    return <Img src={staticFile(src)} style={{position: 'absolute', width: sw, height: sh, left: (W - sw) / 2, top}} />;
  }
  const w = h * iw / ih;
  const cx = (x - .5) * W * zz + W / 2, by = y * H + (y - .5) * (z - 1) * H * par;
  const ground = L.shadow ?? (L.cut !== false && !L.move?.y0 && (L.y ?? .95) >= .85);
  const sw = w * (L.shadowW ?? .62), shh = Math.max(10, h * .07);
  const shadow = ground ? <div style={{position: 'absolute', left: cx - sw / 2 + (L.shadowX ?? 0) * w, top: by - shh * .55 + (L.shadowY ?? 0) * h, width: sw, height: shh, borderRadius: '50%',
    background: 'radial-gradient(closest-side, rgba(20,12,8,.55), rgba(20,12,8,0))', opacity: op, filter: 'blur(2px)'}} /> : null;
  return (<>
    {shadow}
    {prevFi != null ? <Img src={staticFile(L.sprite.frames[prevFi])} style={{position: 'absolute', width: w, height: h, left: cx - w / 2, top: by - h + dy, opacity: op,
      transform: `scale(${scale}) rotate(${rot}deg) ${L.flip ? 'scaleX(-1)' : ''}`, transformOrigin: '50% 100%'}} /> : null}
    <Img src={staticFile(src)} style={{position: 'absolute', width: w, height: h, left: cx - w / 2, top: by - h + dy, opacity: op * (prevFi != null ? mixK : 1),
      transform: `scale(${scale}) rotate(${rot}deg) ${L.flip ? 'scaleX(-1)' : ''}`, transformOrigin: '50% 100%',
      filter: 'drop-shadow(0 6px 8px rgba(0,0,0,.28))'}} />
  </>);
};


// ---------------------------------------------------------------- rigged character: body + expression heads on a neck pivot
const RigLayer = ({L, t, tAbs, env, fps, W, H, z}) => {
  if (t < L.t0 || (L.t1 != null && t > L.t1)) return null;
  const R = L.rig, lt = t - L.t0;
  let level = 0;
  if (L.lineSpan && t >= L.lineSpan[0] && t <= L.lineSpan[1]) level = env[Math.round(tAbs * fps)] || 0;
  const par = .6, zz = 1 + (z - 1) * par;
  let h = (L.h ?? .6) * H * zz, op = 1, sc = 1;
  if ((L.enter ?? 'fade') === 'fade') op = clamp(lt / .35); else { sc = Math.max(.01, ez.back(clamp(lt / .35))); op = clamp(lt / .12); }
  const w = h * R.body.w / R.body.h, x = L.x ?? .5, y = L.y ?? 1;
  const cx = (x - .5) * W * zz + W / 2, by = y * H + (y - .5) * (z - 1) * H * par;
  const breathe = 1 + .006 * Math.sin(tAbs * 1.9);
  const left = cx - w / 2, top = by - h * breathe;
  const k = (w / R.body.w) * R.hscale;
  const nx = left + R.neck[0] / R.body.w * w, ny = top + R.neck[1] / R.body.h * h * breathe;
  // expression schedule with a 0.16 s cross-fade; a small anticipation nod when the expression changes
  const ex = R.expr; let i = 0; while (i + 1 < ex.length && ex[i + 1][0] <= t) i++;
  const cur = ex[i][1], since = t - ex[i][0], prev = i > 0 && since < .16 ? ex[i - 1][1] : null;
  const talking = level > .16;
  const pick = (e) => { const hs = R.heads[e] || {}; if (talking && hs.open && level > .16) return hs.open;
    if (!talking && hs.blink && blinkIndex(tAbs, x) === 2) return hs.blink; return hs.closed; };
  const nod = i > 0 ? -5 * Math.exp(-since * 7) * Math.sin(since * 14) : 0;
  const tilt = 1.4 * Math.sin(tAbs * 1.1 + x * 3) + (talking ? 1.8 * Math.sin(tAbs * 8.5) : 0) + nod;
  const head = (src, o) => src ? <Img src={staticFile(src)} style={{position: 'absolute', left: nx - R.hanchor[0] * k, top: ny - R.hanchor[1] * k,
    width: R.hw * k, height: R.hh * k, opacity: op * o, transform: `rotate(${tilt}deg)`, transformOrigin: `${R.hanchor[0] * k}px ${R.hanchor[1] * k}px`}} /> : null;
  return (
    <div style={{position: 'absolute', inset: 0, transform: `scale(${sc})`, transformOrigin: `${cx}px ${by}px`}}>
      {R.headBehind ? null : <Img src={staticFile(R.body.src)} style={{position: 'absolute', left, top, width: w, height: h * breathe, opacity: op}} />}
      {prev ? head(pick(prev), 1) : null}
      {head(pick(cur), prev ? clamp(since / .16) : 1)}
      {R.headBehind ? <Img src={staticFile(R.body.src)} style={{position: 'absolute', left, top, width: w, height: h * breathe, opacity: op}} /> : null}
    </div>);
};


// ---------------------------------------------------------------- face-patch character: master drawing + mouth / eye patches
const FaceLayer = ({L, t, tAbs, env, fps, W, H, z}) => {
  if (t < L.t0 || (L.t1 != null && t > L.t1)) return null;
  const F = L.face, lt = t - L.t0;
  let level = 0;
  const speaking = L.lineSpan && t >= L.lineSpan[0] && t <= L.lineSpan[1];
  if (speaking) level = env[Math.round(tAbs * fps)] || 0;
  const par = .6, zz = 1 + (z - 1) * par, h = (L.h ?? .6) * H * zz, op = clamp(lt / .35);
  const w = h * F.master.w / F.master.h, x = L.x ?? .5, y = L.y ?? 1;
  const cx = (x - .5) * W * zz + W / 2, by = y * H + (y - .5) * (z - 1) * H * par, k = w / F.master.w;
  // mouth: shape from the sound timing while speaking, otherwise the master's closed mouth
  let mouth = null;
  if (speaking && L.mouth) { let i = -1; for (let j = 0; j < L.mouth.length && L.mouth[j][0] <= t; j++) i = j; if (i >= 0) mouth = L.mouth[i][1]; }
  if (mouth === 'rest') mouth = F.patches.m_rest ? 'rest' : null;
  // eyes/brows from the emotion schedule (0.16 s fade); blinks when neutral
  const ex = F.expr; let i = 0; while (i + 1 < ex.length && ex[i + 1][0] <= t) i++;
  const cur = ex[i][1], since = t - ex[i][0], prev = i > 0 && since < .16 ? ex[i - 1][1] : null;
  const eyeOf = (e) => e === 'brow' ? 'e_brow' : e === 'pained' ? 'e_pained' : (blinkIndex(tAbs, x) === 2 ? 'e_blink' : null);
  // whole-figure motion: gentle sway, a small nod on stressed syllables, a lean when the expression changes
  const nod = i > 0 ? 1.6 * Math.exp(-since * 6) * Math.sin(since * 12) : 0;
  const rot = .5 * Math.sin(tAbs * 1.1 + x * 3) + (speaking ? level * 1.4 * Math.sin(tAbs * 7) : 0) + nod;
  const breathe = 1 + .005 * Math.sin(tAbs * 1.9);
  const patch = (nm, o = 1) => { const P = F.patches[nm]; return P ? <Img key={nm + o} src={staticFile(P.src)} style={{position: 'absolute', left: P.x * k, top: P.y * k, width: P.w * k, height: P.h * k, opacity: o}} /> : null; };
  return (
    <div style={{position: 'absolute', left: cx - w / 2, top: by - h, width: w, height: h, opacity: op,
      transform: `rotate(${rot}deg) scale(${breathe})`, transformOrigin: '50% 100%'}}>
      <Img src={staticFile(F.master.src)} style={{position: 'absolute', left: 0, top: 0, width: w, height: h}} />
      {prev && eyeOf(prev) ? patch(eyeOf(prev), 1) : null}
      {eyeOf(cur) ? patch(eyeOf(cur), prev ? clamp(since / .16) : 1) : null}
      {mouth ? patch('m_' + mouth) : null}
    </div>);
};

// foreground overlay (desk, chairs) drawn ABOVE the characters with the same framing as a flat background
const Foreground = ({shot, u, W, H}) => {
  const [z0, z1, p0 = [0, 0], p1 = [0, 0]] = shot.cam;
  const z = z0 + (z1 - z0) * u, px = p0[0] + (p1[0] - p0[0]) * u, py = p0[1] + (p1[1] - p0[1]) * u, m = 1.25;
  const tx = -px * (W * m - W / z) / 2 * z, ty = -py * (H * m - H / z) / 2 * z;
  return (
    <AbsoluteFill style={{overflow: 'hidden', pointerEvents: 'none'}}>
      <div style={{position: 'absolute', width: W * m, height: H * m, left: (W - W * m) / 2, top: (H - H * m) / 2,
        transform: `translate(${tx}px, ${ty}px) scale(${z})`, transformOrigin: '50% 50%'}}>
        <Img src={staticFile(shot.fg.src)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </div>
    </AbsoluteFill>);
};

// ---------------------------------------------------------------- text / motion graphics
const outline = (px, col = INK) => ({WebkitTextStroke: `${px}px ${col}`, paintOrder: 'stroke fill'});

const Text = ({T, t, W, H}) => {
  if (t < T.t0 || (T.t1 != null && t > T.t1)) return null;
  const lt = t - T.t0, anim = T.anim || 'pop';
  const size = (T.size || 64) * W / 1920;
  let scale = 1, op = clamp(lt / .15), clip = 100;
  if (anim === 'pop') scale = Math.max(.01, ez.back(clamp(lt / .3)));
  if (anim === 'stamp') { scale = 1 + 1.6 * (1 - ez.out(clamp(lt / .18))); op = clamp(lt / .05); }
  if (anim === 'type') clip = 100 * clamp(lt / (T.dur || 1.2));
  let shown = T.text, cursor = null;
  if (anim === 'typewriter') {
    const n = Math.floor(Math.max(0, lt) * (T.cps || 26)); shown = T.text.slice(0, n);
    if (n < T.text.length || Math.floor(lt * 2) % 2 === 0) cursor = <span style={{opacity: n < T.text.length ? 1 : .8}}>▍</span>;
  }
  if (T.t1 != null && T.t1 - t < .2) op *= clamp((T.t1 - t) / .2);
  const base = {position: 'absolute', left: (T.x ?? .5) * W, top: (T.y ?? .2) * H, transform: `translate(-50%,-50%) scale(${scale}) rotate(${T.tilt || 0}deg)`,
    opacity: op, clipPath: clip >= 100 ? 'none' : `inset(-40% ${100 - clip}% -40% -20%)`, padding: `${size * .12}px ${size * .18}px`, maxWidth: (T.maxw || .8) * W, textAlign: 'center', whiteSpace: 'pre-wrap'};
  const k = T.kind;
  if (k === 'pill' || k === 'label') return (
    <div style={{...base, fontFamily: 'Luckiest', fontSize: size, color: RED, background: YELLOW, padding: `${size * .28}px ${size * .55}px ${size * .18}px`,
      borderRadius: size, border: `${Math.max(3, size * .08)}px solid white`, boxShadow: '0 8px 0 rgba(0,0,0,.25)', textTransform: 'uppercase', whiteSpace: 'nowrap', maxWidth: 'none'}}>{T.text}</div>);
  if (k === 'title' || k === 'big') return (
    <div style={{...base, fontFamily: 'Luckiest', fontSize: size, color: k === 'title' ? YELLOW : 'white', ...outline(size * .14), textShadow: '0 6px 0 rgba(0,0,0,.35)', lineHeight: 1.05}}>{T.text}</div>);
  if (k === 'note' || k === 'quote') return (
    <div style={{...base, fontFamily: 'Marker', fontSize: size, color: INK, background: k === 'note' ? '#FFEC96' : CREAM, padding: size * .6, borderLeft: k === 'quote' ? `${size * .2}px solid ${RED}` : 'none',
      boxShadow: '8px 10px 0 rgba(0,0,0,.25)', textAlign: 'left', lineHeight: 1.25, transform: base.transform + (k === 'note' ? ' rotate(-1.5deg)' : '')}}>
      {shown}{cursor}{T.src ? <div style={{fontSize: size * .5, color: RED, marginTop: size * .3, opacity: shown.length >= T.text.length ? 1 : 0}}>{T.src}</div> : null}</div>);
  if (k === 'paper') {
    // a clean typed document card: typewriter font, the key phrase gets a highlighter swipe once it has been typed
    const hl = T.highlight || '', hi = hl ? T.text.indexOf(hl) : -1;
    const typedAll = shown.length >= T.text.length, tDone = (T.text.length / (T.cps || 26));
    const hk = clamp((lt - tDone - .15) / .5);
    const part = (a, b) => shown.slice(a, Math.min(b, shown.length));
    const body = hi < 0 ? [shown] : [part(0, hi),
      <span key="h" style={{background: `linear-gradient(90deg, rgba(255,210,0,.75) ${hk * 100}%, transparent ${hk * 100}%)`, padding: '0 .08em'}}>{part(hi, hi + hl.length)}</span>,
      part(hi + hl.length, T.text.length)];
    return (
      <div style={{...base, fontFamily: 'Typewriter', fontSize: size, color: '#1d1a17', background: '#F6F0E1', padding: `${size * .9}px ${size * 1.1}px`, textAlign: 'left', lineHeight: 1.55,
        boxShadow: '0 18px 40px rgba(0,0,0,.35), inset 0 0 60px rgba(150,120,60,.18)', borderTop: `${size * .25}px solid #E9DFC6`}}>
        {T.head ? <div style={{fontSize: size * .62, color: RED, letterSpacing: '.08em', marginBottom: size * .5, textTransform: 'uppercase'}}>{T.head}</div> : null}
        {body}{!typedAll ? cursor : null}
      </div>);
  }
  if (k === 'slot') {
    // end-screen placeholder where YouTube puts a video card: dashed frame + label (the card covers it on YouTube)
    const bw = (T.w || .34) * W, bh = (T.h || .32) * H;
    return (
      <div style={{position: 'absolute', left: (T.x ?? .5) * W - bw / 2, top: (T.y ?? .5) * H - bh / 2, width: bw, height: bh, opacity: op,
        transform: `scale(${scale})`, border: `${size * .1}px dashed rgba(255,255,255,.85)`, borderRadius: size * .4, background: 'rgba(20,18,18,.35)'}}>
        <div style={{position: 'absolute', left: size * .5, top: -size * .75, fontFamily: 'Luckiest', fontSize: size, color: RED, background: YELLOW,
          padding: `${size * .25}px ${size * .5}px ${size * .12}px`, borderRadius: size, border: `${Math.max(3, size * .08)}px solid white`, whiteSpace: 'nowrap'}}>{T.text}</div>
      </div>);
  }
  if (k === 'callout') {
    // label in clear space + a dotted leader line and dot at the exact spot it refers to (ax, ay)
    const ax = T.ax * W, ay = T.ay * H, lx = (T.x ?? .5) * W, ly = (T.y ?? .2) * H, lk = clamp(lt / .35);
    return (<>
      <svg style={{position: 'absolute', left: 0, top: 0, width: W, height: H, overflow: 'visible', opacity: op}}>
        <line x1={lx} y1={ly} x2={lx + (ax - lx) * lk} y2={ly + (ay - ly) * lk} stroke="white" strokeWidth={size * .09} strokeDasharray={`${size * .25} ${size * .2}`} strokeLinecap="round" />
        <circle cx={ax} cy={ay} r={size * .22 * ez.back(clamp((lt - .3) / .25))} fill={YELLOW} stroke="white" strokeWidth={size * .07} />
      </svg>
      <div style={{...base, fontFamily: 'Luckiest', fontSize: size, color: RED, background: YELLOW, padding: `${size * .28}px ${size * .55}px ${size * .18}px`,
        borderRadius: size, border: `${Math.max(3, size * .08)}px solid white`, boxShadow: '0 8px 0 rgba(0,0,0,.25)', textTransform: 'uppercase', whiteSpace: 'nowrap', maxWidth: 'none'}}>{T.text}</div>
    </>);
  }
  if (k === 'chalk') return (<div style={{...base, fontFamily: 'Marker', fontSize: size, color: '#F5F3EA', textShadow: '0 0 2px rgba(255,255,255,.6)'}}>{T.text}</div>);
  return null;
};

const Particles = ({p, t, W, H}) => {
  const n = p.n || 30, kind = p.kind || 'dust', items = [];
  if (kind === 'ink') {
    const lt = t - (p.t0 || 0); if (lt < 0 || lt > 1.4) return null;
    for (let i = 0; i < n; i++) {
      const ang = random('a' + i) * Math.PI * 2, sp = (.08 + random('v' + i) * .22) * W, r = 4 + random('r' + i) * 14;
      const k = ez.out(clamp(lt / .35)), x = p.x * W + Math.cos(ang) * sp * k, y = p.y * H + Math.sin(ang) * sp * k * .6 + lt * lt * H * .15;
      items.push(<div key={i} style={{position: 'absolute', left: x, top: y, width: r, height: r, borderRadius: '50%', background: '#B3141B', opacity: clamp((1.4 - lt) / .5)}} />);
    }
    return <AbsoluteFill style={{pointerEvents: 'none'}}>{items}</AbsoluteFill>;
  }
  for (let i = 0; i < n; i++) {
    const xs = random('x' + i), ph = random('p' + i), sp = .5 + random('s' + i), sz = random('z' + i);
    if (kind === 'leaves') {
      const u = ((t / (7 / sp)) + ph) % 1, x = (xs + .08 * Math.sin(t * 1.3 + i)) * W, y = (u * 1.2 - .1) * H, r = 10 + sz * 12;
      items.push(<div key={i} style={{position: 'absolute', left: x, top: y, width: r * 2, height: r, borderRadius: '50%',
        background: ['#C4692A', '#AA501E', '#DC9628', '#8C3C1E'][i % 4], transform: `rotate(${(t * 90 * sp + i * 40) % 360}deg)`, opacity: .9}} />);
    } else if (kind === 'paper') {
      const u = ((t / (6 / sp)) + ph) % 1, x = (xs + .1 * Math.sin(t * 1.1 + i)) * W, y = (u * 1.2 - .1) * H, s = 16 + sz * 18;
      items.push(<div key={i} style={{position: 'absolute', left: x, top: y, width: s * 1.4, height: s, background: '#F5F0E4',
        boxShadow: '0 2px 4px rgba(0,0,0,.3)', transform: `rotate(${t * 120 * sp + i * 30}deg) skewX(${10 * Math.sin(t * 3 + i)}deg)`}} />);
    } else {
      const u = ((t / (12 / sp)) + ph) % 1, x = (xs + .03 * Math.sin(t * .7 + i)) * W, y = (1.05 - u * 1.1) * H, r = 2 + sz * 3;
      items.push(<div key={i} style={{position: 'absolute', left: x, top: y, width: r * 2, height: r * 2, borderRadius: '50%', background: 'rgba(255,240,200,.55)', filter: 'blur(1px)'}} />);
    }
  }
  return <AbsoluteFill style={{pointerEvents: 'none'}}>{items}</AbsoluteFill>;
};

// ---------------------------------------------------------------- shot + episode
// ShotView draws one shot at local time t into a W x H box. view = [x0, x1] visible fraction (Shorts) keeps text inside.
export const ShotView = ({shot, t, env, fps, W, H, view, hideTexts}) => {
  const tAbs = shot.start + t;
  const u = ez.smooth(clamp(t / Math.max(shot.dur, .01)));
  const [z0, z1] = shot.cam; const z = z0 + (z1 - z0) * u;
  let sx = 0, sy = 0;
  for (const [a, d, m] of (shot.shake || [])) if (t >= a && t <= a + d) { const k = 1 - (t - a) / d; sx += Math.sin(t * 83) * m * k; sy += Math.cos(t * 71) * m * k; }
  let style = {};
  const td = shot.transDur || .25;
  if (t < td && shot.trans === 'whip') { const k = ez.out(clamp(t / td)); style = {transform: `translateX(${(1 - k) * W}px)`, filter: `blur(${(1 - k) * 18}px)`}; }
  else if (t < td && shot.trans === 'dissolve') style = {opacity: clamp(t / td)};
  const box = {position: 'absolute', left: 0, top: 0, width: W, height: H, overflow: 'hidden'};
  const texts = (shot.texts || []).map((T) => {
    if (!view) return T;
    const vw = view[1] - view[0], m = .06 * vw;
    return {...T, x: Math.min(Math.max(T.x ?? .5, view[0] + m + vw * .3), view[1] - m - vw * .3), maxw: Math.min(T.maxw || .8, vw * .9), size: (T.size || 64) * .95};
  });
  return (
    <div style={{...box, ...style}}>
      <div style={{...box, transform: `translate(${sx}px, ${sy}px) scale(${sx || sy ? 1.03 : 1})`}}>
        <Background shot={shot} u={u} t={t} W={W} H={H} />
        {(shot.layers || []).map((L, i) => {
          if (shot.fg && L.front) return null;   // drawn after the foreground layer
          let LL = L;
          if (view && L.image && L.fitWidth) {
            const wf = (view[1] - view[0]) * .96, hf = wf * W / H * L.image.h / L.image.w;
            LL = {...L, x: (view[0] + view[1]) / 2, h: hf, y: .5 + hf / 2};
          }
          if (L.rig) return <RigLayer key={i} L={L} t={t} tAbs={tAbs} env={env} fps={fps} W={W} H={H} z={view ? 1 : z} />;
          if (L.face) return <FaceLayer key={i} L={L} t={t} tAbs={tAbs} env={env} fps={fps} W={W} H={H} z={view ? 1 : z} />;
          return <Layer key={i} L={LL} t={t} tAbs={tAbs} shot={shot} env={env} fps={fps} W={W} H={H} z={view ? 1 : z} />;
        })}
        {shot.fg ? <Foreground shot={shot} u={u} W={W} H={H} /> : null}
        {shot.fg ? (shot.layers || []).map((L, i) => L.front ? (L.rig ? <RigLayer key={'f' + i} L={L} t={t} tAbs={tAbs} env={env} fps={fps} W={W} H={H} z={z} />
          : <Layer key={'f' + i} L={L} t={t} tAbs={tAbs} shot={shot} env={env} fps={fps} W={W} H={H} z={z} />) : null) : null}
        {shot.particles ? <Particles p={shot.particles} t={tAbs} W={W} H={H} /> : null}
        {(shot.ink || []).map((p, i) => <Particles key={'ink' + i} p={{...p, kind: 'ink'}} t={t} W={W} H={H} />)}
      </div>
      {hideTexts ? null : texts.map((T, i) => <Text key={i} T={T} t={t} W={W} H={H} />)}
      <div style={{...box, background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 60%, rgba(0,0,0,.28) 100%)', pointerEvents: 'none'}} />
    </div>
  );
};

const Shot = ({shot, env}) => {
  const frame = useCurrentFrame(); const {fps, width: W, height: H} = useVideoConfig();
  return <ShotView shot={shot} t={frame / fps} env={env} fps={fps} W={W} H={H} />;
};

export const Episode = ({data}) => {
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill style={{background: 'black'}}>
      <Fonts />
      {data.shots.map((s, i) => {
        const nxt = data.shots[i + 1];
        const extra = nxt ? Math.round((nxt.transDur || 0) * fps) + 1 : 0;
        return (
          <Sequence key={i} from={Math.round(s.start * fps)} durationInFrames={Math.max(1, Math.round(s.dur * fps) + extra)}>
            <Shot shot={s} env={data.env} />
          </Sequence>
        );
      })}
      {data.audio ? <Audio src={staticFile(data.audio)} /> : null}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- vertical Shorts (1080 x 1920)
// data.short = {segments: [[srcStart, srcEnd, outStart]], words: [{w, s, e}] (output time), hook, title, outro: {start, dur, env}}
const shotAt = (shots, ts) => { let i = 0; while (i + 1 < shots.length && shots[i + 1].start <= ts) i++; return i; };

export const Short = ({data}) => {
  const frame = useCurrentFrame(); const {fps} = useVideoConfig();
  const S = data.short, tOut = frame / fps;
  const SW = 1920, SH = 1080, WIN = 1080, K = WIN / SW, TOP = 600, SHV = SH * K;
  let scene = null;
  const seg = S.segments.find(([a, b, o]) => tOut >= o && tOut < o + (b - a));
  if (seg) {
    const ts = seg[0] + (tOut - seg[2]);
    const i = shotAt(data.shots, ts), shot = data.shots[i];
    const td = shot.transDur || .25;
    const prev = i > 0 && ts - shot.start < td ? data.shots[i - 1] : null;
    scene = (
      <div style={{position: 'absolute', left: 0, top: 0, width: SW, height: SH, transform: `scale(${K})`, transformOrigin: '0 0'}}>
        {prev ? <ShotView key={'s' + (i - 1)} shot={prev} t={ts - prev.start} env={data.env} fps={fps} W={SW} H={SH} /> : null}
        <ShotView key={'s' + i} shot={{...shot, trans: shot.trans === 'whip' ? 'dissolve' : shot.trans}} t={ts - shot.start} env={data.env} fps={fps} W={SW} H={SH} />
      </div>
    );
  }
  // captions: groups of up to 3 words, active word in yellow
  let cap = null;
  const ws = S.words, idx = ws.findIndex((w) => tOut >= w.s - .03 && tOut <= Math.max(w.e, w.s + .25) + .15);
  if (idx >= 0 && !S.outro || (idx >= 0 && tOut < S.outro.start)) {
    const g0 = idx - (idx % 3), group = ws.slice(g0, g0 + 3);
    cap = (
      <div style={{position: 'absolute', top: TOP + SHV + 70, left: 50, right: 50, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', columnGap: 26, rowGap: 6, fontFamily: 'Luckiest', fontSize: 88, lineHeight: 1.1, ...outline(10)}}>
        {group.map((w, k) => <span key={k} style={{color: g0 + k === idx ? YELLOW : 'white'}}>{w.w.toUpperCase()}</span>)}
      </div>);
  }
  const hookOp = clamp((3.2 - tOut) / .3) * clamp(tOut / .15);
  const inOutro = S.outro && tOut >= S.outro.start;
  let outro = null;
  if (inOutro) {
    const lt = tOut - S.outro.start, lvl = S.outro.env[Math.round(lt * fps)] || 0;
    const fr = data.mascotTalk; const fi = lvl > .42 ? 2 : lvl > .14 ? 1 : (blinkIndex(tOut, .3) === 2 ? 3 : 0);
    outro = (
      <AbsoluteFill style={{background: 'linear-gradient(#1E5F5F, #123B3B)'}}>
        <div style={{position: 'absolute', top: 170, width: '100%', textAlign: 'center'}}>
          <div style={{display: 'inline-block', fontFamily: 'Luckiest', fontSize: 44, color: RED, background: YELLOW, padding: '14px 34px 8px', borderRadius: 60, border: '5px solid white'}}>{S.series}</div>
        </div>
        <div style={{position: 'absolute', top: 290, left: 60, right: 60, textAlign: 'center', fontFamily: 'Luckiest', fontSize: 92, color: YELLOW, lineHeight: 1.05, ...outline(12),
          transform: `scale(${ez.back(clamp(lt / .35))})`}}>{S.episodeTitle}</div>
        <div style={{position: 'absolute', top: 560, width: '100%', textAlign: 'center', opacity: clamp((lt - .4) / .3)}}>
          <span style={{fontFamily: 'Marker', fontSize: 56, background: '#FFEC96', color: INK, padding: '18px 36px', boxShadow: '8px 10px 0 rgba(0,0,0,.25)'}}>Full story on the channel</span>
        </div>
        <Img src={staticFile(fr.frames[fi])} style={{position: 'absolute', left: 540 - 330, top: 760 - lvl * 18, width: 660, height: 660 * fr.h / fr.w}} />
        <div style={{position: 'absolute', top: 1560, width: '100%', textAlign: 'center', opacity: clamp((lt - .8) / .3)}}>
          <div style={{display: 'inline-block', fontFamily: 'Luckiest', fontSize: 52, color: RED, background: YELLOW, padding: '16px 40px 10px', borderRadius: 60, border: '5px solid white'}}>Follow Your Channel</div>
        </div>
        <div style={{position: 'absolute', top: 1700, width: '100%', textAlign: 'center', opacity: clamp((lt - 1.2) / .3)}}>
          <div style={{display: 'inline-block', fontFamily: 'Luckiest', fontSize: 48, color: 'white', background: RED, padding: '16px 40px 10px', borderRadius: 60, border: '5px solid white'}}>Subscribe to Your Channel</div>
        </div>
      </AbsoluteFill>);
  }
  return (
    <AbsoluteFill style={{background: 'linear-gradient(#1E5F5F 0%, #143F3F 45%, #0E2A2A 100%)'}}>
      <Fonts />
      <div style={{position: 'absolute', left: 0, top: TOP, width: WIN, height: SHV, overflow: 'hidden', boxShadow: '0 0 0 6px #F3EBDD, 0 18px 40px rgba(0,0,0,.5)'}}>{scene}</div>
      <div style={{position: 'absolute', top: 110, width: '100%', textAlign: 'center'}}>
        <div style={{display: 'inline-block', fontFamily: 'Luckiest', fontSize: 46, color: RED, background: YELLOW, padding: '14px 34px 8px', borderRadius: 60, border: '5px solid white'}}>{S.series}</div>
      </div>
      <div style={{position: 'absolute', top: 230, left: 50, right: 50, height: 330, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center'}}>
        {hookOp > 0
          ? <div style={{fontFamily: 'Luckiest', fontSize: 92, color: YELLOW, lineHeight: 1.04, ...outline(12), opacity: hookOp, transform: `scale(${ez.back(clamp(tOut / .35))})`}}>{S.hook}</div>
          : <div style={{fontFamily: 'Luckiest', fontSize: 78, color: 'white', lineHeight: 1.05, ...outline(10), opacity: clamp((tOut - 3.2) / .3)}}>{S.episodeTitle}</div>}
      </div>
      {cap}
      {outro}
      {data.audio ? <Audio src={staticFile(data.audio)} /> : null}
    </AbsoluteFill>
  );
};
