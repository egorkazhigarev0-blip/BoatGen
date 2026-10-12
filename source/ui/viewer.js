/* BoatGen 3D preview: a small WebGL orbit viewer (no libraries).
   Input: scene {prims, lo, hi} from engine/mesh.py, game coordinates in cm (X fwd, Y right, Z up).
   GL space: metres, x = X, y = Z (up), z = Y. */
(function () {
  "use strict";

  // ------------------------------------------------------------------ unit shape templates
  // each template: flat array of vertices [lx, ly, lz, nx, ny, nz] (triangles), local unit cube [-.5, .5]
  function quad(out, a, b, c, d, n) {
    for (const p of [a, b, c, a, c, d]) out.push(p[0], p[1], p[2], n[0], n[1], n[2]);
  }
  function tri(out, a, b, c, n) {
    for (const p of [a, b, c]) out.push(p[0], p[1], p[2], n[0], n[1], n[2]);
  }
  function boxT(x0, x1, y0, y1, z0, z1, out) {
    out = out || [];
    quad(out, [x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1], [1, 0, 0]);
    quad(out, [x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [-1, 0, 0]);
    quad(out, [x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [0, 1, 0]);
    quad(out, [x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1], [0, -1, 0]);
    quad(out, [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [0, 0, 1]);
    quad(out, [x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0], [0, 0, -1]);
    return out;
  }
  function rampT() {
    const o = [], h = 0.5;
    const A = (y) => [-h, y, -h], B = (y) => [h, y, -h], C = (y) => [-h, y, h];
    tri(o, A(-h), B(-h), C(-h), [0, -1, 0]);
    tri(o, A(h), C(h), B(h), [0, 1, 0]);
    quad(o, A(-h), A(h), B(h), B(-h), [0, 0, -1]);
    quad(o, A(-h), C(-h), C(h), A(h), [-1, 0, 0]);
    quad(o, B(-h), B(h), C(h), C(-h), [0.7071, 0, 0.7071]);
    return o;
  }
  function rampRoundT() {
    const o = [], h = 0.5, N = 10;
    const P = (t, y) => [-h + Math.cos(t), y, -h + Math.sin(t)];
    for (let i = 0; i < N; i++) {
      const t0 = (i / N) * Math.PI / 2, t1 = ((i + 1) / N) * Math.PI / 2;
      tri(o, [-h, -h, -h], P(t0, -h), P(t1, -h), [0, -1, 0]);
      tri(o, [-h, h, -h], P(t1, h), P(t0, h), [0, 1, 0]);
      const n0 = [Math.cos(t0), 0, Math.sin(t0)], n1 = [Math.cos(t1), 0, Math.sin(t1)];
      const a = P(t0, -h), b = P(t0, h), c = P(t1, h), d = P(t1, -h);
      o.push(...a, ...n0, ...b, ...n0, ...c, ...n1, ...a, ...n0, ...c, ...n1, ...d, ...n1);
    }
    quad(o, [-h, -h, -h], [-h, h, -h], [h, h, -h], [h, -h, -h], [0, 0, -1]);
    quad(o, [-h, -h, -h], [-h, -h, h], [-h, h, h], [-h, h, -h], [-1, 0, 0]);
    return o;
  }
  function ring(N, f) {
    const r = [];
    for (let i = 0; i <= N; i++) { const a = (i / N) * Math.PI * 2; r.push(f(Math.cos(a), Math.sin(a))); }
    return r;
  }
  function cylT(N) {
    const o = [], h = 0.5;
    const R = ring(N, (c, s) => [c * h, s * h, c, s]);
    for (let i = 0; i < N; i++) {
      const a = R[i], b = R[i + 1];
      o.push(a[0], a[1], -h, a[2], a[3], 0, b[0], b[1], -h, b[2], b[3], 0, b[0], b[1], h, b[2], b[3], 0);
      o.push(a[0], a[1], -h, a[2], a[3], 0, b[0], b[1], h, b[2], b[3], 0, a[0], a[1], h, a[2], a[3], 0);
      tri(o, [0, 0, h], [a[0], a[1], h], [b[0], b[1], h], [0, 0, 1]);
      tri(o, [0, 0, -h], [b[0], b[1], -h], [a[0], a[1], -h], [0, 0, -1]);
    }
    return o;
  }
  function coneT(N) {
    const o = [], h = 0.5;
    const R = ring(N, (c, s) => [c * h, s * h, c, s]);
    for (let i = 0; i < N; i++) {
      const a = R[i], b = R[i + 1];
      const na = [a[2], a[3], 0.5], nb = [b[2], b[3], 0.5];
      o.push(a[0], a[1], -h, ...na, b[0], b[1], -h, ...nb, 0, 0, h, (a[2] + b[2]) / 2, (a[3] + b[3]) / 2, 0.5);
      tri(o, [0, 0, -h], [b[0], b[1], -h], [a[0], a[1], -h], [0, 0, -1]);
    }
    return o;
  }
  function hemiT(N, M) {
    const o = [], h = 0.5;
    const pt = (th, ph) => {
      const x = 0.5 * Math.sin(th) * Math.cos(ph), y = 0.5 * Math.sin(th) * Math.sin(ph), z = Math.cos(th);
      return [x, y, z - h, x * 4, y * 4, z];
    };
    for (let j = 0; j < M; j++) {
      const t0 = (j / M) * Math.PI / 2, t1 = ((j + 1) / M) * Math.PI / 2;
      for (let i = 0; i < N; i++) {
        const p0 = (i / N) * Math.PI * 2, p1 = ((i + 1) / N) * Math.PI * 2;
        const a = pt(t0, p0), b = pt(t1, p0), c = pt(t1, p1), d = pt(t0, p1);
        o.push(...a, ...b, ...c, ...a, ...c, ...d);
      }
    }
    const R = ring(N, (c, s) => [c * h, s * h]);
    for (let i = 0; i < N; i++) tri(o, [0, 0, -h], [R[i + 1][0], R[i + 1][1], -h], [R[i][0], R[i][1], -h], [0, 0, -1]);
    return o;
  }
  function seatT() {
    const o = boxT(-0.5, 0.5, -0.5, 0.5, 0, 0.22);
    boxT(-0.5, -0.3, -0.5, 0.5, 0.22, 1.0, o);
    boxT(-0.3, 0.35, -0.5, -0.38, 0.22, 0.45, o);
    boxT(-0.3, 0.35, 0.38, 0.5, 0.22, 0.45, o);
    return o;
  }
  function gunT() {
    const o = boxT(-0.5, 0.5, -0.5, 0.5, -0.5, 0.5);
    const N = 12, L0 = 0.5, L1 = 2.3, ry = 0.17, rz = 0.19;
    const R = ring(N, (c, s) => [c, s]);
    for (let i = 0; i < N; i++) {
      const a = R[i], b = R[i + 1];
      const A0 = [L0, a[0] * ry, a[1] * rz], A1 = [L1, a[0] * ry, a[1] * rz];
      const B0 = [L0, b[0] * ry, b[1] * rz], B1 = [L1, b[0] * ry, b[1] * rz];
      const na = [0, a[0] / ry, a[1] / rz], nb = [0, b[0] / ry, b[1] / rz];
      o.push(...A0, ...na, ...B0, ...nb, ...B1, ...nb, ...A0, ...na, ...B1, ...nb, ...A1, ...na);
    }
    return o;
  }
  const T = [boxT(-0.5, 0.5, -0.5, 0.5, -0.5, 0.5), rampT(), rampRoundT(), cylT(20), coneT(18), hemiT(16, 6), seatT(), gunT()];

  // ------------------------------------------------------------------ shaders
  const VS = `
attribute vec3 a_pos; attribute vec3 a_nrm; attribute vec4 a_col; attribute float a_mat;
uniform mat4 u_vp;
varying vec3 v_n; varying vec4 v_col; varying float v_mat; varying vec3 v_w;
void main() { v_n = a_nrm; v_col = a_col; v_mat = a_mat; v_w = a_pos; gl_Position = u_vp * vec4(a_pos, 1.0); }`;
  const FS = `
precision mediump float;
uniform vec3 u_eye; uniform float u_water; uniform vec3 u_wc;
varying vec3 v_n; varying vec4 v_col; varying float v_mat; varying vec3 v_w;
void main() {
  vec3 n = normalize(v_n);
  vec3 V = normalize(u_eye - v_w);
  if (dot(n, V) < 0.0) n = -n;
  vec3 base = pow(v_col.rgb, vec3(2.2));
  float m = v_mat;
  vec3 L1 = normalize(vec3(0.45, 0.85, 0.35));
  vec3 L2 = normalize(vec3(-0.6, 0.35, -0.55));
  vec3 amb = mix(vec3(0.10, 0.09, 0.08), vec3(0.32, 0.38, 0.46), n.y * 0.5 + 0.5);
  float d1 = max(dot(n, L1), 0.0), d2 = max(dot(n, L2), 0.0);
  vec3 col = base * (amb + d1 * vec3(1.05, 1.0, 0.94) + d2 * vec3(0.16, 0.2, 0.26));
  float ks = 0.12, sh = 24.0;
  if (m > 0.5 && m < 1.5) { ks = 0.55; sh = 48.0; }
  else if (m > 1.5 && m < 2.5) { ks = 0.9; sh = 90.0; }
  else if (m > 3.5 && m < 4.5) { ks = 0.03; sh = 8.0; }
  vec3 H = normalize(L1 + V);
  col += ks * pow(max(dot(n, H), 0.0), sh) * vec3(1.0);
  float a = v_col.a;
  if (m > 2.5 && m < 3.5) { col = base * 1.6 + 0.15; }
  if (m > 4.5) {
    float fr = pow(1.0 - max(dot(n, V), 0.0), 3.0);
    col = mix(vec3(0.02, 0.09, 0.15), vec3(0.25, 0.42, 0.55), fr) + 0.6 * pow(max(dot(n, H), 0.0), 120.0);
    a = mix(0.55, 0.85, fr) * (1.0 - smoothstep(u_wc.z * 0.3, u_wc.z, length(v_w.xz - u_wc.xy)));
  } else if (v_w.y < u_water) {
    col = mix(col, vec3(0.02, 0.12, 0.17), 0.35);
  }
  gl_FragColor = vec4(pow(col, vec3(1.0 / 2.2)), a);
}`;

  function compile(gl, type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }

  // ------------------------------------------------------------------ math
  function persp(fov, asp, n, f) {
    const t = 1 / Math.tan(fov / 2);
    return [t / asp, 0, 0, 0, 0, t, 0, 0, 0, 0, (f + n) / (n - f), -1, 0, 0, (2 * f * n) / (n - f), 0];
  }
  function lookAt(e, c, u) {
    let z = [e[0] - c[0], e[1] - c[1], e[2] - c[2]];
    let l = Math.hypot(...z); z = z.map((v) => v / l);
    let x = [u[1] * z[2] - u[2] * z[1], u[2] * z[0] - u[0] * z[2], u[0] * z[1] - u[1] * z[0]];
    l = Math.hypot(...x); x = x.map((v) => v / l);
    const y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]];
    return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0,
      -(x[0] * e[0] + x[1] * e[1] + x[2] * e[2]), -(y[0] * e[0] + y[1] * e[1] + y[2] * e[2]),
      -(z[0] * e[0] + z[1] * e[1] + z[2] * e[2]), 1];
  }
  function mmul(a, b) {
    const o = new Array(16);
    for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
      let s = 0;
      for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k];
      o[i * 4 + j] = s;
    }
    return o;
  }

  // ------------------------------------------------------------------ viewer
  function Viewer(canvas) {
    this.canvas = canvas;
    const gl = canvas.getContext("webgl", { antialias: true, alpha: true, premultipliedAlpha: false, preserveDrawingBuffer: false });
    this.gl = gl;
    if (!gl) return;
    const p = gl.createProgram();
    gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, VS));
    gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(p);
    this.prog = p;
    this.loc = {
      pos: gl.getAttribLocation(p, "a_pos"), nrm: gl.getAttribLocation(p, "a_nrm"),
      col: gl.getAttribLocation(p, "a_col"), mat: gl.getAttribLocation(p, "a_mat"),
      vp: gl.getUniformLocation(p, "u_vp"), eye: gl.getUniformLocation(p, "u_eye"), water: gl.getUniformLocation(p, "u_water"), wc: gl.getUniformLocation(p, "u_wc"),
    };
    this.buf = gl.createBuffer();
    this.counts = null;
    this.yaw0 = 0.62; this.pitch0 = 0.36;
    this.yaw = 0.62; this.pitch = 0.36; this.dist = 10; this.target = [0, 0, 0]; this.radius = 5;
    this.vyaw = 0; this.vpitch = 0; this.auto = true; this.zoom = 1;
    this.water = -1e3; this.showWater = true;
    this._bind();
    const ro = new ResizeObserver(() => { this._resize(); this.base = null; });
    ro.observe(canvas);
    this._resize();
    let last = performance.now();
    const loop = (t) => {
      const dt = Math.min(0.05, (t - last) / 1000); last = t;
      if (this.auto && this.autoRotate !== false) this.yaw += dt * 0.22;
      if (!this.drag) {
        this.yaw += this.vyaw; this.pitch += this.vpitch;
        this.vyaw *= 0.92; this.vpitch *= 0.92;
      }
      this.pitch = Math.max(0.04, Math.min(1.35, this.pitch));
      this.zoomS = this.zoomS == null ? this.zoom : this.zoomS + (this.zoom - this.zoomS) * 0.15;
      this.draw();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  Viewer.prototype._bind = function () {
    const c = this.canvas;
    let px = 0, py = 0;
    c.addEventListener("pointerdown", (e) => { this.drag = true; this.auto = false; px = e.clientX; py = e.clientY; c.setPointerCapture(e.pointerId); });
    c.addEventListener("pointermove", (e) => {
      if (!this.drag) return;
      const dx = e.clientX - px, dy = e.clientY - py; px = e.clientX; py = e.clientY;
      this.vyaw = dx * 0.006; this.vpitch = dy * 0.005;
      this.yaw += this.vyaw; this.pitch += this.vpitch;
    });
    const up = () => { this.drag = false; };
    c.addEventListener("pointerup", up);
    c.addEventListener("pointercancel", up);
    c.addEventListener("wheel", (e) => {
      e.preventDefault(); this.auto = false;
      this.zoom = Math.max(0.35, Math.min(2.6, this.zoom * Math.exp(e.deltaY * 0.0012)));
    }, { passive: false });
    c.addEventListener("dblclick", () => this.reset());
  };

  Viewer.prototype.reset = function () {
    this.yaw = 0.62; this.pitch = 0.36; this.zoom = 1; this.vyaw = this.vpitch = 0; this.auto = true;
  };

  Viewer.prototype._resize = function () {
    const r = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.max(1, Math.round(this.canvas.clientWidth * r)), h = Math.max(1, Math.round(this.canvas.clientHeight * r));
    if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; }
  };

  Viewer.prototype.setScene = function (sc, waterCm) {
    const gl = this.gl;
    if (!gl) return;
    const opaque = [], trans = [];
    for (const p of sc.prims) {
      const shape = p[0], c = [p[1], p[2], p[3]], X = [p[4], p[5], p[6]], Y = [p[7], p[8], p[9]], Z = [p[10], p[11], p[12]];
      const s = [p[13], p[14], p[15]], col = [p[16] / 255, p[17] / 255, p[18] / 255, p[19] / 255], mat = p[20];
      const out = col[3] < 0.99 ? trans : opaque;
      const t = T[shape] || T[0];
      for (let i = 0; i < t.length; i += 6) {
        const lx = t[i] * s[0], ly = t[i + 1] * s[1], lz = t[i + 2] * s[2];
        const gx = c[0] + X[0] * lx + Y[0] * ly + Z[0] * lz;
        const gy = c[1] + X[1] * lx + Y[1] * ly + Z[1] * lz;
        const gz = c[2] + X[2] * lx + Y[2] * ly + Z[2] * lz;
        const nx = t[i + 3] / (s[0] || 1), ny = t[i + 4] / (s[1] || 1), nz = t[i + 5] / (s[2] || 1);
        let wx = X[0] * nx + Y[0] * ny + Z[0] * nz, wy = X[1] * nx + Y[1] * ny + Z[1] * nz, wz = X[2] * nx + Y[2] * ny + Z[2] * nz;
        const l = Math.hypot(wx, wy, wz) || 1;
        out.push(gx / 100, gz / 100, gy / 100, wx / l, wz / l, wy / l, col[0], col[1], col[2], col[3], mat);
      }
    }
    const lo = sc.lo, hi = sc.hi;
    const cx = (lo[0] + hi[0]) / 200, cy = (lo[1] + hi[1]) / 200, cz = (lo[2] + hi[2]) / 200;
    const ext = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 100;
    this.target = [cx, cz * 0.75, cy];
    this.radius = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], 0.6 * (hi[2] - lo[2])) / 200;
    this.corners = [];
    for (const x of [lo[0], hi[0]]) for (const y of [lo[1], hi[1]]) for (const z of [Math.max(lo[2], (waterCm || 0) - 20), hi[2]])
      this.corners.push([x / 100, z / 100, y / 100]);
    this.base = null;
    // water plane (two triangles) at the waterline
    const water = [];
    this.water = waterCm != null ? waterCm / 100 : -1e3;
    if (waterCm != null) {
      const W = ext * 2.2, y = waterCm / 100;
      this.wc = [cx, cy, W];
      const corners = [[cx - W, cy - W], [cx + W, cy - W], [cx + W, cy + W], [cx - W, cy + W]];
      for (const k of [0, 1, 2, 0, 2, 3]) water.push(corners[k][0], y, corners[k][1], 0, 1, 0, 0.1, 0.3, 0.45, 0.6, 5);
    }
    const all = new Float32Array(opaque.concat(trans, water));
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    gl.bufferData(gl.ARRAY_BUFFER, all, gl.STATIC_DRAW);
    this.counts = [opaque.length / 11, trans.length / 11, water.length / 11];
  };

  Viewer.prototype.draw = function (opts) {
    const gl = this.gl;
    if (!gl) return;
    opts = opts || {};
    const w = this.canvas.width, h = this.canvas.height;
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    if (!this.counts) return;
    const zoom = opts.zoom || this.zoomS || 1;
    const fov = 0.62;
    if (!this.base && !opts.base) this.base = this.fit(this.yaw0, this.pitch0, w / h, 1.22);
    const dist = (opts.base || this.base) * zoom;
    const yaw = opts.yaw != null ? opts.yaw : this.yaw, pitch = opts.pitch != null ? opts.pitch : this.pitch;
    const t = this.target;
    const eye = [t[0] + dist * Math.cos(pitch) * Math.cos(yaw), t[1] + dist * Math.sin(pitch), t[2] + dist * Math.cos(pitch) * Math.sin(yaw)];
    const vp = mmul(persp(fov, w / h, dist / 40, dist * 20), lookAt(eye, t, [0, 1, 0]));
    gl.useProgram(this.prog);
    gl.uniformMatrix4fv(this.loc.vp, false, new Float32Array(vp));
    gl.uniform3fv(this.loc.eye, new Float32Array(eye));
    gl.uniform1f(this.loc.water, opts.noWater ? -1e3 : this.water);
    gl.uniform3fv(this.loc.wc, new Float32Array(this.wc || [0, 0, 1]));
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    const S = 44, L = this.loc;
    gl.enableVertexAttribArray(L.pos); gl.vertexAttribPointer(L.pos, 3, gl.FLOAT, false, S, 0);
    gl.enableVertexAttribArray(L.nrm); gl.vertexAttribPointer(L.nrm, 3, gl.FLOAT, false, S, 12);
    gl.enableVertexAttribArray(L.col); gl.vertexAttribPointer(L.col, 4, gl.FLOAT, false, S, 24);
    gl.enableVertexAttribArray(L.mat); gl.vertexAttribPointer(L.mat, 1, gl.FLOAT, false, S, 40);
    gl.enable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    gl.disable(gl.BLEND);
    gl.depthMask(true);
    const [no, nt, nw] = this.counts;
    gl.drawArrays(gl.TRIANGLES, 0, no);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);
    if (nt) gl.drawArrays(gl.TRIANGLES, no, nt);
    if (nw && !opts.noWater && this.showWater) gl.drawArrays(gl.TRIANGLES, no + nt, nw);
    gl.depthMask(true);
  };

  // camera distance at which the bounding box fills `margin` of the view
  Viewer.prototype.fit = function (yaw, pitch, aspect, margin) {
    const fov = 0.62, t = this.target, tf = Math.tan(fov / 2);
    const ok = (dist) => {
      const eye = [t[0] + dist * Math.cos(pitch) * Math.cos(yaw), t[1] + dist * Math.sin(pitch), t[2] + dist * Math.cos(pitch) * Math.sin(yaw)];
      const V = lookAt(eye, t, [0, 1, 0]);
      for (const c of this.corners) {
        const x = V[0] * c[0] + V[4] * c[1] + V[8] * c[2] + V[12];
        const y = V[1] * c[0] + V[5] * c[1] + V[9] * c[2] + V[13];
        const z = -(V[2] * c[0] + V[6] * c[1] + V[10] * c[2] + V[14]);
        if (z <= 0.01) return false;
        if (Math.abs(x / (z * tf * aspect)) > margin || Math.abs(y / (z * tf)) > margin) return false;
      }
      return true;
    };
    let lo = this.radius * 0.3, hi = this.radius * 12;
    for (let i = 0; i < 30; i++) { const m = (lo + hi) / 2; if (ok(m)) hi = m; else lo = m; }
    return hi;
  };

  // 256x256 transparent snapshot for Preview.png (the game's thumbnail)
  Viewer.prototype.capture = function (size) {
    size = size || 256;
    const c = this.canvas, w = c.width, h = c.height;
    c.width = size; c.height = size;
    this.draw({ yaw: 0.72, pitch: 0.42, zoom: 1, noWater: true, base: this.fit(0.72, 0.42, 1, 1.22) });
    const url = c.toDataURL("image/png");
    c.width = w; c.height = h;
    this.draw();
    return url;
  };

  window.BoatViewer = Viewer;
})();
