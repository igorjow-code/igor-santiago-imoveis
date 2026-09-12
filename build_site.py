#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gerador do site Igor Santiago Imoveis.

Le os dados em dados/ e escreve HTML estatico em publico/.
Python 3.11, stdlib apenas (convencao do repo, ver CLAUDE.md).

Uso:
    python build_site.py            build normal (permite imovel demo)
    python build_site.py --check    so lista o que falta, nao escreve nada
    python build_site.py --publicar build de publicacao: RECUSA se houver imovel demo
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
DADOS = ROOT / "dados"
ASSETS = ROOT / "assets"
SAIDA = ROOT / "publico"

PENDENTE = "__PENDENTE_IGOR__"

# Campos que toda ficha precisa ter para virar pagina.
OBRIGATORIOS = ("slug", "titulo", "operacao", "tipo", "bairro", "cidade", "preco")
NUMERICOS = ("area", "area_terreno", "quartos", "suites", "vagas",
             "preco", "condominio", "iptu")
BOOLEANOS = ("destaque", "demo")


# --------------------------------------------------------------------------
# leitura dos dados
# --------------------------------------------------------------------------

def ler_corretor() -> dict:
    with (DADOS / "corretor.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def ler_ficha(caminho: Path) -> dict:
    """Front-matter entre '---' + corpo em secoes '##'."""
    texto = caminho.read_text(encoding="utf-8")
    if not texto.startswith("---"):
        raise ValueError(f"{caminho}: falta o front-matter entre ---")

    _, bruto, corpo = texto.split("---", 2)

    dados: dict = {}
    for linha in bruto.strip().splitlines():
        if not linha.strip() or ":" not in linha:
            continue
        chave, valor = linha.split(":", 1)
        dados[chave.strip()] = valor.strip()

    for chave in NUMERICOS:
        if chave in dados and dados[chave] != "":
            dados[chave] = int(dados[chave])
    for chave in BOOLEANOS:
        dados[chave] = str(dados.get(chave, "false")).lower() == "true"

    dados.update(_secoes(corpo))
    dados["_arquivo"] = caminho
    return dados


def _secoes(corpo: str) -> dict:
    """Separa '## Descricao', '## Destaques' e '## Duvidas comuns'."""
    saida = {"descricao": "", "destaques": [], "duvidas": []}
    atual = None
    pergunta = None

    for linha in corpo.splitlines():
        cabecalho = re.match(r"^##\s+(.*)$", linha)
        if cabecalho and not linha.startswith("###"):
            nome = _sem_acento(cabecalho.group(1)).lower()
            atual = ("descricao" if "descri" in nome
                     else "destaques" if "destaque" in nome
                     else "duvidas" if "duvida" in nome
                     else None)
            pergunta = None
            continue

        if atual == "descricao":
            saida["descricao"] += linha + "\n"
        elif atual == "destaques" and linha.strip().startswith("- "):
            saida["destaques"].append(linha.strip()[2:].strip())
        elif atual == "duvidas":
            titulo = re.match(r"^###\s+(.*)$", linha)
            if titulo:
                pergunta = {"pergunta": titulo.group(1).strip(), "resposta": ""}
                saida["duvidas"].append(pergunta)
            elif pergunta is not None:
                pergunta["resposta"] += linha + "\n"

    saida["descricao"] = _paragrafos(saida["descricao"])
    for item in saida["duvidas"]:
        item["resposta"] = " ".join(item["resposta"].split())
    return saida


def _sem_acento(texto: str) -> str:
    tabela = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
                           "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC")
    return texto.translate(tabela)


def _paragrafos(bruto: str) -> list[str]:
    return [" ".join(bloco.split())
            for bloco in bruto.strip().split("\n\n") if bloco.strip()]


def ler_imoveis() -> list[dict]:
    pasta = DADOS / "imoveis"
    if not pasta.is_dir():
        return []
    imoveis = [ler_ficha(f / "ficha.md")
               for f in sorted(pasta.iterdir()) if (f / "ficha.md").is_file()]
    imoveis.sort(key=lambda i: (i.get("operacao") != "venda", -i.get("preco", 0)))
    return imoveis


# --------------------------------------------------------------------------
# formatacao
# --------------------------------------------------------------------------

def e(valor) -> str:
    return html.escape(str(valor), quote=True)


def moeda(valor: int) -> str:
    return "R$ " + f"{valor:,}".replace(",", ".")


def preco_rotulo(imovel: dict) -> str:
    if imovel.get("operacao") == "locacao":
        return moeda(imovel["preco"]) + '<span class="por-mes">/mês</span>'
    return moeda(imovel["preco"])


def wa_link(corretor: dict, mensagem: str) -> str:
    return f"https://wa.me/{corretor['whatsapp_e164']}?text={quote(mensagem)}"


def wa_imovel(corretor: dict, imovel: dict) -> str:
    verbo = "alugar" if imovel["operacao"] == "locacao" else "comprar"
    msg = (f"Olá, Igor. Vi no seu site o imóvel \"{imovel['titulo']}\" "
           f"({preco_texto(imovel)}) e gostaria de {verbo}.")
    return wa_link(corretor, msg)


def preco_texto(imovel: dict) -> str:
    base = moeda(imovel["preco"])
    return base + "/mês" if imovel["operacao"] == "locacao" else base


def specs(imovel: dict) -> list[tuple[str, str]]:
    itens: list[tuple[str, str]] = []
    if imovel.get("area"):
        itens.append(("Área construída", f"{imovel['area']} m²"))
    if imovel.get("area_terreno"):
        itens.append(("Terreno", f"{imovel['area_terreno']} m²"))
    if imovel.get("quartos"):
        itens.append(("Quartos", str(imovel["quartos"])))
    if imovel.get("suites"):
        itens.append(("Suítes", str(imovel["suites"])))
    if imovel.get("vagas"):
        itens.append(("Vagas", str(imovel["vagas"])))
    if imovel.get("condominio"):
        itens.append(("Condomínio", moeda(imovel["condominio"]) + "/mês"))
    if imovel.get("iptu"):
        itens.append(("IPTU", moeda(imovel["iptu"]) + "/ano"))
    return itens


def resumo(imovel: dict) -> str:
    partes = []
    if imovel.get("area"):
        partes.append(f"{imovel['area']} m²")
    if imovel.get("quartos"):
        partes.append(f"{imovel['quartos']} quartos")
    if imovel.get("suites"):
        partes.append(f"{imovel['suites']} suítes")
    if imovel.get("vagas"):
        partes.append(f"{imovel['vagas']} vagas")
    return " · ".join(partes)


# --------------------------------------------------------------------------
# blocos de HTML
# --------------------------------------------------------------------------

def reveal(n: int = 0, passo_ms: int = 80) -> str:
    """Atributo de revelação escalonada: n-ésimo elemento de um grupo visual.
    Sem JS ou com "reduzir movimento", não faz nada (ver script no <head>)."""
    return f'data-reveal style="--atraso:{n * passo_ms}ms"'


def foto_placeholder(rotulo: str, altura: str = "aspect-4-3") -> str:
    return (f'<div class="foto {altura} pendente" role="img" '
            f'aria-label="Foto pendente: {e(rotulo)}">'
            f'<span>FOTO PENDENTE</span></div>')


def barra_demo(imoveis: list[dict]) -> str:
    if not any(i.get("demo") for i in imoveis):
        return ""
    return ('<div class="barra-demo" role="status">PRÉVIA — imóveis de demonstração. '
            'Nenhum destes imóveis existe. Não publicar.</div>')


def cabecalho(corretor: dict, ativo: str, prefixo: str) -> str:
    itens = [("index.html", "Início"), ("imoveis.html", "Imóveis"),
             ("sobre.html", "Sobre"), ("vender.html", "Vender meu imóvel")]
    partes = []
    for href, rotulo in itens:
        classe = ' class="ativo"' if href == ativo else ""
        partes.append(f'<a href="{prefixo}{href}"{classe}>{rotulo}</a>')
    links = "".join(partes)
    return f"""<header class="topo">
  <div class="wrap topo-linha">
    <a class="marca" href="{prefixo}index.html">
      <img class="marca-simbolo" src="{prefixo}assets/simbolo.png" alt="" width="28" height="32" />
      <span class="marca-nome">Igor Santiago</span>
    </a>
    <nav class="nav" aria-label="Principal">{links}</nav>
    <a class="btn btn-wa nav-wa" href="{e(wa_link(corretor, corretor['mensagem_whatsapp_geral']))}"
       target="_blank" rel="noopener">WhatsApp</a>
    <button class="menu-btn" aria-label="Abrir menu" aria-expanded="false">
      <span></span><span></span><span></span>
    </button>
  </div>
</header>"""


def rodape(corretor: dict, prefixo: str) -> str:
    insta = e(corretor["instagram"])
    return f"""<footer class="rodape">
  <div class="wrap rodape-grade">
    <div>
      <p class="rodape-marca">
        <img class="marca-simbolo" src="{prefixo}assets/simbolo.png" alt="" width="24" height="27" />
        Igor Santiago
      </p>
      <p class="rodape-pos">{e(corretor['posicionamento'])}</p>
    </div>
    <nav class="rodape-links" aria-label="Rodapé">
      <a href="{prefixo}imoveis.html">Imóveis</a>
      <a href="{prefixo}sobre.html">Sobre o corretor</a>
      <a href="{prefixo}vender.html">Vender meu imóvel</a>
      <a href="{prefixo}privacidade.html">Privacidade</a>
    </nav>
    <div class="rodape-contato">
      <a href="{e(wa_link(corretor, corretor['mensagem_whatsapp_geral']))}"
         target="_blank" rel="noopener">{e(corretor['whatsapp_exibicao'])}</a>
      <a href="https://instagram.com/{insta}" target="_blank" rel="noopener">@{insta}</a>
      <p>{e(corretor['atuacao'])}</p>
    </div>
  </div>
  <div class="wrap rodape-legal">
    <p><strong>{e(corretor['nome_pessoa'])}</strong> · {e(corretor['titulo_profissional'])}
       · <strong>{e(corretor['creci'])}</strong></p>
    <p class="mini">Imagens e informações sujeitas a conferência em visita. Valores de
       condomínio e IPTU informados pelo proprietário e confirmados na documentação.</p>
  </div>
</footer>"""


def wa_fixo(corretor: dict, mensagem: str) -> str:
    return (f'<a class="wa-fixo" href="{e(wa_link(corretor, mensagem))}" '
            f'target="_blank" rel="noopener">Falar no WhatsApp</a>')


def pagina(titulo: str, descricao: str, corpo: str, corretor: dict,
           imoveis: list[dict], ativo: str, prefixo: str = "",
           mensagem_wa: str | None = None, extra_js: str = "") -> str:
    mensagem_wa = mensagem_wa or corretor["mensagem_whatsapp_geral"]
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao)}" />
<meta name="theme-color" content="#0a0a0a" />
<meta name="robots" content="noindex, nofollow" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet" />
<link rel="stylesheet" href="{prefixo}assets/styles.css" />
<link rel="icon" href="{prefixo}assets/favicon.png" type="image/png" />
<link rel="apple-touch-icon" href="{prefixo}assets/favicon-512.png" />
<script>
  if (!window.matchMedia || !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {{
    if ("IntersectionObserver" in window) document.documentElement.className += " js";
  }}
</script>
</head>
<body>
{barra_demo(imoveis)}
{cabecalho(corretor, ativo, prefixo)}
<main id="conteudo">
{corpo}
</main>
{rodape(corretor, prefixo)}
{wa_fixo(corretor, mensagem_wa)}
<script src="{prefixo}assets/script.js"></script>
{extra_js}
</body>
</html>
"""


def card(imovel: dict, corretor: dict, prefixo: str = "",
         numero: int | None = None, atraso: int = 0) -> str:
    marca_reservado = ('<span class="selo selo-reservado">Reservado</span>'
                       if imovel.get("situacao") == "reservado" else "")
    operacao = "Locação" if imovel["operacao"] == "locacao" else "Venda"
    lote = f'<span class="card-lote">{numero:02d}</span>' if numero else ""
    return f"""<article class="card" data-operacao="{e(imovel['operacao'])}"
         data-tipo="{e(imovel['tipo'])}" data-bairro="{e(imovel['bairro'])}"
         data-quartos="{imovel.get('quartos', 0)}" data-preco="{imovel['preco']}"
         data-reveal style="--atraso:{atraso}ms">
  <a class="card-link" href="{prefixo}imovel/{e(imovel['slug'])}.html">
    <div class="card-foto">
      {foto_placeholder(imovel['titulo'])}
      {lote}
      <span class="selo selo-op">{operacao}</span>
      {marca_reservado}
    </div>
    <div class="card-corpo">
      <p class="card-preco">{preco_rotulo(imovel)}</p>
      <h3 class="card-titulo">{e(imovel['titulo'])}</h3>
      <p class="card-local">{e(imovel['bairro'])} · {e(imovel['cidade'])}</p>
      <p class="card-specs">{e(resumo(imovel))}</p>
    </div>
  </a>
  <a class="card-wa" href="{e(wa_imovel(corretor, imovel))}" target="_blank" rel="noopener">
    Falar sobre este imóvel
  </a>
</article>"""


# --------------------------------------------------------------------------
# paginas
# --------------------------------------------------------------------------

def bio_ou_aviso(corretor: dict, campo: str, fallback: str) -> str:
    valor = corretor.get(campo, PENDENTE)
    if valor == PENDENTE:
        return (f'<span class="pendente-txt" title="Aguardando texto de Igor">'
                f'{e(fallback)}</span>')
    return e(valor)


def anos_mercado(corretor: dict) -> str:
    valor = corretor.get("anos_de_mercado", PENDENTE)
    if valor == PENDENTE:
        return ('<span class="pendente-txt">[anos de mercado — Igor informar]</span>')
    return e(f"{valor} anos de mercado")


def linhas_recibo(imovel: dict) -> list[tuple[str, str]]:
    linhas = [("Preço", preco_texto(imovel))]
    if imovel.get("condominio"):
        linhas.append(("Condomínio", moeda(imovel["condominio"]) + "/mês"))
    if imovel.get("iptu"):
        linhas.append(("IPTU", moeda(imovel["iptu"]) + "/ano"))
    if len(linhas) == 1:
        linhas.append(("Condomínio e IPTU", "sem cobrança — confirmar na visita"))
    return linhas


def recibo(imovel: dict, atraso_base: int = 0) -> str:
    itens = "".join(
        f'<div class="recibo-linha" {reveal(n, 90)}><dt>{e(rotulo)}</dt>'
        f'<dd>{valor}</dd></div>'
        for n, (rotulo, valor) in enumerate(linhas_recibo(imovel)))
    return f"""<article class="recibo" data-reveal style="--atraso:{atraso_base}ms">
  <p class="recibo-titulo">{e(imovel['titulo'])}</p>
  <p class="recibo-local">{e(imovel['bairro'])} · {e(imovel['cidade'])}</p>
  <dl class="recibo-linhas">{itens}</dl>
  <p class="recibo-rodape">Nada some depois do WhatsApp.</p>
</article>"""


def secao_recibo(destaques: list[dict]) -> str:
    if not destaques:
        return ""
    recibos = "".join(recibo(i, atraso_base=n * 110) for n, i in enumerate(destaques))
    return f"""
<section class="secao secao-alt secao-recibo">
  <div class="wrap">
    <p class="sobrelinha" {reveal(0)}>Preço sem letra miúda</p>
    <h2 {reveal(1)}>Preço, condomínio e IPTU — antes de você me chamar, não depois.</h2>
    <p class="sub" {reveal(2)}>É a diferença entre um anúncio e uma negociação séria: você
       decide se cabe no seu orçamento antes de eu te tomar tempo com uma visita.</p>
    <div class="recibo-grade">{recibos}</div>
  </div>
</section>
"""


def pagina_home(corretor: dict, imoveis: list[dict]) -> str:
    destaques = [i for i in imoveis if i.get("destaque")][:3]
    cards = "".join(card(i, corretor, numero=n, atraso=(n - 1) * 90)
                    for n, i in enumerate(destaques, 1))
    provas = "".join(
        f'<div class="prova" {reveal(i)}><h3>{e(p["titulo"])}</h3><p>{e(p["texto"])}</p></div>'
        for i, p in enumerate(corretor["provas"]))

    corpo = f"""
<section class="hero">
  <img class="hero-marca-agua" src="assets/simbolo.png" alt="" aria-hidden="true" />
  <div class="wrap hero-grade">
    <div class="hero-texto">
      <p class="sobrelinha" {reveal(0)}>{e(corretor['atuacao'])}</p>
      <h1 {reveal(1)}>Imóveis de alto padrão com quem <span class="acento">responde</span> pelo negócio do começo ao fim.</h1>
      <p class="hero-sub" {reveal(2)}>{bio_ou_aviso(corretor, 'bio_curta',
        '[bio curta — Igor informar: uma frase sobre quem você é e como atende]')}</p>
      <div class="hero-assinatura" {reveal(3)}>
        <strong>{e(corretor['nome_pessoa'])}</strong>
        <span>{e(corretor['titulo_profissional'])} · {e(corretor['creci'])}</span>
        <span>{anos_mercado(corretor)}</span>
      </div>
      <div class="hero-botoes" {reveal(4)}>
        <a class="btn btn-principal" href="imoveis.html">Ver imóveis</a>
        <a class="btn btn-wa" target="_blank" rel="noopener"
           href="{e(wa_link(corretor, corretor['mensagem_whatsapp_geral']))}">Falar no WhatsApp</a>
      </div>
    </div>
    <div class="hero-foto" {reveal(2)}>
      {foto_placeholder('Retrato de Igor Santiago', 'aspect-3-4')}
      <span class="hero-selo-creci">{e(corretor['creci'])} · ativo</span>
      <p class="mini centro">Foto de Igor — pendente</p>
    </div>
  </div>
</section>

<section class="faixa-provas">
  <div class="wrap provas-grade">{provas}</div>
</section>
{secao_recibo(destaques)}
<section class="secao">
  <div class="wrap">
    <div class="secao-topo" {reveal(0)}>
      <h2>Selecionados</h2>
      <a class="link-seta" href="imoveis.html">Ver todos os imóveis</a>
    </div>
    <div class="grade-cards grade-cards--vitrine">{cards}</div>
  </div>
</section>

<section class="faixa-captacao">
  <div class="wrap captacao-grade">
    <div {reveal(0)}>
      <h2>Tem um imóvel para vender?</h2>
      <p>Faço a avaliação de mercado do seu imóvel em {e(corretor['cidade'])} com base em
         comparáveis reais do bairro — e explico como cheguei ao número, sem promessa
         inflada para conseguir a exclusividade.</p>
    </div>
    <div class="captacao-cta" {reveal(1)}>
      <a class="btn btn-claro" href="vender.html">Como funciona a avaliação</a>
    </div>
  </div>
</section>
"""
    return pagina(
        titulo="Igor Santiago Imóveis — alto padrão em Feira de Santana",
        descricao=("Corretor de imóveis em Feira de Santana, CRECI-BA 28.140. "
                   "Imóveis de alto padrão para venda e locação, com atendimento pessoal."),
        corpo=corpo, corretor=corretor, imoveis=imoveis,
        ativo="index.html")


def pagina_catalogo(corretor: dict, imoveis: list[dict]) -> str:
    cards = "".join(card(i, corretor, numero=n, atraso=min(n - 1, 5) * 70)
                    for n, i in enumerate(imoveis, 1))

    def opcoes(chave: str) -> str:
        vistos = sorted({str(i[chave]) for i in imoveis})
        return "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in vistos)

    corpo = f"""
<section class="cabeca-pagina">
  <div class="wrap">
    <h1>Imóveis disponíveis</h1>
    <p>Venda e locação em {e(corretor['atuacao'])}. Todos com preço à vista na tela —
       você sabe se cabe antes de me chamar.</p>
  </div>
</section>

<section class="secao">
  <div class="wrap">
    <form class="filtros" id="filtros" aria-label="Filtrar imóveis">
      <label>Operação
        <select name="operacao">
          <option value="">Todas</option>
          <option value="venda">Venda</option>
          <option value="locacao">Locação</option>
        </select>
      </label>
      <label>Tipo
        <select name="tipo"><option value="">Todos</option>{opcoes('tipo')}</select>
      </label>
      <label>Bairro
        <select name="bairro"><option value="">Todos</option>{opcoes('bairro')}</select>
      </label>
      <label>Quartos
        <select name="quartos">
          <option value="">Qualquer</option>
          <option value="2">2 ou mais</option>
          <option value="3">3 ou mais</option>
          <option value="4">4 ou mais</option>
        </select>
      </label>
      <label>Ordenar
        <select name="ordem">
          <option value="destaque">Relevância</option>
          <option value="menor">Menor preço</option>
          <option value="maior">Maior preço</option>
        </select>
      </label>
      <button type="button" class="btn btn-limpar" id="limpar">Limpar</button>
    </form>

    <p class="contagem" id="contagem" aria-live="polite"></p>
    <div class="grade-cards" id="lista">{cards}</div>
    <p class="vazio" id="vazio" hidden>Nenhum imóvel com esses filtros.
       <button type="button" class="link-botao" id="limpar2">Limpar filtros</button>
       ou me chame no WhatsApp: eu procuro na carteira e fora dela.</p>
  </div>
</section>
"""
    return pagina(
        titulo="Imóveis à venda e para locação — Igor Santiago Imóveis",
        descricao="Catálogo de imóveis de alto padrão em Feira de Santana, com preço visível.",
        corpo=corpo, corretor=corretor, imoveis=imoveis,
        ativo="imoveis.html")


def pagina_imovel(corretor: dict, imovel: dict, imoveis: list[dict]) -> str:
    galeria = "".join(foto_placeholder(f"{imovel['titulo']} — foto {n}")
                      for n in range(1, 5))
    linhas_spec = "".join(
        f'<div class="spec"><dt>{e(k)}</dt><dd>{e(v)}</dd></div>' for k, v in specs(imovel))
    texto = "".join(f"<p>{e(p)}</p>" for p in imovel["descricao"])
    destaques = "".join(f"<li>{e(d)}</li>" for d in imovel["destaques"])
    duvidas = "".join(
        f'<details class="duvida"><summary>{e(d["pergunta"])}</summary>'
        f'<p>{e(d["resposta"])}</p></details>' for d in imovel["duvidas"])
    operacao = "Locação" if imovel["operacao"] == "locacao" else "Venda"
    reservado = ('<p class="aviso-reservado">Este imóvel está com proposta em análise. '
                 'Posso registrar seu interesse como segunda opção.</p>'
                 if imovel.get("situacao") == "reservado" else "")

    corpo = f"""
<nav class="migalha wrap" aria-label="Você está em">
  <a href="../index.html">Início</a> › <a href="../imoveis.html">Imóveis</a> ›
  <span>{e(imovel['bairro'])}</span>
</nav>

<section class="imovel-topo">
  <div class="wrap imovel-grade">
    <div class="imovel-galeria">{galeria}</div>
    <aside class="imovel-painel">
      <span class="selo selo-op">{operacao}</span>
      <p class="imovel-preco">{preco_rotulo(imovel)}</p>
      <h1>{e(imovel['titulo'])}</h1>
      <p class="imovel-local">{e(imovel['bairro'])} · {e(imovel['cidade'])}</p>
      {reservado}
      <a class="btn btn-wa btn-largo" target="_blank" rel="noopener"
         href="{e(wa_imovel(corretor, imovel))}">Falar sobre este imóvel</a>
      <p class="painel-creci">{e(corretor['nome_pessoa'])} ·
         {e(corretor['titulo_profissional'])} · <strong>{e(corretor['creci'])}</strong></p>
    </aside>
  </div>
</section>

<section class="secao">
  <div class="wrap imovel-conteudo">
    <div class="imovel-texto">
      <h2>Sobre o imóvel</h2>
      {texto}
      <h2>Destaques</h2>
      <ul class="lista-destaques">{destaques}</ul>
    </div>
    <div class="imovel-specs">
      <h2>Ficha técnica</h2>
      <dl class="specs-grade">{linhas_spec}</dl>
      <p class="mini">Medidas e valores conferidos na documentação antes de qualquer
         proposta. Nada aqui substitui a certidão de matrícula, que eu levo na visita.</p>
    </div>
  </div>
</section>

<section class="secao secao-alt">
  <div class="wrap">
    <h2>Dúvidas comuns sobre este imóvel</h2>
    <p class="sub">Respondidas antes de você perguntar, para a conversa começar adiantada.</p>
    <div class="duvidas">{duvidas}</div>
    <p class="duvidas-cta">Ficou outra dúvida?
      <a href="{e(wa_imovel(corretor, imovel))}" target="_blank" rel="noopener">Me pergunte
      no WhatsApp</a> — respondo eu mesmo.</p>
  </div>
</section>
"""
    return pagina(
        titulo=f"{imovel['titulo']} — {preco_texto(imovel)} | Igor Santiago Imóveis",
        descricao=(f"{imovel['titulo']}. {resumo(imovel)}. {preco_texto(imovel)}. "
                   f"{corretor['creci']}."),
        corpo=corpo, corretor=corretor, imoveis=imoveis,
        ativo="imoveis.html", prefixo="../",
        mensagem_wa=(f"Olá, Igor. Vi no seu site o imóvel \"{imovel['titulo']}\" "
                     f"e gostaria de mais informações."))


def pagina_sobre(corretor: dict, imoveis: list[dict]) -> str:
    provas = "".join(
        f'<div class="prova"><h3>{e(p["titulo"])}</h3><p>{e(p["texto"])}</p></div>'
        for p in corretor["provas"])
    bio = bio_ou_aviso(
        corretor, "bio_longa",
        "[bio longa — Igor informar: como começou na corretagem, quantos anos de mercado, "
        "o que os 2 anos nos Estados Unidos mudaram no seu jeito de atender, e o tipo de "
        "cliente que você atende hoje]")

    corpo = f"""
<section class="cabeca-pagina">
  <div class="wrap">
    <h1>Sobre o corretor</h1>
    <p>Antes do imóvel, quem vai conduzir o negócio.</p>
  </div>
</section>

<section class="secao">
  <div class="wrap sobre-grade">
    <div class="sobre-foto">
      {foto_placeholder('Retrato de Igor Santiago', 'aspect-3-4')}
      <p class="mini centro">Foto de Igor — pendente</p>
    </div>
    <div class="sobre-texto">
      <h2>{e(corretor['nome_pessoa'])}</h2>
      <p class="sobre-credencial">{e(corretor['titulo_profissional'])} ·
         <strong>{e(corretor['creci'])}</strong> · {anos_mercado(corretor)}</p>
      <p class="sobre-bio">{bio}</p>
      <h3>Como eu trabalho</h3>
      <ul class="lista-destaques">
        <li>Você fala comigo do primeiro contato à escritura. Não passo você adiante.</li>
        <li>Preço na tela e custo mensal real (condomínio e IPTU) antes da visita.</li>
        <li>Matrícula e certidões conferidas antes de qualquer proposta ser apresentada.</li>
        <li>O que eu não sei, eu digo que não sei e vou verificar.</li>
      </ul>
      <a class="btn btn-wa" target="_blank" rel="noopener"
         href="{e(wa_link(corretor, corretor['mensagem_whatsapp_geral']))}">Falar no WhatsApp</a>
    </div>
  </div>
</section>

<section class="faixa-provas">
  <div class="wrap provas-grade">{provas}</div>
</section>
"""
    return pagina(
        titulo="Sobre Igor Santiago — Corretor de Imóveis, CRECI-BA 28.140",
        descricao=("Igor Santiago, corretor de imóveis em Feira de Santana, "
                   "CRECI-BA 28.140. Atendimento pessoal em imóveis de alto padrão."),
        corpo=corpo, corretor=corretor, imoveis=imoveis, ativo="sobre.html")


def pagina_vender(corretor: dict, imoveis: list[dict]) -> str:
    wa = e(wa_link(corretor, corretor["mensagem_whatsapp_captacao"]))
    passos = [
        ("Você me manda o imóvel",
         "Endereço, metragem, quartos, vagas e o que já tem de documentação. "
         "Pode ser por WhatsApp, em mensagem de voz mesmo."),
        ("Eu levanto os comparáveis",
         "Imóveis parecidos no mesmo bairro, o que pediram e o que de fato saiu. "
         "Ajusto por conservação, andar, vaga e posição."),
        ("Você recebe a avaliação por escrito",
         "Com a faixa de preço, o raciocínio por trás dela e o tempo estimado de venda. "
         "Não é laudo oficial de avaliação — é análise de mercado para decidir o preço."),
        ("Você decide",
         "Se quiser seguir comigo, fechamos a captação. Se não quiser, a avaliação é sua "
         "do mesmo jeito."),
    ]
    lista = "".join(
        f'<li class="passo"><span class="passo-num">{n}</span>'
        f'<div><h3>{e(t)}</h3><p>{e(d)}</p></div></li>'
        for n, (t, d) in enumerate(passos, 1))

    corpo = f"""
<section class="cabeca-pagina cabeca-escura">
  <div class="wrap">
    <h1>Vender seu imóvel</h1>
    <p>Avaliação de mercado com o raciocínio na mesa. Preço inflado não vende — só faz o
       imóvel envelhecer no anúncio e perder valor de negociação.</p>
    <a class="btn btn-wa" href="{wa}" target="_blank" rel="noopener">Pedir avaliação</a>
  </div>
</section>

<section class="secao">
  <div class="wrap">
    <h2>Como funciona</h2>
    <ol class="passos">{lista}</ol>
  </div>
</section>

<section class="secao secao-alt">
  <div class="wrap">
    <h2>O que eu não faço</h2>
    <ul class="lista-destaques lista-nao">
      <li>Não prometo preço acima do mercado para conseguir a exclusividade.</li>
      <li>Não anuncio imóvel sem a documentação conferida.</li>
      <li>Não publico foto editada que mude a percepção de tamanho, luz ou estado do imóvel.
          Quando há edição, ela vem rotulada.</li>
      <li>Não repasso seus dados para lista de terceiros.</li>
    </ul>
    <a class="btn btn-principal" href="{wa}" target="_blank" rel="noopener">
      Falar sobre meu imóvel</a>
  </div>
</section>
"""
    return pagina(
        titulo="Vender meu imóvel — avaliação de mercado | Igor Santiago Imóveis",
        descricao=("Avaliação de mercado do seu imóvel em Feira de Santana, com "
                   "comparáveis reais do bairro. CRECI-BA 28.140."),
        corpo=corpo, corretor=corretor, imoveis=imoveis, ativo="vender.html",
        mensagem_wa=corretor["mensagem_whatsapp_captacao"])


def pagina_privacidade(corretor: dict, imoveis: list[dict]) -> str:
    corpo = f"""
<section class="cabeca-pagina">
  <div class="wrap">
    <h1>Aviso de privacidade</h1>
    <p class="mini">Rascunho — aguarda revisão jurídica e aprovação de Igor antes de o
       site ir ao ar.</p>
  </div>
</section>

<section class="secao">
  <div class="wrap texto-legal">
    <h2>Quem trata os seus dados</h2>
    <p>{e(corretor['nome_pessoa'])}, {e(corretor['titulo_profissional'])},
       {e(corretor['creci'])}, atuando em {e(corretor['atuacao'])}.
       Contato: {e(corretor['whatsapp_exibicao'])}.</p>

    <h2>Quais dados são coletados</h2>
    <p>Este site não tem formulário e não coleta dados por conta própria. O contato
       acontece pelo WhatsApp, por iniciativa sua. A partir daí, ficam registrados o
       nome, o telefone e as informações que você mesmo enviar sobre o imóvel que
       procura ou que quer vender.</p>

    <h2>Para que os dados são usados</h2>
    <p>Exclusivamente para atender ao seu contato: entender o que você procura, indicar
       imóveis, agendar visita e conduzir a negociação. A base legal é a execução de
       procedimentos preliminares a contrato, a seu pedido (art. 7º, V, da LGPD).</p>

    <h2>Compartilhamento</h2>
    <p>Seus dados são compartilhados apenas com quem for necessário para a negociação que
       você mesmo pediu: proprietário do imóvel, cartório, banco ou administradora de
       condomínio. Não há venda de dados, não há repasse para lista de terceiros e não há
       disparo de mensagem em massa.</p>

    <h2>Por quanto tempo</h2>
    <p>Contato que não avança é descartado em até 12 meses. Dados de negociação concluída
       são mantidos pelo prazo legal aplicável ao contrato.</p>

    <h2>Seus direitos</h2>
    <p>Você pode pedir a qualquer momento o acesso, a correção ou a exclusão dos seus
       dados, além de pedir para não ser mais contatado. Basta escrever no mesmo WhatsApp
       — o pedido é atendido sem que você precise justificar.</p>

    <h2>Sobre as imagens dos imóveis</h2>
    <p>Fotos podem receber ajuste de exposição, nitidez e correção de perspectiva. Quando
       a edição for além disso, a imagem vem rotulada como editada digitalmente e a
       original fica disponível a pedido. Não são usados recursos que alterem a percepção
       de tamanho, de luz ou do estado de conservação do imóvel.</p>
  </div>
</section>
"""
    return pagina(
        titulo="Aviso de privacidade — Igor Santiago Imóveis",
        descricao="Como os dados de quem entra em contato são tratados. LGPD.",
        corpo=corpo, corretor=corretor, imoveis=imoveis, ativo="privacidade.html")


def pagina_404(corretor: dict, imoveis: list[dict]) -> str:
    corpo = """
<section class="cabeca-pagina">
  <div class="wrap">
    <h1>Página não encontrada</h1>
    <p>O endereço não existe ou o imóvel saiu do catálogo.</p>
    <a class="btn btn-principal" href="imoveis.html">Ver imóveis disponíveis</a>
  </div>
</section>
"""
    return pagina(titulo="Página não encontrada — Igor Santiago Imóveis",
                  descricao="Página não encontrada.", corpo=corpo,
                  corretor=corretor, imoveis=imoveis, ativo="")


# --------------------------------------------------------------------------
# arquivos auxiliares
# --------------------------------------------------------------------------

def escrever_auxiliares(corretor: dict, imoveis: list[dict], publicar: bool) -> None:
    base = corretor["site_url"].rstrip("/")

    # Enquanto houver demo, robots.txt proibe tudo. So o build --publicar libera.
    if publicar:
        robots = f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n"
    else:
        robots = "User-agent: *\nDisallow: /\n"
    (SAIDA / "robots.txt").write_text(robots, encoding="utf-8")

    urls = ["index.html", "imoveis.html", "sobre.html", "vender.html", "privacidade.html"]
    urls += [f"imovel/{i['slug']}.html" for i in imoveis]
    corpo = "".join(f"  <url><loc>{base}/{u}</loc></url>\n" for u in urls)
    (SAIDA / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{corpo}</urlset>\n", encoding="utf-8")

    # netlify.toml e' arquivo de fonte na raiz do repositorio (Netlify le antes
    # de rodar o build), nao artefato gerado. Nao recriar aqui.


# --------------------------------------------------------------------------
# verificacao
# --------------------------------------------------------------------------

def pendencias(corretor: dict, imoveis: list[dict]) -> list[str]:
    faltas = [f"corretor.json → {chave}" for chave, valor in corretor.items()
              if valor == PENDENTE]
    if not corretor.get("creci_confirmado_por_igor"):
        faltas.append("corretor.json → creci_confirmado_por_igor (Igor precisa confirmar "
                      f"que a grafia \"{corretor['creci']}\" bate com a carteirinha)")
    for imovel in imoveis:
        for campo in OBRIGATORIOS:
            if not imovel.get(campo):
                faltas.append(f"{imovel['_arquivo'].parent.name}/ficha.md → {campo}")
        if not imovel["duvidas"]:
            faltas.append(f"{imovel['_arquivo'].parent.name}/ficha.md → Dúvidas comuns (IS-5)")
        pasta_fotos = imovel["_arquivo"].parent / "fotos-tratadas"
        if not pasta_fotos.is_dir() or not any(pasta_fotos.iterdir()):
            faltas.append(f"{imovel['_arquivo'].parent.name}/fotos-tratadas/ → vazia")
    return faltas


def main(argv: list[str]) -> int:
    checar = "--check" in argv
    publicar = "--publicar" in argv

    corretor = ler_corretor()
    imoveis = ler_imoveis()
    if not imoveis:
        print("ERRO: nenhum imóvel em dados/imoveis/", file=sys.stderr)
        return 1

    demos = [i["slug"] for i in imoveis if i.get("demo")]

    if checar:
        faltas = pendencias(corretor, imoveis)
        print(f"{len(imoveis)} imóveis lidos ({len(demos)} de demonstração).")
        if demos:
            print("Demonstração: " + ", ".join(demos))
        print(f"\n{len(faltas)} pendência(s):")
        for f in faltas:
            print("  - " + f)
        return 0

    if publicar and demos:
        print("RECUSADO: build de publicação com imóvel de demonstração.", file=sys.stderr)
        print("Imóveis marcados demo: true — " + ", ".join(demos), file=sys.stderr)
        print("Anunciar imóvel que não existe é risco de CDC e de ética CRECI.",
              file=sys.stderr)
        print("Remova as fichas demo ou marque demo: false antes de publicar.",
              file=sys.stderr)
        return 2

    if SAIDA.exists():
        shutil.rmtree(SAIDA)
    (SAIDA / "imovel").mkdir(parents=True)

    shutil.copytree(ASSETS, SAIDA / "assets")

    (SAIDA / "index.html").write_text(pagina_home(corretor, imoveis), encoding="utf-8")
    (SAIDA / "imoveis.html").write_text(pagina_catalogo(corretor, imoveis), encoding="utf-8")
    (SAIDA / "sobre.html").write_text(pagina_sobre(corretor, imoveis), encoding="utf-8")
    (SAIDA / "vender.html").write_text(pagina_vender(corretor, imoveis), encoding="utf-8")
    (SAIDA / "privacidade.html").write_text(pagina_privacidade(corretor, imoveis),
                                            encoding="utf-8")
    (SAIDA / "404.html").write_text(pagina_404(corretor, imoveis), encoding="utf-8")
    for imovel in imoveis:
        (SAIDA / "imovel" / f"{imovel['slug']}.html").write_text(
            pagina_imovel(corretor, imovel, imoveis), encoding="utf-8")

    escrever_auxiliares(corretor, imoveis, publicar)

    faltas = pendencias(corretor, imoveis)
    print(f"OK -> {SAIDA / 'index.html'}")
    print(f"{len(imoveis)} imóveis · {len(imoveis) + 6} páginas")
    if demos:
        print(f"AVISO: {len(demos)} imóvel(is) de demonstração no build. "
              "robots.txt está bloqueando tudo. Não publicar.")
    if faltas:
        print(f"{len(faltas)} pendência(s) — rode --check para a lista.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
