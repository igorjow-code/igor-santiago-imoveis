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
    var capa = document.body.classList.contains("pagina-capa");
    var menu = function (aberto) {
      nav.classList.toggle("aberto", aberto);
      botao.setAttribute("aria-expanded", aberto ? "true" : "false");
      botao.setAttribute("aria-label", aberto ? "Fechar menu" : "Abrir menu");
      // Na capa o menu do celular cobre a tela: a página por baixo não rola.
      if (capa) document.documentElement.classList.toggle("menu-aberto", aberto);
    };
    botao.addEventListener("click", function () { menu(!nav.classList.contains("aberto")); });
    nav.addEventListener("click", function (evento) {
      if (evento.target.closest && evento.target.closest("a")) menu(false);
    });
    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape" && nav.classList.contains("aberto")) { menu(false); botao.focus(); }
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
      faixaCampo.disabled = false;
      var avisoFaixa = form.querySelector(".faixa-aviso");
      if (avisoFaixa) avisoFaixa.hidden = true;
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

// --- capa: os telhados da logo abrem e mostram a casa -------------------------
// Momento assinatura da direção "Marca forte". A rolagem engrossa os 5 riscos da
// máscara SVG até a foto ocupar a tela. Sem "js" no <html> (movimento reduzido ou
// navegador antigo) nada disto roda: o CSS já mostra a foto inteira, parada.
(function () {
  "use strict";
  var raiz = document.documentElement;
  var abre = document.querySelector(".abre");
  if (!abre) { raiz.classList.remove("na-abertura"); return; }

  // A barra de WhatsApp do celular só entra depois da abertura.
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entradas) {
      raiz.classList.toggle("na-abertura", entradas[0].isIntersecting);
    }, { rootMargin: "0px 0px -40% 0px" }).observe(abre);
  } else {
    raiz.classList.remove("na-abertura");
  }

  var palco = abre.querySelector(".palco");
  var svg = abre.querySelector(".abre-svg");
  var capa = abre.querySelector(".capa-texto");
  if (!palco || !svg || !capa) return;
  var semFoto = abre.classList.contains("abre--sem-foto");
  var vivo = raiz.classList.contains("js");
  if (!vivo && !semFoto) return;

  var riscos = Array.prototype.slice.call(svg.querySelectorAll(".risco"));
  var grupo = svg.querySelector("mask g");
  var imagem = svg.querySelector("image");
  var sombra = abre.querySelector(".abre-sombra");
  var destaque = abre.querySelector(".destaque");
  var fotoL = Number(abre.dataset.fotoL) || 0;
  var fotoA = Number(abre.dataset.fotoA) || 0;
  var foco = (abre.dataset.foco || "50% 50%").split(/\s+/).map(function (v) {
    var n = parseFloat(v);
    return (isNaN(n) ? 50 : n) / 100;
  });
  if (imagem) imagem.setAttribute("preserveAspectRatio", "none");
  var g = null, quadro = 0, pulso = false, inicioPulso = 0;

  function lim(v) { return Math.min(1, Math.max(0, v)); }
  function suave(t) { return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

  function medir() {
    var vw = palco.clientWidth, vh = semFoto ? window.innerHeight : palco.clientHeight;
    var largo = vw >= 900;
    var primeiro = capa.firstElementChild || capa;
    var topoTexto = primeiro.getBoundingClientRect().top - palco.getBoundingClientRect().top;
    var respiro = largo ? 104 : 90;
    var altura = Math.max(150, topoTexto - respiro - (largo ? 28 : 20));  // os telhados moram entre o topo e o título
    var bw = Math.min(vw * (largo ? .44 : .84), altura / .86), bh = bw * .86;
    var x0 = (vw - bw) / 2, y0 = respiro + (altura - bh) / 2;
    riscos.forEach(function (r, k) {                                      // 5 telhados empilhados: o desenho da logo
      var dy = k * .145 * bh;
      r.setAttribute("points", [[.02, .40], [.74, .05], [.98, .17]].map(function (p) {
        return (x0 + p[0] * bw).toFixed(1) + "," + (y0 + p[1] * bh + dy).toFixed(1);
      }).join(" "));
    });
    g = { vw: vw, vh: vh, base: bw * .052, fim: Math.hypot(vw, vh) * 2.2,
          cx: vw / 2, cy: y0 + bh * .49, cresce: largo ? .9 : .28 };
    pintar(performance.now());
  }

  function cobrir(zoom) {
    if (!imagem || !fotoL || !fotoA) return;
    var escala = Math.max(g.vw / fotoL, g.vh / fotoA) * zoom;
    var w = fotoL * escala, h = fotoA * escala;
    imagem.setAttribute("width", w.toFixed(1));
    imagem.setAttribute("height", h.toFixed(1));
    imagem.setAttribute("x", ((g.vw - w) * foco[0]).toFixed(1));
    imagem.setAttribute("y", ((g.vh - h) * foco[1]).toFixed(1));
  }

  function pintar(agora) {
    quadro = 0;
    if (!g) return;
    if (!vivo || semFoto) {
      riscos.forEach(function (r) { r.setAttribute("stroke-width", g.base.toFixed(2)); });
      return;
    }
    var p = lim(-abre.getBoundingClientRect().top / (abre.offsetHeight - g.vh));
    var e = suave(lim((p - .04) / .6));
    var sw = g.base * Math.pow(g.fim / g.base, e);
    if (pulso) {                                   // convite: os riscos "respiram" enquanto ninguém rola
      var t = (agora - inicioPulso) / 1100;
      if (t >= 1 || p > .01) pulso = false;
      else sw *= 1 + .55 * Math.sin(Math.PI * t);
    }
    // Enquanto o título sai, os telhados descem para o meio da tela e crescem: a casa
    // abre do centro, não do canto de cima (no desktop o quadro intermediário ficava vazio).
    var c = suave(lim(p / .34));
    var escala = 1 + g.cresce * c;
    if (grupo) {
      grupo.setAttribute("transform", "translate(" + g.cx.toFixed(1) + "," + (g.cy + c * (g.vh / 2 - g.cy)).toFixed(1) +
        ") scale(" + escala.toFixed(4) + ") translate(" + (-g.cx).toFixed(1) + "," + (-g.cy).toFixed(1) + ")");
    }
    riscos.forEach(function (r) { r.setAttribute("stroke-width", (sw / escala).toFixed(2)); });
    cobrir(1.12 - .12 * e);                        // a câmera recua enquanto a casa abre
    var sai = lim(p / .12);                      // o título sai antes de os telhados passarem por ele
    capa.style.opacity = (1 - sai).toFixed(3);
    capa.style.transform = "translate3d(0," + (-30 * sai).toFixed(1) + "px,0)";
    capa.style.visibility = sai >= 1 ? "hidden" : "visible";
    var entra = suave(lim((p - .62) / .25));
    if (sombra) sombra.style.opacity = entra.toFixed(3);
    if (destaque) {
      destaque.style.opacity = entra.toFixed(3);
      destaque.style.transform = "translate3d(0," + ((1 - entra) * 34).toFixed(1) + "px,0)";
      destaque.style.visibility = entra <= 0 ? "hidden" : "visible";
    }
    if (pulso) pedir();
  }

  function pedir() { if (!quadro) quadro = requestAnimationFrame(pintar); }

  window.addEventListener("resize", medir);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(medir);
  medir();
  if (!vivo || semFoto) return;

  window.addEventListener("scroll", pedir, { passive: true });
  window.setInterval(function () {
    if (pulso || document.hidden || window.scrollY > 4) return;
    pulso = true; inicioPulso = performance.now(); pedir();
  }, 3800);
})();
