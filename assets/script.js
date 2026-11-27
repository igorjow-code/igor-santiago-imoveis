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

// --- ficha: a rua de fotos que se arrasta de lado -----------------------------
// A tira é rolagem nativa (funciona sem este script). Aqui entram a contagem, o fio
// de progresso, as setas, o arraste com o mouse e o aceno que convida o dedo.
// Só transform e scrollLeft; um único ouvinte passivo de rolagem por tira.
(function () {
  "use strict";
  var tiras = document.querySelectorAll("[data-tira]");
  if (!tiras.length) return;
  var vivo = document.documentElement.classList.contains("js");

  Array.prototype.forEach.call(tiras, function (raiz) {
    var rolo = raiz.querySelector(".tira-rolo");
    var trilho = raiz.querySelector(".tira-trilho");
    var quadros = Array.prototype.slice.call(raiz.querySelectorAll(".tira-quadro"));
    var conta = raiz.querySelector(".tira-conta");
    var fio = raiz.querySelector(".tira-fio i");
    var antes = raiz.querySelector("[data-anterior]");
    var depois = raiz.querySelector("[data-proxima]");
    if (!rolo || !trilho || !quadros.length) return;
    var total = quadros.filter(function (q) { return !q.classList.contains("tira-fim"); }).length;
    var atual = 0, quadro = 0, tocou = false;
    raiz.classList.add("com-tira");

    function dois(n) { return (n < 10 ? "0" : "") + n; }
    function maximo() { return Math.max(1, rolo.scrollWidth - rolo.clientWidth); }
    function inicio(k) { return quadros[k].offsetLeft - quadros[0].offsetLeft; }
    function indice() {                       // quadro que está na margem de leitura
      var x = rolo.scrollLeft, melhor = 0, perto = Infinity;
      for (var k = 0; k < quadros.length; k++) {
        var d = Math.abs(inicio(k) - x);
        if (d < perto) { perto = d; melhor = k; }
      }
      return x >= maximo() - 2 ? quadros.length - 1 : melhor;
    }

    function pintar() {
      quadro = 0;
      var k = indice(), n = Math.min(k, total - 1) + 1;
      if (n !== atual && conta) {
        atual = n;
        conta.innerHTML = "<b>" + dois(n) + "</b> / " + dois(total);
      }
      var passo = 1 / quadros.length;
      if (fio) fio.style.setProperty("--p", (passo + (1 - passo) * Math.min(1, rolo.scrollLeft / maximo())).toFixed(4));
      if (antes) antes.disabled = rolo.scrollLeft <= 2;
      if (depois) depois.disabled = rolo.scrollLeft >= maximo() - 2;
    }
    function pedir() { if (!quadro) quadro = requestAnimationFrame(pintar); }

    function ir(passo) {
      var k = Math.max(0, Math.min(quadros.length - 1, indice() + passo));
      tocou = true;
      rolo.scrollTo({ left: Math.min(inicio(k), maximo()), behavior: vivo ? "smooth" : "auto" });
    }
    if (antes) antes.addEventListener("click", function () { ir(-1); });
    if (depois) depois.addEventListener("click", function () { ir(1); });
    rolo.addEventListener("scroll", function () {
      if (rolo.scrollLeft > 6) tocou = true;
      pedir();
    }, { passive: true });
    window.addEventListener("resize", pedir);

    // arraste com o mouse (o dedo já arrasta sozinho: é rolagem nativa)
    var arrasto = null, calar = false;
    rolo.addEventListener("pointerdown", function (ev) {
      if (ev.pointerType !== "mouse" || ev.button !== 0) return;
      if (ev.target.closest && ev.target.closest("video")) return;   // controles do vídeo
      arrasto = { x: ev.clientX, de: rolo.scrollLeft, andou: false };
    });
    window.addEventListener("pointermove", function (ev) {
      if (!arrasto) return;
      var dx = ev.clientX - arrasto.x;
      if (!arrasto.andou && Math.abs(dx) < 5) return;
      if (!arrasto.andou) { arrasto.andou = true; tocou = true; rolo.classList.add("arrastando"); }
      rolo.scrollLeft = arrasto.de - dx;
    });
    function soltar() {
      if (!arrasto) return;
      var andou = arrasto.andou;
      arrasto = null;
      if (!andou) return;
      calar = true;                           // o clique que fecha o arraste não abre link
      window.setTimeout(function () { calar = false; }, 0);
      // encaixa no quadro mais próximo e só então religa o encaixe nativo
      rolo.scrollTo({ left: Math.min(inicio(indice()), maximo()), behavior: vivo ? "smooth" : "auto" });
      window.setTimeout(function () { rolo.classList.remove("arrastando"); }, vivo ? 520 : 0);
    }
    window.addEventListener("pointerup", soltar);
    window.addEventListener("pointercancel", soltar);
    rolo.addEventListener("click", function (ev) {
      if (calar) { ev.preventDefault(); ev.stopPropagation(); }
    }, true);

    // aceno: enquanto ninguém arrasta, a rua anda um pouco e volta (até 3 vezes)
    if (vivo && "IntersectionObserver" in window && rolo.scrollWidth > rolo.clientWidth + 40) {
      var acenos = 0, relogio = 0;
      var acenar = function () {
        if (tocou || acenos >= 3 || document.hidden) return;
        acenos++;
        trilho.classList.add("acena");
      };
      trilho.addEventListener("animationend", function (ev) {
        if (ev.animationName === "tira-acena") trilho.classList.remove("acena");
      });
      new IntersectionObserver(function (entradas) {
        window.clearInterval(relogio);
        if (!entradas[0].isIntersecting || tocou) return;
        window.setTimeout(acenar, 1700);
        relogio = window.setInterval(acenar, 5600);
      }, { threshold: .55 }).observe(rolo);
    }

    // toque ou clique (sem arraste) amplia a foto; o teclado anda de foto em foto
    var comFoto = quadros.filter(function (q) { return !q.classList.contains("tira-fim") && q.querySelector("img"); });
    if (comFoto.length && typeof HTMLDialogElement !== "undefined") {
      // uma parada de Tab só (a foto da vez); as setas do teclado andam de foto em foto
      var vez = function (k) {
        comFoto.forEach(function (q, n) { q.setAttribute("tabindex", n === k ? "0" : "-1"); });
      };
      comFoto.forEach(function (q, k) {
        q.setAttribute("role", "button");
        q.setAttribute("aria-label", "Ampliar foto " + (k + 1) + " de " + comFoto.length);
        q.addEventListener("click", function () { if (!calar) abrirLuz(comFoto, k, rolo); });
        q.addEventListener("focus", function () {
          vez(k);
          // no teclado, a foto em foco vira a foto da vez (o contador e o fio acompanham)
          if (q.matches(":focus-visible")) rolo.scrollTo({ left: Math.min(inicio(quadros.indexOf(q)), maximo()), behavior: "auto" });
        });
        q.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); abrirLuz(comFoto, k, rolo); }
          var passo = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
          if (!passo) return;
          ev.preventDefault();
          var alvo = comFoto[Math.max(0, Math.min(comFoto.length - 1, k + passo))];
          tocou = true;
          alvo.focus();
        });
      });
      vez(0);
      rolo.removeAttribute("tabindex");
      // a foto de dentro da folha abre a mesma foto ampliada
      Array.prototype.forEach.call(document.querySelectorAll(".folha-foto[data-foto]"), function (f) {
        var k = Number(f.dataset.foto);
        if (!comFoto[k] || raiz.closest(".ficha-videos")) return;
        f.setAttribute("role", "button");
        f.setAttribute("tabindex", "0");
        f.setAttribute("aria-label", "Ampliar foto " + (k + 1) + " de " + comFoto.length);
        f.addEventListener("click", function () { abrirLuz(comFoto, k, rolo); });
        f.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); abrirLuz(comFoto, k, rolo); }
        });
      });
    }

    if (document.fonts && document.fonts.ready) document.fonts.ready.then(pedir);
    window.addEventListener("load", pedir);
    pintar();
  });

  // --- luz: a foto ampliada, com as mesmas setas, o mesmo contador e o mesmo fio ---
  var luz = null, luzFoto, luzConta, luzFio, lista = [], onde = 0, deOnde = null, abriu = null;
  function doisDigitos(n) { return (n < 10 ? "0" : "") + n; }
  function mostrar(k) {
    onde = (k + lista.length) % lista.length;
    var origem = lista[onde].querySelector("img");
    luzFoto.style.animation = "none";
    luzFoto.src = origem.currentSrc || origem.src;
    luzFoto.alt = origem.alt;
    void luzFoto.offsetWidth;
    luzFoto.style.animation = "";
    luzConta.innerHTML = "<b>" + doisDigitos(onde + 1) + "</b> / " + doisDigitos(lista.length);
    luzFio.style.setProperty("--p", ((onde + 1) / lista.length).toFixed(4));
  }
  function montar() {
    luz = document.createElement("dialog");
    luz.className = "luz";
    luz.setAttribute("aria-label", "Foto ampliada");
    luz.innerHTML = '<div class="luz-palco"><img alt="" /></div>' +
      '<button class="tira-seta luz-fechar" type="button" aria-label="Fechar foto ampliada">&#215;</button>' +
      '<div class="luz-pe"><p class="tira-conta"></p><span class="tira-fio" aria-hidden="true"><i></i></span>' +
      '<div class="tira-setas"><button class="tira-seta" type="button" data-anterior aria-label="Foto anterior">&#8592;</button>' +
      '<button class="tira-seta" type="button" data-proxima aria-label="Próxima foto">&#8594;</button></div></div>';
    document.body.appendChild(luz);
    luzFoto = luz.querySelector("img");
    luzConta = luz.querySelector(".tira-conta");
    luzFio = luz.querySelector(".tira-fio i");
    luz.querySelector("[data-anterior]").addEventListener("click", function () { mostrar(onde - 1); });
    luz.querySelector("[data-proxima]").addEventListener("click", function () { mostrar(onde + 1); });
    luz.querySelector(".luz-fechar").addEventListener("click", function () { luz.close(); });
    luz.addEventListener("click", function (ev) {
      if (ev.target === luz || ev.target.classList.contains("luz-palco")) luz.close();
    });
    luz.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowLeft") mostrar(onde - 1);
      if (ev.key === "ArrowRight") mostrar(onde + 1);
    });
    var toque = null;                        // no celular, o dedo passa as fotos
    luz.addEventListener("touchstart", function (ev) { toque = ev.touches.length === 1 ? ev.touches[0].clientX : null; }, { passive: true });
    luz.addEventListener("touchend", function (ev) {
      if (toque === null) return;
      var dx = ev.changedTouches[0].clientX - toque;
      toque = null;
      if (Math.abs(dx) > 44) mostrar(onde + (dx < 0 ? 1 : -1));
    }, { passive: true });
    luz.addEventListener("close", function () {
      document.documentElement.classList.remove("luz-aberta");
      var quadro = lista[onde];
      if (deOnde && quadro) deOnde.scrollTo({ left: quadro.offsetLeft - lista[0].offsetLeft, behavior: "auto" });
      // o foco volta para quem abriu (a foto da tira ou a foto da folha)
      var volta = abriu && document.contains(abriu) ? abriu : quadro;
      if (volta) volta.focus({ preventScroll: true });
      abriu = null;
    });
  }
  function abrirLuz(quadros, k, rolo) {
    if (!luz) montar();
    abriu = document.activeElement && document.activeElement.classList.contains("folha-foto") ? document.activeElement : null;
    lista = quadros;
    deOnde = rolo;
    mostrar(k);
    document.documentElement.classList.add("luz-aberta");
    luz.showModal();
  }

  // --- vídeos: o controle nativo só entra depois do toque no botão da própria página ---
  var videos = Array.prototype.slice.call(document.querySelectorAll(".tira-quadro--video video"));
  videos.forEach(function (video) {
    var botao = video.parentNode.querySelector(".tira-tocar");
    if (!botao) return;
    video.controls = false;
    botao.hidden = false;
    botao.addEventListener("click", function () {
      videos.forEach(function (outro) { if (outro !== video) outro.pause(); });
      botao.hidden = true;
      video.controls = true;
      var toca = video.play();
      if (toca && toca.catch) toca.catch(function () {});
    });
  });
})();

// --- ficha: a conta do mês soma até o total -----------------------------------
// O texto que vem no HTML é o valor final. A contagem só começa quando a conta entra
// na tela e sempre termina no texto original (um relógio garante, mesmo com a aba oculta).
(function () {
  "use strict";
  if (!document.documentElement.classList.contains("js")) return;
  if (!("IntersectionObserver" in window)) return;
  var linha = document.querySelector(".folha .conta-total[data-total][data-parcelas]");
  var forte = linha && linha.querySelector("strong");
  var fim = linha ? Number(linha.dataset.total) : 0;
  // só há soma para mostrar quando mais de uma parcela em reais entra no total
  if (!forte || !fim || Number(linha.dataset.parcelas) < 2) return;
  var texto = forte.textContent;
  function moeda(n) { return "R$ " + String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, "."); }
  var olho = new IntersectionObserver(function (entradas) {
    if (!entradas[0].isIntersecting) return;
    olho.disconnect();
    var espera = 520, dura = 1100, comeco = performance.now() + espera;
    forte.textContent = moeda(0);
    function passo(agora) {
      var t = Math.min(1, Math.max(0, (agora - comeco) / dura));
      if (t >= 1) { forte.textContent = texto; return; }
      forte.textContent = moeda(fim * (1 - Math.pow(1 - t, 4)));
      requestAnimationFrame(passo);
    }
    requestAnimationFrame(passo);
    window.setTimeout(function () { forte.textContent = texto; }, espera + dura + 400);
  }, { threshold: .15, rootMargin: "0px 0px -40px 0px" });
  olho.observe(linha);
})();

// --- alugar: a conta de entrada troca de imóvel no toque ------------------------
// Sem JS as contas ficam uma abaixo da outra. Com JS a lista da esquerda escolhe qual
// aparece; com movimento, a conta soma de novo a cada escolha (e na primeira vez que
// entra na tela). O texto que vem no HTML é sempre o valor final.
(function () {
  "use strict";
  var raiz = document.querySelector("[data-entrada]");
  if (!raiz) return;
  var escolha = raiz.querySelector(".entrada-escolha");
  var botoes = Array.prototype.slice.call(raiz.querySelectorAll(".entrada-botao"));
  var contas = Array.prototype.slice.call(raiz.querySelectorAll(".entrada-conta"));
  if (!escolha || botoes.length < 2 || botoes.length !== contas.length) return;
  var vivo = document.documentElement.classList.contains("js");
  var relogio = 0, quadro = 0, vezes = 0;
  function moeda(n) { return "R$ " + String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, "."); }
  function somar(conta) {
    var linha = conta.querySelector("[data-entrada-total]");
    var forte = linha && linha.querySelector("strong");
    var fim = linha ? Number(linha.getAttribute("data-entrada-total")) : 0;
    if (!forte || !fim) return;
    var texto = forte.getAttribute("data-final") || forte.textContent;
    forte.setAttribute("data-final", texto);
    window.clearTimeout(relogio); cancelAnimationFrame(quadro);
    conta.classList.remove("soma"); void conta.offsetWidth; conta.classList.add("soma");
    // a primeira soma é a apresentação; quem compara imóveis recebe a resposta depressa
    var celular = window.matchMedia && window.matchMedia("(max-width: 899px)").matches;
    var espera = vezes ? 120 : (celular ? 160 : 460), dura = vezes ? 450 : 900, comeco = performance.now() + espera;
    vezes++;
    forte.textContent = moeda(0);
    function passo(agora) {
      var t = Math.min(1, Math.max(0, (agora - comeco) / dura));
      if (t >= 1) { forte.textContent = texto; return; }
      forte.textContent = moeda(fim * (1 - Math.pow(1 - t, 4)));
      quadro = requestAnimationFrame(passo);
    }
    quadro = requestAnimationFrame(passo);
    relogio = window.setTimeout(function () { cancelAnimationFrame(quadro); forte.textContent = texto; }, espera + dura + 400);
  }
  function mostrar(k, animar) {
    botoes.forEach(function (b, n) { b.setAttribute("aria-pressed", n === k ? "true" : "false"); });
    contas.forEach(function (c, n) {
      var forte = c.querySelector("[data-entrada-total] strong");
      if (forte && forte.getAttribute("data-final")) forte.textContent = forte.getAttribute("data-final");
      c.hidden = n !== k;
    });
    if (animar && vivo) somar(contas[k]);
  }
  escolha.hidden = false;
  raiz.classList.add("entrada--abas");
  botoes.forEach(function (b, k) { b.addEventListener("click", function () { mostrar(k, true); }); });
  mostrar(0, false);
  if (vivo && "IntersectionObserver" in window) {
    var olho = new IntersectionObserver(function (entradas) {
      if (!entradas[0].isIntersecting) return;
      olho.disconnect();
      var k = 0;
      botoes.forEach(function (b, n) { if (b.getAttribute("aria-pressed") === "true") k = n; });
      somar(contas[k]);
    }, { threshold: .35 });
    olho.observe(raiz.querySelector(".entrada-contas"));
  }
})();

// --- capa: os telhados da logo abrem e mostram a casa -------------------------
// Momento assinatura da direção "Marca forte". A rolagem engrossa os 5 riscos da
// máscara SVG até a foto ocupar a tela. Sem "js" no <html> (movimento reduzido ou
// navegador antigo) nada disto roda: o CSS já mostra a foto inteira, parada.
(function () {
  "use strict";
  var raiz = document.documentElement;
  var abre = document.querySelector(".abre");
  var pele = document.body.classList.contains("pagina-capa");
  // na ficha a barra do celular leva o valor e a visita: ocupa a largura e só sai quando
  // outro botão de conversa está na tela, no fecho e com o menu aberto. Enquanto o preço
  // do topo está à vista ela espera fora (o preço não aparece duas vezes na mesma tela).
  var ficha = document.body.classList.contains("pagina-ficha");
  var precoTopo = ficha && document.querySelector(".ficha-valor");
  if (precoTopo && "IntersectionObserver" in window) {
    raiz.classList.add("preco-a-vista");
    new IntersectionObserver(function (entradas) {
      raiz.classList.toggle("preco-a-vista", entradas[0].isIntersecting);
    }, { rootMargin: "-72px 0px 0px 0px" }).observe(precoTopo);
  }
  if (!abre) raiz.classList.remove("na-abertura");
  if (!pele) return;

  // A barra verde do celular só aparece quando não há outro botão de WhatsApp na tela:
  // some na abertura e sempre que um botão principal de conversa está visível.
  // Vale para toda página com a pele nova, não só para a capa.
  if ("IntersectionObserver" in window) {
    if (abre) new IntersectionObserver(function (entradas) {
      raiz.classList.toggle("na-abertura", entradas[0].isIntersecting);
    }, { rootMargin: "0px 0px -40% 0px" }).observe(abre);
    var aVista = [];
    var olhoBotoes = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (entrada) {
        var i = aVista.indexOf(entrada.target);
        if (entrada.isIntersecting && i < 0) aVista.push(entrada.target);
        if (!entrada.isIntersecting && i >= 0) aVista.splice(i, 1);
      });
      raiz.classList.toggle("cta-a-vista", aVista.length > 0);
    }, { threshold: .6 });
    Array.prototype.forEach.call(document.querySelectorAll(ficha ? 'main .bt[href*="wa.me"]' : 'main .bloco .bt[href*="wa.me"]'), function (b) {
      olhoBotoes.observe(b);
    });
    // ...e também enquanto as dúvidas, o fecho ou a rubrica estão na tela (ele cobria o "+" e o texto)
    var blocosLivres = [];
    var olhoBlocos = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (entrada) {
        var i = blocosLivres.indexOf(entrada.target);
        if (entrada.isIntersecting && i < 0) blocosLivres.push(entrada.target);
        if (!entrada.isIntersecting && i >= 0) blocosLivres.splice(i, 1);
      });
      raiz.classList.toggle("sem-flutuante", blocosLivres.length > 0);
    }, { rootMargin: "0px 0px -18% 0px" });
    Array.prototype.forEach.call(document.querySelectorAll(ficha ? "main .fecho" : "main .faq, main .fecho"), function (b) {
      olhoBlocos.observe(b);
    });
    // a tabela de medidas e a rubrica têm conteúdo no canto direito: basta encostarem na tela
    var olhoCanto = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (entrada) {
        var i = blocosLivres.indexOf(entrada.target);
        if (entrada.isIntersecting && i < 0) blocosLivres.push(entrada.target);
        if (!entrada.isIntersecting && i >= 0) blocosLivres.splice(i, 1);
      });
      raiz.classList.toggle("sem-flutuante", blocosLivres.length > 0);
    });
    Array.prototype.forEach.call(ficha ? [] : document.querySelectorAll("main .medidas, main .rubrica, main .entrada"), function (b) {
      olhoCanto.observe(b);
    });
  } else {
    raiz.classList.remove("na-abertura");
  }
  if (!abre) return;

  var palco = abre.querySelector(".palco");
  var svg = abre.querySelector(".abre-svg");
  var capa = abre.querySelector(".capa-texto");
  if (!palco || !svg || !capa) return;
  var semFoto = abre.classList.contains("abre--sem-foto");
  var vivo = raiz.classList.contains("js");
  if (!vivo && !semFoto) return;

  var riscos = Array.prototype.slice.call(svg.querySelectorAll(".risco"));
  var grupo = svg.querySelector(".riscos");
  var tampas = svg.querySelectorAll(".tampa");
  var imagem = svg.querySelector("image");
  var sombra = abre.querySelector(".abre-sombra");
  var destaque = abre.querySelector(".destaque");
  var sobre = abre.querySelector(".capa-sobre");
  // Depois da chegada coreografada as animações de entrada são desligadas: animação com
  // "forwards" ganha de estilo em linha e impediria a sobrelinha de sair primeiro.
  window.setTimeout(function () { abre.classList.add("chegou"); }, 2900);
  var fotoL = Number(abre.dataset.fotoL) || 0;
  var fotoA = Number(abre.dataset.fotoA) || 0;
  var foco = (abre.dataset.foco || "50% 50%").split(/\s+/).map(function (v) {
    var n = parseFloat(v);
    return (isNaN(n) ? 50 : n) / 100;
  });
  if (imagem) imagem.setAttribute("preserveAspectRatio", "none");
  var g = null, quadro = 0, pulso = false, inicioPulso = 0, capaDy = 0;

  function lim(v) { return Math.min(1, Math.max(0, v)); }
  function suave(t) { return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

  function medir() {
    var vw = palco.clientWidth, vh = semFoto ? window.innerHeight : palco.clientHeight;
    var largo = vw >= 900;
    var primeiro = capa.firstElementChild || capa;
    var topoTexto = primeiro.getBoundingClientRect().top - palco.getBoundingClientRect().top - capaDy;
    var respiro = largo ? 98 : 86;
    var altura = Math.max(130, topoTexto - respiro - (largo ? 30 : 22));   // os telhados moram entre o topo e o título
    var bw = Math.min(vw * (largo ? .48 : .84), altura / .86), bh = bw * .86;
    var x0 = (vw - bw) / 2, y0 = respiro + (altura - bh) / 2;
    riscos.forEach(function (r, k) {                                       // 5 telhados empilhados: o desenho da logo
      var dy = k * .145 * bh;
      r.setAttribute("points", [[.02, .40], [.74, .05], [.98, .17]].map(function (p) {
        return (x0 + p[0] * bw).toFixed(1) + "," + (y0 + p[1] * bh + dy).toFixed(1);
      }).join(" "));
    });
    // "fim" é o risco mais grosso que ainda faz diferença: o bastante para cobrir os cantos.
    // Risco gigante (2,4x a diagonal) custava quadros no desktop sem mudar um pixel na tela.
    g = { vw: vw, vh: vh, bw: bw, bh: bh, base: bw * .052, fim: Math.max(vw * 1.2, vh * 1.4),
          cx: vw / 2, cy: y0 + bh * .49, cresce: largo ? 1 : .22 };
    pintar(performance.now());
  }

  function pintar(agora) {
    quadro = 0;
    if (!g) return;
    var p = (!vivo || semFoto) ? 0 : lim(-abre.getBoundingClientRect().top / (abre.offsetHeight - g.vh));

    // Três movimentos sobrepostos desde o primeiro pixel de rolagem (sem tempo morto):
    // os riscos engrossam, o conjunto desce ao centro e cresce, e o título sai.
    var e = Math.pow(lim(p / .26), 1.35);
    var c = suave(lim(p / .20));
    var escala = 1 + g.cresce * c;
    var sw = g.base * escala * Math.pow(g.fim / g.base, e);
    if (pulso) {                                   // convite: os riscos "respiram" enquanto ninguém rola
      var t = (agora - inicioPulso) / 1100;
      if (t >= 1 || p > .01) pulso = false;
      else sw *= 1 + .5 * Math.sin(Math.PI * t);
    }
    var cy = g.cy + c * (g.vh / 2 - g.cy);
    if (grupo) {
      grupo.setAttribute("transform", "translate(" + g.cx.toFixed(1) + "," + cy.toFixed(1) +
        ") scale(" + escala.toFixed(4) + ") translate(" + (-g.cx).toFixed(1) + "," + (-g.cy).toFixed(1) + ")");
    }
    riscos.forEach(function (r) { r.setAttribute("stroke-width", (sw / escala).toFixed(2)); });

    // As pontas são cortadas na vertical: quando os riscos se fundem, os lados da janela
    // ficam retos (parede de casa) em vez de serrilhados.
    var meia = g.bw * .48 * escala + Math.max(0, sw - g.base * escala) * .45;
    // (dois retângulos pretos dentro da máscara; clipPath aqui custava 7 ms por quadro no desktop)
    if (tampas.length === 2) {
      var beira = [[-g.vw, g.cx - meia + g.vw], [g.cx + meia, g.vw * 2]];
      for (var k = 0; k < 2; k++) {
        tampas[k].setAttribute("x", beira[k][0].toFixed(1));
        tampas[k].setAttribute("width", Math.max(0, beira[k][1]).toFixed(1));
        tampas[k].setAttribute("y", (-g.vh).toFixed(1));
        tampas[k].setAttribute("height", (g.vh * 3).toFixed(1));
      }
    }
    if (!vivo || semFoto) return;

    // A foto acompanha a janela: na chegada a casa inteira cabe dentro dos telhados e,
    // conforme a janela cresce, a casa vem na direção de quem rola até ocupar a tela.
    if (imagem && fotoL && fotoA) {
      var metadeAlta = g.bh * .5 * escala + sw * .56;
      var esq = Math.max(0, g.cx - meia), dir = Math.min(g.vw, g.cx + meia);
      var topo = Math.max(0, cy - metadeAlta), baixo = Math.min(g.vh, cy + metadeAlta);
      var rw = dir - esq, rh = baixo - topo;
      var s = Math.max(rw / fotoL, rh / fotoA) * 1.04;
      var w = fotoL * s, h = fotoA * s;
      imagem.setAttribute("width", w.toFixed(1));
      imagem.setAttribute("height", h.toFixed(1));
      imagem.setAttribute("x", (esq + (rw - w) * foco[0]).toFixed(1));
      imagem.setAttribute("y", (topo + (rh - h) * foco[1]).toFixed(1));
    }

    var sai = lim(p / .11);                     // o título sobe e some antes de a janela chegar nele
    // a sobrelinha é a primeira a sair, antes de a janela passar por ela
    if (sobre && abre.classList.contains("chegou")) sobre.style.opacity = (1 - lim(p / .04)).toFixed(3);
    capaDy = -64 * sai;
    capa.style.opacity = (1 - sai).toFixed(3);
    capa.style.transform = "translate3d(0," + capaDy.toFixed(1) + "px,0)";
    capa.style.visibility = sai >= 1 ? "hidden" : "visible";
    var entra = suave(lim((p - .27) / .27));    // sem platô: a ficha entra logo depois de a casa abrir
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
