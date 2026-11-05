/*
 * SupportDesk website widget loader. Paste on any page:
 *
 *   <script src="https://support.example.com/widget.js" data-key="pk_..." async></script>
 *
 * It adds a launcher button and an iframe served by the SupportDesk web app (the origin
 * this script came from). The chat itself runs inside the iframe, so the host page never
 * sees visitor tokens or messages; the two only exchange open, close and appearance
 * events through postMessage, checked against the iframe's origin.
 *
 * Optional attributes: data-position="left|right", data-color="#4f46e5" (the inbox's
 * settings win once loaded), data-api (kept for API clients; the frame uses its own origin).
 *
 * Signed-in customers (identity verification): add data-external-id, data-signature (the
 * HMAC-SHA256 of the external id with the inbox's identity secret, computed by your
 * backend), and optionally data-email and data-name. Or call, before or after this script
 * loads:
 *
 *   window.SupportDesk = window.SupportDesk || { _q: [], identify: function (i) { this._q.push(i); } };
 *   SupportDesk.identify({ externalId: "42", signature: "<hmac>", email: "a@b.example", name: "Ana" });
 *
 * data-user-id / data-user-hash and { userId, userHash } are accepted as aliases.
 */
(function () {
  "use strict";
  if (window.__supportdeskWidget) return;
  window.__supportdeskWidget = true;

  var script =
    document.currentScript ||
    (function () {
      var all = document.querySelectorAll("script[data-key]");
      for (var i = all.length - 1; i >= 0; i--) {
        if (/\/widget\.js(\?|$)/.test(all[i].src)) return all[i];
      }
      return null;
    })();
  if (!script) return;

  var key = script.getAttribute("data-key") || "";
  if (!key) {
    if (window.console) console.warn("SupportDesk widget: add data-key=\"pk_...\" to the script tag.");
    return;
  }
  var appOrigin = new URL(script.src, location.href).origin;
  var state = {
    open: false,
    position: script.getAttribute("data-position") === "left" ? "left" : "right",
    color: /^#[0-9a-f]{6}$/i.test(script.getAttribute("data-color") || "") ? script.getAttribute("data-color") : "#4f46e5",
    label: "Help",
  };

  var pre = window.SupportDesk;
  var frameReady = false;
  var identity = null;
  function pick(attr) {
    var v = script.getAttribute(attr);
    return v && v.trim() ? v.trim() : null;
  }
  var attrId = pick("data-external-id") || pick("data-user-id");
  if (attrId) {
    identity = { userId: attrId, userHash: pick("data-signature") || pick("data-user-hash"), email: pick("data-email"), name: pick("data-name") };
  }

  var Z = 2147483000;
  var root = document.createElement("div");
  root.id = "supportdesk-widget";
  root.style.cssText = "position:fixed;bottom:0;z-index:" + Z + ";";

  var frameWrap = document.createElement("div");
  frameWrap.style.cssText =
    "position:fixed;bottom:88px;width:380px;height:600px;max-height:calc(100vh - 112px);max-width:calc(100vw - 32px);" +
    "border-radius:18px;overflow:hidden;box-shadow:0 12px 48px rgba(15,23,42,.22),0 2px 8px rgba(15,23,42,.12);" +
    "opacity:0;transform:translateY(12px) scale(.98);pointer-events:none;transition:opacity .18s ease,transform .18s ease;" +
    "background:transparent;z-index:" + Z + ";";

  var iframe = document.createElement("iframe");
  iframe.title = "Support chat";
  iframe.src = appOrigin + "/widget/frame?key=" + encodeURIComponent(key) + "&origin=" + encodeURIComponent(location.origin);
  iframe.style.cssText = "width:100%;height:100%;border:0;display:block;color-scheme:normal;";
  iframe.setAttribute("allow", "clipboard-write");
  iframe.setAttribute("loading", "eager");
  frameWrap.appendChild(iframe);

  var button = document.createElement("button");
  button.type = "button";
  button.setAttribute("aria-label", "Open support chat");
  button.setAttribute("aria-expanded", "false");
  button.style.cssText =
    "position:fixed;bottom:20px;height:56px;min-width:56px;padding:0 18px 0 16px;border:0;border-radius:28px;cursor:pointer;" +
    "display:flex;align-items:center;gap:8px;font:600 14px/1 system-ui,-apple-system,'Segoe UI',sans-serif;" +
    "box-shadow:0 8px 24px rgba(15,23,42,.24);transition:transform .15s ease,box-shadow .15s ease;z-index:" + Z + ";";
  var chatIcon =
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>';
  var closeIcon =
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';

  function textOn(hex) {
    var n = parseInt(hex.slice(1), 16);
    var r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    var lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    return lum > 0.6 ? "#0b0b1a" : "#ffffff";
  }

  function render() {
    var side = state.position === "left" ? "left" : "right";
    var other = side === "left" ? "right" : "left";
    var mobile = window.innerWidth < 480;
    button.style[side] = "20px";
    button.style[other] = "auto";
    button.style.background = state.color;
    button.style.color = textOn(state.color);
    button.innerHTML = state.open ? closeIcon : chatIcon + '<span style="white-space:nowrap">' + escapeHtml(state.label) + "</span>";
    button.style.padding = state.open ? "0" : "0 18px 0 16px";
    button.style.width = state.open ? "56px" : "auto";
    button.style.justifyContent = "center";
    button.setAttribute("aria-label", state.open ? "Close support chat" : "Open support chat");
    button.setAttribute("aria-expanded", state.open ? "true" : "false");
    if (mobile) {
      frameWrap.style.left = "0";
      frameWrap.style.right = "0";
      frameWrap.style.bottom = "0";
      frameWrap.style.top = "0";
      frameWrap.style.width = "100vw";
      frameWrap.style.height = "100%";
      frameWrap.style.maxHeight = "100%";
      frameWrap.style.maxWidth = "100vw";
      frameWrap.style.borderRadius = "0";
      button.style.display = state.open ? "none" : "flex";
    } else {
      frameWrap.style[side] = "20px";
      frameWrap.style[other] = "auto";
      frameWrap.style.top = "auto";
      frameWrap.style.bottom = "88px";
      frameWrap.style.width = "380px";
      frameWrap.style.height = "600px";
      frameWrap.style.maxHeight = "calc(100vh - 112px)";
      frameWrap.style.maxWidth = "calc(100vw - 32px)";
      frameWrap.style.borderRadius = "18px";
      button.style.display = "flex";
    }
    frameWrap.style.opacity = state.open ? "1" : "0";
    frameWrap.style.transform = state.open ? "none" : "translateY(12px) scale(.98)";
    frameWrap.style.pointerEvents = state.open ? "auto" : "none";
    frameWrap.setAttribute("aria-hidden", state.open ? "false" : "true");
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function sendIdentity() {
    if (frameReady && iframe.contentWindow) iframe.contentWindow.postMessage({ source: "supportdesk-loader", type: "identity", identity: identity }, appOrigin);
  }

  function identify(i) {
    var id = i && typeof i === "object" ? i.externalId || i.userId : null;
    var sig = i && typeof i === "object" ? i.signature || i.userHash : null;
    if (!id) {
      identity = null;
    } else {
      identity = {
        userId: String(id),
        userHash: sig ? String(sig) : null,
        email: i.email ? String(i.email) : null,
        name: i.name ? String(i.name) : null,
      };
    }
    sendIdentity();
  }

  function setOpen(open) {
    state.open = open;
    render();
    if (open && iframe.contentWindow) iframe.contentWindow.postMessage({ source: "supportdesk-loader", type: "open" }, appOrigin);
    if (!open) button.focus();
  }

  button.addEventListener("click", function () {
    setOpen(!state.open);
  });
  button.addEventListener("mouseenter", function () {
    button.style.transform = "translateY(-1px)";
  });
  button.addEventListener("mouseleave", function () {
    button.style.transform = "none";
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && state.open) setOpen(false);
  });
  window.addEventListener("resize", render);

  window.addEventListener("message", function (e) {
    if (e.origin !== appOrigin || e.source !== iframe.contentWindow) return;
    var d = e.data || {};
    if (d.source !== "supportdesk") return;
    if (d.type === "close") setOpen(false);
    if (d.type === "ready") {
      frameReady = true;
      sendIdentity();
    }
    if (d.type === "config") {
      if (typeof d.color === "string" && /^#[0-9a-f]{6}$/i.test(d.color)) state.color = d.color;
      if (d.position === "left" || d.position === "right") state.position = d.position;
      if (typeof d.label === "string" && d.label.trim()) state.label = d.label.trim().slice(0, 40);
      render();
    }
  });

  window.SupportDesk = {
    open: function () {
      setOpen(true);
    },
    close: function () {
      setOpen(false);
    },
    toggle: function () {
      setOpen(!state.open);
    },
    identify: identify,
    logout: function () {
      identify(null);
    },
  };
  if (pre && Array.isArray(pre._q)) {
    for (var q = 0; q < pre._q.length; q++) identify(pre._q[q]);
  }

  render();
  root.appendChild(frameWrap);
  root.appendChild(button);
  function mount() {
    document.body.appendChild(root);
  }
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);
})();
