/* Igor Santiago Imoveis - menu do celular e filtros do catalogo.
   Sem dependencia. Se o JS nao rodar, a pagina continua legivel e o
   catalogo aparece inteiro. */
(function () {
  "use strict";

  // Barra de demonstração quebra em várias linhas no celular.
  var barra = document.querySelector(".barra-demo");
  var topo = document.querySelector(".topo");
  function medirTopo() {
    var alturaBarra = barra ? barra.getBoundingClientRect().height : 0;
    var alturaTopo = topo ? topo.getBoundingClientRect().height : 0;
    document.documentElement.style.setProperty("--altura-demo", alturaBarra + "px");
    document.documentElement.style.setProperty("--ancora-topo", Math.max(96, alturaBarra + alturaTopo + 16) + "px");
  }
  medirTopo();
  window.addEventListener("resize", medirTopo);
  if ("ResizeObserver" in window) {
    var medidor = new ResizeObserver(medirTopo);
    if (barra) medidor.observe(barra);
    if (topo) medidor.observe(topo);
  }
  if (document.fonts) document.fonts.ready.then(medirTopo);

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
    var finalidade = valor("finalidade");
    var faixaCampo = form.elements.faixa;
    if (faixaCampo) {
      faixaCampo.disabled = operacao !== "locacao";
      var avisoFaixa = form.querySelector(".faixa-aviso");
      if (avisoFaixa) avisoFaixa.hidden = !faixaCampo.disabled;
      if (faixaCampo.disabled) faixaCampo.value = "";
    }
    var faixa = valor("faixa").split("-");
    var minimo = parseInt(faixa[0], 10) || 0;
    var maximo = parseInt(faixa[1], 10) || Infinity;
    var ordem = valor("ordem");
    var visiveis = 0;

    cards.forEach(function (card) {
      var ok =
        (!operacao || card.dataset.operacao === operacao) &&
        (!finalidade || card.dataset.finalidade === finalidade) &&
        (!valor("faixa") || (parseInt(card.dataset.preco, 10) > minimo && parseInt(card.dataset.preco, 10) <= maximo)) &&
        (!tipo || card.dataset.tipo === tipo) &&
        (!bairro || card.dataset.bairro === bairro) &&
        (!quartos || parseInt(card.dataset.quartos, 10) >= quartos);
      card.hidden = !ok;
      if (ok) visiveis++;
    });

    var ordenados = ordemOriginal.slice();
    if (ordem === "menor" || ordem === "maior") {
      ordenados.sort(function (a, b) {
        if (a.dataset.operacao !== b.dataset.operacao) {
          return a.dataset.operacao === "locacao" ? -1 : 1;
        }
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
    ["tipo", "bairro", "quartos", "finalidade", "faixa"].forEach(function (nome) {
      if (form.elements[nome]) form.elements[nome].value = "";
    });
    if (form.elements.operacao) form.elements.operacao.value = "locacao";
    if (form.elements.ordem) form.elements.ordem.value = "destaque";
    aplicar();
  }

  var cartoesBairro = document.querySelectorAll("[data-bairro-card]");
  Array.prototype.forEach.call(cartoesBairro, function (elCard) {
    elCard.addEventListener("click", function (evento) {
      evento.preventDefault();
      if (form.elements.bairro) form.elements.bairro.value = elCard.dataset.bairroCard;
      aplicar();
      lista.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    });
  });

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

// Pontos decorativos seguem a etapa no centro da leitura.
(function () {
  "use strict";
  var pontos = document.querySelectorAll(".percurso-pontos span");
  if (!pontos.length) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    pontos.forEach(function (p) { p.classList.add("ativo"); });
    return;
  }
  if (!("IntersectionObserver" in window)) return;
  var observador = new IntersectionObserver(function (entradas) {
    entradas.forEach(function (entrada) {
      if (!entrada.isIntersecting) return;
      var indice = Number(entrada.target.dataset.passo) - 1;
      pontos.forEach(function (p, n) { p.classList.toggle("ativo", n === indice); });
    });
  }, { rootMargin: "-45% 0px -45% 0px", threshold: 0 });
  document.querySelectorAll("[data-passo]").forEach(function (p) { observador.observe(p); });
})();

// Sentinela em y=24: nenhum listener contínuo de scroll.
(function () {
  "use strict";
  if (!document.body.classList.contains("pagina-home")) return;
  var sentinela = document.querySelector(".topo-sentinela");
  var topo = document.querySelector(".topo");
  if (!sentinela || !topo || !("IntersectionObserver" in window)) return;
  new IntersectionObserver(function (entradas) {
    topo.classList.toggle("topo--fixado", !entradas[0].isIntersecting);
  }).observe(sentinela);
})();

// --- carrossel de fotos (ficha de imovel) ---------------------------------
(function () {
  "use strict";
  var carrosseis = document.querySelectorAll("[data-carrossel]");

  Array.prototype.forEach.call(carrosseis, function (raiz) {
    var trilho = raiz.querySelector(".carrossel-trilho");
    var slides = raiz.querySelectorAll(".carrossel-slide");
    var pontos = raiz.querySelectorAll(".carrossel-ponto");
    var atual = 0;

    function irPara(indice) {
      atual = (indice + slides.length) % slides.length;
      trilho.style.transform = "translateX(-" + (atual * 100) + "%)";
      Array.prototype.forEach.call(pontos, function (ponto, n) {
        ponto.classList.toggle("ativo", n === atual);
      });
    }

    var anterior = raiz.querySelector("[data-anterior]");
    var proxima = raiz.querySelector("[data-proxima]");
    if (anterior) anterior.addEventListener("click", function () { irPara(atual - 1); });
    if (proxima) proxima.addEventListener("click", function () { irPara(atual + 1); });
    Array.prototype.forEach.call(pontos, function (ponto, n) {
      ponto.addEventListener("click", function () { irPara(n); });
    });
  });
})();
