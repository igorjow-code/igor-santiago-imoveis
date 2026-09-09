/* Igor Santiago Imoveis - menu do celular e filtros do catalogo.
   Sem dependencia. Se o JS nao rodar, a pagina continua legivel e o
   catalogo aparece inteiro. */
(function () {
  "use strict";

  // --- menu do celular ---------------------------------------------------
  var botao = document.querySelector(".menu-btn");
  var nav = document.querySelector(".nav");
  if (botao && nav) {
    botao.addEventListener("click", function () {
      var aberto = nav.classList.toggle("aberto");
      botao.setAttribute("aria-expanded", aberto ? "true" : "false");
    });
  }

  // --- filtros do catalogo -----------------------------------------------
  var form = document.getElementById("filtros");
  var lista = document.getElementById("lista");
  if (!form || !lista) return;

  var cards = Array.prototype.slice.call(lista.querySelectorAll(".card"));
  var contagem = document.getElementById("contagem");
  var vazio = document.getElementById("vazio");
  var ordemOriginal = cards.slice();

  function valor(nome) {
    var campo = form.elements[nome];
    return campo ? campo.value : "";
  }

  function aplicar() {
    var operacao = valor("operacao");
    var tipo = valor("tipo");
    var bairro = valor("bairro");
    var quartos = parseInt(valor("quartos"), 10) || 0;
    var ordem = valor("ordem");
    var visiveis = 0;

    cards.forEach(function (card) {
      var ok =
        (!operacao || card.dataset.operacao === operacao) &&
        (!tipo || card.dataset.tipo === tipo) &&
        (!bairro || card.dataset.bairro === bairro) &&
        (!quartos || parseInt(card.dataset.quartos, 10) >= quartos);
      card.hidden = !ok;
      if (ok) visiveis++;
    });

    var ordenados = ordemOriginal.slice();
    if (ordem === "menor" || ordem === "maior") {
      ordenados.sort(function (a, b) {
        var pa = parseInt(a.dataset.preco, 10);
        var pb = parseInt(b.dataset.preco, 10);
        return ordem === "menor" ? pa - pb : pb - pa;
      });
    }
    ordenados.forEach(function (card) { lista.appendChild(card); });

    if (contagem) {
      contagem.textContent =
        visiveis === 0 ? "" :
        visiveis === 1 ? "1 imóvel" : visiveis + " imóveis";
    }
    if (vazio) vazio.hidden = visiveis !== 0;
  }

  function limpar() {
    ["operacao", "tipo", "bairro", "quartos"].forEach(function (nome) {
      if (form.elements[nome]) form.elements[nome].value = "";
    });
    if (form.elements.ordem) form.elements.ordem.value = "destaque";
    aplicar();
  }

  form.addEventListener("change", aplicar);
  var limpar1 = document.getElementById("limpar");
  var limpar2 = document.getElementById("limpar2");
  if (limpar1) limpar1.addEventListener("click", limpar);
  if (limpar2) limpar2.addEventListener("click", limpar);

  aplicar();
})();

// --- revelação escalonada -------------------------------------------------
// A classe "js" só existe no <html> quando JS rodou e o visitante não pediu
// "reduzir movimento" (script inline no <head>). Sem ela, tudo já está visível.
(function () {
  "use strict";
  if (!document.documentElement.classList.contains("js")) return;
  if (!("IntersectionObserver" in window)) return;

  var alvos = document.querySelectorAll("[data-reveal]");
  var observador = new IntersectionObserver(function (entradas) {
    entradas.forEach(function (entrada) {
      if (!entrada.isIntersecting) return;
      entrada.target.classList.add("in-view");
      observador.unobserve(entrada.target);
    });
  }, { threshold: .15, rootMargin: "0px 0px -40px 0px" });

  Array.prototype.forEach.call(alvos, function (el) { observador.observe(el); });
})();
