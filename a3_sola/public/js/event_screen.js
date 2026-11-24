/* The stall screen (www/event_screen): asks the feed every 2 seconds (a3_sola.api.event_screen)
   and plays each moment in turn - a welcome when someone registers, a paper plane to WhatsApp
   when their brochure goes out - then returns to the QR, the counters and the ticker. */
(function () {
	"use strict";

	var tv = document.querySelector("[data-tv]");
	if (!tv) return;
	var key = tv.dataset.key;
	var POLL_MS = 2000;
	var MAX_BACKOFF_MS = 15000;
	var idle = tv.querySelector("[data-idle]");
	var momentEl = tv.querySelector("[data-moment]");
	var card = tv.querySelector("[data-card]");
	var confettiCanvas = tv.querySelector("[data-confetti]");
	var offline = tv.querySelector("[data-offline]");
	var ticker = tv.querySelector("[data-ticker]");
	var queue = [];
	var playing = false;
	var after = null;
	/* The moments already queued, by key: each poll looks back over the last few minutes (a slow
	   registration is saved after the screen has polled past it), so the same one comes again. */
	var seen = {}, seenOrder = [];
	function fresh(item) {
		var k = item.key || (item.kind + "|" + item.id + "|" + item.at);
		if (seen[k]) return false;
		seen[k] = true;
		seenOrder.push(k);
		if (seenOrder.length > 2000) delete seen[seenOrder.shift()];
		return true;
	}
	var failures = 0;
	var chime = false;
	var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
	var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
	var counters = {};
	/* A counter's rupees: in full up to a lakh, then "₹1.2 L" - it stays one short line on the card. */
	function rupees(v) {
		return v >= 100000 ? "\u20b9" + (v / 100000).toFixed(v >= 1000000 ? 0 : 1) + " L" : money.format(v);
	}

	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}
	function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

	/* ------------------------------------------------------------------ clock */
	var clock = tv.querySelector("[data-clock]");
	function tick() { clock.textContent = new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }); }
	tick();
	setInterval(tick, 15000);

	/* ------------------------------------------------------------------ start: full screen, awake, sound */
	var wakeLock = null;
	function keepAwake() {
		if (navigator.wakeLock && document.visibilityState === "visible") {
			navigator.wakeLock.request("screen").then(function (l) { wakeLock = l; }).catch(function () {});
		}
	}
	document.addEventListener("visibilitychange", function () { if (!wakeLock || wakeLock.released) keepAwake(); });
	var audio = null;
	tv.querySelector("[data-start-btn]").addEventListener("click", function () {
		chime = tv.querySelector("[data-chime]").checked;
		if (chime && (window.AudioContext || window.webkitAudioContext)) audio = new (window.AudioContext || window.webkitAudioContext)();
		var el = document.documentElement;
		if (el.requestFullscreen) el.requestFullscreen().catch(function () {});
		keepAwake();
		tv.querySelector("[data-start]").hidden = true;
		document.body.classList.add("is-started");
	});
	/* Two notes rising: a welcome. */
	function ding() {
		if (!chime || !audio) return;
		[[659.25, 0], [987.77, 0.14]].forEach(function (n) {
			var o = audio.createOscillator(), g = audio.createGain(), t = audio.currentTime + n[1];
			o.type = "sine"; o.frequency.value = n[0];
			g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
			o.connect(g); g.connect(audio.destination); o.start(t); o.stop(t + 0.65);
		});
	}

	/* ------------------------------------------------------------------ counters and ticker */
	/* A number that went up: the card pops, and "+1" floats off it. */
	function bump(el, by, isMoney) {
		var card = el.closest(".a3s-tv__stat");
		if (!card || reduced) return;
		card.classList.remove("is-bump");
		void card.offsetWidth;  // restart the animation
		card.classList.add("is-bump");
		var tag = document.createElement("span");
		tag.className = "a3s-tv__plus";
		tag.textContent = "+" + (isMoney ? money.format(by) : (by % 1 ? by.toFixed(1) : by));
		card.appendChild(tag);
		setTimeout(function () { tag.remove(); }, 1800);
	}
	function countTo(el, to, isMoney) {
		var known = Object.prototype.hasOwnProperty.call(counters, el.dataset.count);
		var from = counters[el.dataset.count] || 0;
		counters[el.dataset.count] = to;
		if (known && to > from) bump(el, Math.round((to - from) * 10) / 10, isMoney);
		if (from === to) { el.textContent = isMoney ? rupees(to) : String(to); return; }
		var start = null, dur = reduced ? 0 : 1200;
		function step(ts) {
			if (start === null) start = ts;
			var p = dur ? Math.min(1, (ts - start) / dur) : 1;
			var v = from + (to - from) * (1 - Math.pow(1 - p, 3));
			el.textContent = isMoney ? rupees(Math.round(v)) : (to % 1 ? v.toFixed(1) : String(Math.round(v)));
			if (p < 1) requestAnimationFrame(step);
		}
		requestAnimationFrame(step);
	}
	function setCounters(c) {
		tv.querySelectorAll("[data-count]").forEach(function (el) {
			var v = Number(c[el.dataset.count] || 0);
			countTo(el, v, el.hasAttribute("data-money"));
		});
	}
	var tickerKey = "";
	function setTicker(names) {
		names = (names || []).filter(Boolean);
		var k = names.join("|");
		if (k === tickerKey) return;
		tickerKey = k;
		if (!names.length) { ticker.innerHTML = '<span class="a3s-tv__ticker-item">Be the first to register today</span>'; return; }
		var items = names.map(function (n) { return '<span class="a3s-tv__ticker-item">' + esc(n) + "</span>"; }).join("");
		ticker.innerHTML = items + items;  // twice, so the loop is seamless
		ticker.style.animationDuration = Math.max(20, names.length * 5) + "s";
	}

	/* ------------------------------------------------------------------ the headlines, in turn */
	var slides = [].slice.call(tv.querySelectorAll("[data-slides] .a3s-tv__slide"));
	var dots = tv.querySelector("[data-dots]");
	var slideAt = 0;
	dots.innerHTML = slides.length > 1 ? slides.map(function (_, i) { return "<i" + (i ? "" : ' class="is-on"') + "></i>"; }).join("") : "";
	function nextSlide() {
		if (slides.length < 2 || playing) return;  // a welcome on screen: the headline waits
		slides[slideAt].classList.remove("is-on");
		slides[slideAt].classList.add("is-off");
		var was = slides[slideAt];
		setTimeout(function () { was.classList.remove("is-off"); }, 900);
		slideAt = (slideAt + 1) % slides.length;
		slides[slideAt].classList.add("is-on");
		[].forEach.call(dots.children, function (d, i) { d.classList.toggle("is-on", i === slideAt); });
	}
	setInterval(nextSlide, 7000);

	/* ------------------------------------------------------------------ sparkles rising from the sun */
	(function sparkles() {
		var canvas = tv.querySelector("[data-sparkles]");
		if (!canvas || reduced) return;
		var ctx = canvas.getContext("2d");
		var w, h, dots2 = [];
		function size() { w = canvas.width = canvas.offsetWidth; h = canvas.height = canvas.offsetHeight; }
		size();
		window.addEventListener("resize", size);
		function spawn(anywhere) {
			return { x: Math.random() * w, y: anywhere ? Math.random() * h : h + 10, r: Math.random() * 2.2 + 0.6,
				vy: Math.random() * 0.45 + 0.15, vx: (Math.random() - 0.5) * 0.2, a: Math.random() * 0.6 + 0.2,
				tw: Math.random() * Math.PI * 2, warm: Math.random() < 0.75 };
		}
		for (var i = 0; i < 70; i++) dots2.push(spawn(true));
		(function frame() {
			ctx.clearRect(0, 0, w, h);
			dots2.forEach(function (d, i) {
				d.y -= d.vy; d.x += d.vx; d.tw += 0.04;
				if (d.y < -10) dots2[i] = spawn(false);
				var alpha = d.a * (0.6 + 0.4 * Math.sin(d.tw));
				ctx.beginPath();
				ctx.fillStyle = d.warm ? "rgba(251, 176, 64, " + alpha + ")" : "rgba(91, 194, 236, " + alpha + ")";
				ctx.shadowColor = d.warm ? "#fbb040" : "#5bc2ec";
				ctx.shadowBlur = 8;
				ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
				ctx.fill();
			});
			requestAnimationFrame(frame);
		})();
	})();

	/* ------------------------------------------------------------------ the moments */
	function typeIn(el, text, ms) {
		if (reduced) { el.textContent = text; return Promise.resolve(); }
		el.textContent = "";
		el.classList.add("is-typing");
		var i = 0;
		return new Promise(function (resolve) {
			var t = setInterval(function () {
				i += 1;
				el.textContent = text.slice(0, i);
				if (i >= text.length) { clearInterval(t); el.classList.remove("is-typing"); resolve(); }
			}, ms);
		});
	}
	function confetti(ms) {
		if (reduced) return;
		var ctx = confettiCanvas.getContext("2d");
		var w = confettiCanvas.width = confettiCanvas.offsetWidth;
		var h = confettiCanvas.height = confettiCanvas.offsetHeight;
		var colors = ["#f7941e", "#fbb040", "#29abe2", "#28c840", "#ffffff"];
		var bits = [];
		for (var i = 0; i < 160; i++) {
			bits.push({ x: w / 2 + (Math.random() - 0.5) * w * 0.3, y: h * 0.45, vx: (Math.random() - 0.5) * 16, vy: -Math.random() * 16 - 4,
				r: Math.random() * 6 + 4, c: colors[i % colors.length], a: Math.random() * Math.PI, va: (Math.random() - 0.5) * 0.3 });
		}
		var end = performance.now() + ms;
		(function frame(now) {
			ctx.clearRect(0, 0, w, h);
			bits.forEach(function (b) {
				b.vy += 0.35; b.vx *= 0.99; b.x += b.vx; b.y += b.vy; b.a += b.va;
				ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.a); ctx.fillStyle = b.c;
				ctx.fillRect(-b.r / 2, -b.r / 4, b.r, b.r / 2); ctx.restore();
			});
			if (now < end) requestAnimationFrame(frame); else ctx.clearRect(0, 0, w, h);
		})(performance.now());
	}
	function show(kind) {
		momentEl.className = "a3s-tv__moment a3s-tv__moment--" + kind;
		momentEl.hidden = false;
		idle.classList.add("is-away");
		requestAnimationFrame(function () { momentEl.classList.add("is-on"); });
	}
	function hide() {
		momentEl.classList.remove("is-on");
		idle.classList.remove("is-away");
		return wait(500).then(function () { momentEl.hidden = true; card.innerHTML = ""; });
	}
	/* How long each moment stays: shorter while others wait. */
	function holdMs() { return queue.length > 3 ? 4000 : queue.length ? 6000 : 9000; }

	/* One figure of the estimate, counting up: `to` the number, `kind` money / years / kW. */
	function stat(to, label, kind, extra) {
		if (to === null || to === undefined || to === "" || (!Number(to) && kind !== "kw")) return "";
		return '<div class="a3s-tv__stat2' + (extra ? " " + extra : "") + '"><b data-to="' + Number(to) + '" data-kind="' + kind + '">' +
			(kind === "money" ? "\u20b90" : "0") + "</b><span>" + label + "</span></div>";
	}
	var ICON = {
		home: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11l9-7 9 7M5 10v10h14V10"/></svg>',
		phone: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18h2"/></svg>',
		bolt: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2L4 14h7l-1 8 9-12h-7z"/></svg>'
	};
	function playWelcome(item) {
		show("welcome");
		ding();
		var named = !item.hidden && item.name;
		var est = item.estimate;
		var facts = [];
		if (named && (item.interest || item.system_type)) {
			facts.push(ICON.home + esc([item.interest, item.system_type && item.system_type !== "Not sure" ? item.system_type : ""].filter(Boolean).join(" \u00b7 ")));
		}
		if (named && item.mobile) facts.push(ICON.phone + esc(item.mobile));
		/* Their bill as KSEB sends it - every two months - and what it means in units. */
		if (named && est && est.monthly_bill) {
			facts.push(ICON.bolt + "Bill " + esc(money.format(est.monthly_bill * 2)) + " / 2 months" +
				(est.monthly_units ? " \u00b7 " + esc(est.monthly_units) + " units a month" : ""));
		}
		var rows = "";
		if (est && est.kw) {
			var first = stat(est.kw, "kW system", "kw") + stat(est.price, "price", "money") +
				(est.subsidy ? stat(est.subsidy, "subsidy", "money") + stat(est.net, "you pay", "money", "is-key") : "");
			var second = est.battery ? "" : stat(est.monthly_saving, "saved a month", "money") +
				stat(est.monthly_saving * 12, "saved a year", "money") + stat(est.payback_years, "years to pay back", "years");
			rows = '<div class="a3s-tv__est2">' + '<div class="a3s-tv__est2-row">' + first + "</div>" +
				(second ? '<div class="a3s-tv__est2-row">' + second + "</div>" : "") +
				(est.battery ? '<p class="a3s-tv__est2-note">Our engineer will design your battery system</p>' : "") + "</div>";
		}
		card.innerHTML = '<p class="a3s-tv__hello">Welcome' + (named ? "," : "!") + "</p>" +
			'<p class="a3s-tv__name" data-name></p>' +
			'<p class="a3s-tv__place">' + (item.district ? (named ? "" : "A visitor from ") + esc(item.district) : "") + "</p>" +
			(facts.length ? '<div class="a3s-tv__facts">' + facts.map(function (f, i) {
				return '<span class="a3s-tv__fact" style="animation-delay:' + (1.1 + i * 0.2) + 's">' + f + "</span>";
			}).join("") + "</div>" : "") + rows;
		card.classList.toggle("has-est", !!rows);
		confetti(2600);
		var typed = named ? typeIn(card.querySelector("[data-name]"), item.name, 55) : Promise.resolve();
		return typed.then(function () {
			card.querySelectorAll("[data-to]").forEach(function (b, i) {
				setTimeout(function () {
					b.parentNode.classList.add("is-in");
					var to = Number(b.dataset.to), start = null;
					(function step(ts) {
						if (start === null) start = ts;
						var p = reduced ? 1 : Math.min(1, (ts - start) / 900);
						var v = to * (1 - Math.pow(1 - p, 3));
						var kind = b.dataset.kind || (b.hasAttribute("data-money") ? "money" : "kw");
						b.textContent = kind === "money" ? money.format(Math.round(v)) : (to % 1 ? v.toFixed(1) : String(Math.round(v)));
						if (p < 1) requestAnimationFrame(step);
					})(performance.now());
				}, 300 + i * 200);
			});
			return wait(holdMs());
		}).then(hide);
	}
	function playSent(item) {
		show("sent");
		var first = (item.name || "").split(" ")[0];
		var text = item.via === "Downloaded" ? (first ? "Brochure is on " + first + "'s phone" : "Brochure is on the visitor's phone")
			: "Brochure sent to WhatsApp";
		card.innerHTML = (item.name ? '<p class="a3s-tv__name a3s-tv__name--sm">' + esc(item.name) + "</p>" : "") +
			'<div class="a3s-tv__flight">' +
			'<svg class="a3s-tv__plane" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>' +
			'<span class="a3s-tv__path"></span>' +
			'<span class="a3s-tv__wa"><svg viewBox="0 0 52 52" aria-hidden="true"><path d="M15 27l7 7 15-16"/></svg></span>' +
			"</div>" +
			'<p class="a3s-tv__sent">' + esc(text) + "</p>";
		return wait(holdMs() - 1500).then(hide);
	}
	function play() {
		if (playing || !queue.length) return;
		playing = true;
		var item = queue.shift();
		(item.kind === "sent" ? playSent(item) : playWelcome(item))
			.catch(function () {})
			.then(function () { playing = false; return wait(400); })
			.then(play);
	}

	/* ------------------------------------------------------------------ the feed */
	function poll() {
		var url = "/api/method/a3_sola.api.event_screen.feed?key=" + encodeURIComponent(key) + (after ? "&after=" + encodeURIComponent(after) : "");
		fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" }, cache: "no-store" })
			.then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
			.then(function (body) {
				var d = body.message || {};
				failures = 0;
				offline.hidden = true;
				after = d.now || after;
				(d.items || []).filter(fresh).forEach(function (i) { queue.push(i); });
				setCounters(d.counters || {});
				setTicker(d.ticker);
				play();
				setTimeout(poll, POLL_MS);
			})
			.catch(function () {
				failures += 1;
				offline.hidden = failures < 2;
				setTimeout(poll, Math.min(MAX_BACKOFF_MS, POLL_MS * Math.pow(2, failures)));
			});
	}
	setTicker([]);
	poll();
})();
