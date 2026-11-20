/* Cards that open and close from their heading (UI style guide: collapsible card).
 *
 * Markup, rendered open or closed by the server so nothing moves on load:
 *   <section data-a3s-collapse class="... [is-collapsed]">
 *     <h3 ...><button type="button" class="a3s-edit__toggle" aria-expanded="true|false" aria-controls="ID">
 *       <span class="a3s-edit__toggle-label">Title</span><svg class="a3s-edit__chevron">...</svg></button></h3>
 *     <div class="a3s-edit__body" id="ID" [hidden]>...</div>
 *   </section>
 *
 * Each card opens and closes on its own. window.a3sReveal(el) opens the card holding `el`, for
 * a form that is about to focus a field the person still has to fill in.
 */
(function () {
	"use strict";

	function setOpen(card, open) {
		var toggle = card.querySelector(".a3s-edit__toggle");
		var body = card.querySelector(".a3s-edit__body");
		if (!toggle || !body) return;
		card.classList.toggle("is-collapsed", !open);
		body.hidden = !open;
		toggle.setAttribute("aria-expanded", open ? "true" : "false");
	}

	document.addEventListener("click", function (event) {
		var toggle = event.target.closest("[data-a3s-collapse] .a3s-edit__toggle");
		if (!toggle) return;
		var card = toggle.closest("[data-a3s-collapse]");
		setOpen(card, card.classList.contains("is-collapsed"));
	});

	window.a3sReveal = function (el) {
		var card = el && el.closest && el.closest("[data-a3s-collapse].is-collapsed");
		if (card) setOpen(card, true);
	};
})();
