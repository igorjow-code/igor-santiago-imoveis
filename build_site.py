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
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
DADOS = ROOT / "dados"
ASSETS = ROOT / "assets"
SAIDA = ROOT / "publico"

PENDENTE = "__PENDENTE_IGOR__"

# Centro aproximado de cada bairro (não o endereço exato do imóvel — por
# padrão de privacidade do setor, a localização pública é por bairro).
# Geocodificado uma vez via Nominatim/OpenStreetMap (12/09/2026); bairro sem
# entrada aqui simplesmente não mostra mapa, em vez de adivinhar coordenada.
COORDENADAS_BAIRRO = {
    # Nominatim, 17/09/2026: node 1778006256, Centro (suburb).
    "Centro|Feira de Santana": (-12.2565682, -38.9648737),
    "Santa Mônica|Feira de Santana": (-12.2615379, -38.9385258),
    "Muchila|Feira de Santana": (-12.2705727, -38.9684344),
    "Sim|Feira de Santana": (-12.2512799, -38.9260106),
    "Ponto Central|Feira de Santana": (-12.2526425, -38.9520510),
    "Brasília|Feira de Santana": (-12.2666487, -38.9505934),
}

# Campos que toda ficha precisa ter para virar pagina.
OBRIGATORIOS = ("slug", "titulo", "operacao", "finalidade", "tipo", "bairro", "cidade", "preco")
NUMERICOS = ("area", "area_terreno", "quartos", "suites", "vagas",
             "preco", "condominio", "iptu")
BOOLEANOS = ("destaque", "demo")
ALIASES = {"aluguel": "preco", "valor_aluguel": "preco", "taxa_condominio": "condominio"}
DATAS = ("disponivel_a_partir",)
LISTAS = ("garantias", "contas_inclusas")
ENUMS = {"operacao": {"locacao", "venda"},
         "finalidade": {"residencial", "comercial"},
         "situacao": {"disponivel", "reservado", "alugado", "vendido"},
         "mobiliado": {"sim", "nao", "semi"},
         "aceita_pet": {"sim", "nao", "consultar"}}


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

    origens = {}
    for alias, chave in ALIASES.items():
        if alias in dados:
            if chave in dados and dados[chave] != dados[alias]:
                raise ValueError(f"{caminho}: campos '{alias}' e '{chave}' conflitantes")
            dados[chave] = dados.pop(alias)
            origens[chave] = alias
    _coerce(dados, caminho, origens)
    if not dados.get("finalidade"):
        dados["finalidade"] = ("comercial" if dados.get("tipo") in
                               {"Sala comercial", "Loja", "Ponto comercial", "Galpão"}
                               else "residencial")

    dados.update(_secoes(corpo))
    dados["_arquivo"] = caminho
    return dados


def _coerce(dados: dict, caminho: Path, origens: dict | None = None) -> None:
    for chave in NUMERICOS:
        valor = dados.get(chave, "")
        if valor != "":
            try:
                dados[chave] = int(valor)
            except (ValueError, TypeError) as exc:
                nome = (origens or {}).get(chave, chave)
                raise ValueError(f"{caminho}: campo '{nome}' = {valor!r} não é número inteiro") from exc
        elif chave in dados:
            dados.pop(chave)
    for chave in BOOLEANOS:
        dados[chave] = str(dados.get(chave, "false")).lower() == "true"
    for chave in DATAS:
        valor = dados.get(chave)
        if valor:
            try:
                dados[chave] = date.fromisoformat(valor)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{caminho}: campo '{chave}' = {valor!r} não é data ISO válida") from exc
    for chave in LISTAS:
        dados[chave] = [v.strip() for v in dados.get(chave, "").split(",") if v.strip()]


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
    imoveis.sort(key=lambda i: (i.get("operacao") != "locacao",
                               i.get("preco", 0) if i.get("operacao") == "locacao"
                               else -i.get("preco", 0)))
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
        return 'Aluguel ' + moeda(imovel["preco"]) + '<span class="por-mes">/mês</span>'
    return moeda(imovel["preco"])


def wa_link(corretor: dict, mensagem: str) -> str:
    return f"https://wa.me/{corretor['whatsapp_e164']}?text={quote(mensagem)}"


def wa_imovel(corretor: dict, imovel: dict) -> str:
    msg = (f"Olá, Igor. Vi no seu site o imóvel \"{imovel['titulo']}\" "
           f"({preco_texto(imovel)}) e gostaria de agendar uma visita.")
    return wa_link(corretor, msg)


def preco_texto(imovel: dict) -> str:
    base = moeda(imovel["preco"])
    return "Aluguel " + base + "/mês" if imovel["operacao"] == "locacao" else base


def custo_mensal(imovel: dict) -> int:
    # Encargos incluídos no aluguel não podem ser cobrados duas vezes.
    inclusas = imovel.get("contas_inclusas", [])
    condominio = 0 if "condominio" in inclusas else imovel.get("condominio", 0)
    iptu = 0 if "iptu" in inclusas else imovel.get("iptu", 0) // 12
    return imovel["preco"] + condominio + iptu


def data_br(d: date) -> str:
    meses = ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
    return f"{'1º' if d.day == 1 else d.day} de {meses[d.month - 1]}"


def disponibilidade(imovel: dict, hoje: date | None = None) -> str:
    d = imovel.get("disponivel_a_partir")
    if not d or d < (hoje or date.today()) or imovel.get("situacao") in {"alugado", "vendido"}:
        return ""
    return f"Disponível a partir de {data_br(d)} de {d.year}"


def specs(imovel: dict) -> list[tuple[str, str]]:
    itens: list[tuple[str, str]] = []
    if imovel.get("area"):
        itens.append(("Área construída", f"{imovel['area']} m²"))
    if imovel.get("area_terreno"):
        itens.append(("Terreno", f"{imovel['area_terreno']} m²"))
    if imovel.get("quartos") and imovel.get("finalidade") != "comercial":
        itens.append(("Quartos", str(imovel["quartos"])))
    if imovel.get("suites") and imovel.get("finalidade") != "comercial":
        itens.append(("Suítes", str(imovel["suites"])))
    if imovel.get("vagas"):
        itens.append(("Vagas", str(imovel["vagas"])))
    if imovel.get("condominio"):
        itens.append(("Condomínio", moeda(imovel["condominio"]) + "/mês"))
    if imovel.get("iptu"):
        itens.append(("IPTU", moeda(imovel["iptu"]) + "/ano"))
    rotulos = {"sim": "Sim", "nao": "Não", "semi": "Semimobiliado", "consultar": "Consultar"}
    for chave, rotulo in (("mobiliado", "Mobiliado"), ("aceita_pet", "Aceita pet")):
        if imovel.get(chave):
            itens.append((rotulo, rotulos.get(imovel[chave], imovel[chave])))
    nomes = {"seguro-fianca": "seguro-fiança", "caucao": "caução", "agua": "água"}
    for chave, rotulo in (("garantias", "Garantias a consultar"), ("contas_inclusas", "Contas inclusas")):
        if imovel.get(chave):
            itens.append((rotulo, ", ".join(nomes.get(v, v) for v in imovel[chave])))
    return itens


def resumo(imovel: dict) -> str:
    partes = []
    if imovel.get("area"):
        partes.append(f"{imovel['area']} m²")
    if imovel.get("quartos") and imovel.get("finalidade") != "comercial":
        partes.append(f"{imovel['quartos']} quartos")
    if imovel.get("suites") and imovel.get("finalidade") != "comercial":
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


def marca_simbolo(prefixo: str = "") -> str:
    return f'<img class="marca-simbolo" src="{prefixo}assets/simbolo-64.png" alt="" width="28" height="32" />'


def cabecalho(corretor: dict, ativo: str, prefixo: str) -> str:
    itens = [("index.html", "Início"), ("imoveis.html", "Alugar"),
             ("alugar-sala-comercial.html", "Salas comerciais"),
             ("administracao.html", "Administração"), ("sobre.html", "Sobre")]
    partes = []
    for href, rotulo in itens:
        classe = ' class="ativo"' if href == ativo else ""
        partes.append(f'<a href="{prefixo}{href}"{classe}>{rotulo}</a>')
    links = "".join(partes)
    return f"""<header class="topo">
  <div class="wrap topo-linha">
    <a class="marca" href="{prefixo}index.html">
      {marca_simbolo(prefixo)}
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
        {marca_simbolo(prefixo)}
        Igor Santiago
      </p>
      <p class="rodape-pos">{e(corretor['posicionamento'])}</p>
    </div>
    <nav class="rodape-links" aria-label="Rodapé">
      <a href="{prefixo}imoveis.html">Imóveis para alugar</a>
      <a href="{prefixo}alugar-residencial.html">Aluguel residencial</a>
      <a href="{prefixo}administracao.html">Administração</a>
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
            f'target="_blank" rel="noopener">Agendar pelo WhatsApp</a>')


def pagina(titulo: str, descricao: str, corpo: str, corretor: dict,
           imoveis: list[dict], ativo: str, prefixo: str = "",
           mensagem_wa: str | None = None, extra_js: str = "",
           publicar: bool = False, jsonld: str = "", no_pagina: str | None = None) -> str:
    mensagem_wa = mensagem_wa or corretor["mensagem_whatsapp_geral"]
    no_pagina = no_pagina or ativo or "404.html"
    indexar = publicar and no_pagina not in {"obrigado.html", "404.html"}
    canonical = corretor["site_url"].rstrip("/") + "/" + no_pagina
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao)}" />
<meta name="theme-color" content="#0a0a0a" />
<meta name="robots" content="{'index, follow' if indexar else 'noindex, nofollow'}" />
<link rel="canonical" href="{e(canonical)}" />
{jsonld}
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
    custo = (f'<p class="custo-total">Custo mensal total: {moeda(custo_mensal(imovel))}/mês</p>'
             '<p class="mini">Aluguel + encargos informados; IPTU em 12 meses. Consumos à parte, salvo inclusos.</p>'
             if imovel['operacao'] == 'locacao' else '')
    quando = disponibilidade(imovel)
    quando = f'<p class="disponivel-em">{e(quando)}</p>' if quando else ''
    return f"""<article class="card" data-operacao="{e(imovel['operacao'])}"
         data-tipo="{e(imovel['tipo'])}" data-bairro="{e(imovel['bairro'])}" data-finalidade="{e(imovel['finalidade'])}"
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
      {custo}{quando}
      <h3 class="card-titulo">{e(imovel['titulo'])}</h3>
      <p class="card-local">{e(imovel['bairro'])} · {e(imovel['cidade'])}</p>
      <p class="card-specs">{e(resumo(imovel))}</p>
    </div>
  </a>
  <a class="card-wa" href="{e(wa_imovel(corretor, imovel))}" target="_blank" rel="noopener">
    Agendar visita pelo WhatsApp
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
    locacao = imovel.get("operacao") == "locacao"
    linhas = [("Aluguel" if locacao else "Preço", moeda(imovel["preco"]) + ("/mês" if locacao else ""))]
    if imovel.get("condominio"):
        linhas.append(("Condomínio", "Incluso no aluguel" if locacao and "condominio" in imovel.get("contas_inclusas", []) else moeda(imovel["condominio"]) + "/mês"))
    if imovel.get("iptu"):
        linhas.append(("IPTU", "Incluso no aluguel" if locacao and "iptu" in imovel.get("contas_inclusas", []) else moeda(imovel["iptu"]) + "/ano"))
    if len(linhas) == 1:
        linhas.append(("Condomínio e IPTU", "valores não informados — consultar"))
    if locacao:
        linhas.append(("Custo mensal total", f'<strong class="custo-total">{moeda(custo_mensal(imovel))}/mês</strong>'))
        linhas.append(("Composição", "Aluguel + encargos informados; IPTU rateado em 12 meses, arredondado para baixo. Consumos à parte, salvo contas inclusas."))
        # O total encerra o recibo; a observação vem antes dele.
        linhas[-2], linhas[-1] = linhas[-1], linhas[-2]
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


def recibo_ficha(corretor: dict, imovel: dict) -> str:
    """Painel de preço da ficha — mesmo mecanismo do recibo() da Home (IS-22),
    com o botão de WhatsApp e o CRECI, que a Home não precisa mostrar."""
    operacao = "Locação" if imovel["operacao"] == "locacao" else "Venda"
    itens = "".join(
        f'<div class="recibo-linha" {reveal(n + 1, 90)}><dt>{e(rotulo)}</dt>'
        f'<dd>{valor}</dd></div>'
        for n, (rotulo, valor) in enumerate(linhas_recibo(imovel)))
    reservado = ('<p class="aviso-reservado">Proposta em análise — posso registrar '
                 'seu interesse como segunda opção.</p>'
                 if imovel.get("situacao") == "reservado" else "")
    return f"""<aside class="recibo recibo-ficha" data-reveal style="--atraso:0ms">
  <span class="selo selo-op" {reveal(0)}>{operacao}</span>
  <h1 {reveal(1)}>{e(imovel['titulo'])}</h1>
  <p class="recibo-local" {reveal(2)}>{e(imovel['bairro'])} · {e(imovel['cidade'])}</p>
  <dl class="recibo-linhas">{itens}</dl>
  {reservado}
  <a class="btn btn-wa btn-largo" {reveal(5, 90)} target="_blank" rel="noopener"
     href="{e(wa_imovel(corretor, imovel))}">Falar sobre este imóvel</a>
  <p class="painel-creci" {reveal(6, 90)}>{e(corretor['nome_pessoa'])} ·
     {e(corretor['titulo_profissional'])} · <strong>{e(corretor['creci'])}</strong></p>
</aside>"""


def mapa_bairro(imovel: dict) -> str:
    chave = f"{imovel['bairro']}|{imovel['cidade']}"
    coordenada = COORDENADAS_BAIRRO.get(chave)
    if not coordenada:
        return ""
    lat, lon = coordenada
    delta = 0.012
    bbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"
    embed = (f"https://www.openstreetmap.org/export/embed.html"
             f"?bbox={bbox}&layer=mapnik&marker={lat},{lon}")
    rota = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}"
    return f"""<div class="mapa-card">
  <h2>Localização</h2>
  <div class="mapa-frame">
    <iframe src="{e(embed)}" loading="lazy" title="Mapa de {e(imovel['bairro'])}, {e(imovel['cidade'])}"
            referrerpolicy="no-referrer-when-downgrade"></iframe>
  </div>
  <p class="mapa-legenda">{e(imovel['bairro'])} · {e(imovel['cidade'])} — localização
     aproximada do bairro. <a href="{e(rota)}" target="_blank" rel="noopener">Ver rota</a></p>
</div>"""


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


def secao_dor() -> str:
    return '''<section class="secao"><div class="wrap">
<h2>O anúncio cabe no orçamento. E a conta completa?</h2>
<p>Buscar imóvel cansa quando falta resposta, o anúncio já saiu da carteira ou os encargos
só aparecem depois. Aqui você compara aluguel, condomínio e IPTU antes de agendar.</p>
</div></section>'''


def secao_passos(passos: list[tuple[str, str]] | None = None) -> str:
    passos = passos or [
        ("Você conta o que procura", "Moradia ou negócio, bairro, faixa de aluguel e quando precisa mudar."),
        ("Conferimos o custo e as condições", "Aluguel, encargos, garantia e documentos necessários antes da visita."),
        ("Agendamos a visita", "Combinamos um horário para conhecer o imóvel e tirar as dúvidas."),
        ("Proposta, análise e contrato", "Se fizer sentido, seguimos para análise, vistoria e assinatura. Sem promessa de aprovação.")]
    lista = ''.join(f'<li class="passo"><span class="passo-num">{n}</span>'
                    f'<div><h3>{e(t)}</h3><p>{e(d)}</p></div></li>'
                    for n, (t, d) in enumerate(passos, 1))
    return f'<section class="secao"><div class="wrap"><h2>Como funciona</h2><ol class="passos">{lista}</ol></div></section>'


def faq_global(corretor: dict) -> list[dict]:
    return [
        {"pergunta": "Preciso de fiador?", "resposta": "Depende do imóvel. A ficha apresenta as alternativas informadas, como fiador, seguro-fiança ou caução. Confirmamos a garantia e seu custo antes da proposta."},
        {"pergunta": "É meu primeiro aluguel e não tenho comprovação tradicional. Posso conversar?", "resposta": "Sim. Conte como é sua renda para verificarmos quais documentos e alternativas podem ser analisados. Não prometo aprovação."},
        {"pergunta": "Posso levar meu pet?", "resposta": "Consulte o campo de pet da ficha. Quando estiver como consultar, verifico as condições do imóvel antes da visita."},
        {"pergunta": "Posso procurar uma sala sem ter CNPJ ainda?", "resposta": "Sim. Podemos agendar uma conversa sobre o espaço e a atividade pretendida. A viabilidade do uso e os documentos precisam ser conferidos antes da contratação."},
        {"pergunta": "Há opções mobiliadas?", "resposta": "As fichas indicam se o imóvel é mobiliado, semimobiliado ou sem mobília. A relação de itens deve ser conferida na vistoria e no contrato."},
        {"pergunta": "Quem paga o quê além do aluguel?", "resposta": "O custo mensal mostrado soma aluguel, condomínio não incluso e IPTU anual dividido por 12, arredondado para baixo. Contas declaradas inclusas não são somadas novamente. Consumos e custos da garantia podem ser adicionais; confirmamos valores e responsabilidades no contrato."}]


def secao_objecoes(corretor: dict) -> str:
    itens = ''.join(f'<details class="duvida"><summary>{e(d["pergunta"])}</summary><p>{e(d["resposta"])}</p></details>' for d in faq_global(corretor))
    wa = e(wa_link(corretor, "Olá, Igor. Quero agendar uma conversa para tirar dúvidas sobre garantia e custos do aluguel."))
    return f'''<section class="secao secao-alt"><div class="wrap"><h2>Antes de alugar</h2>
<div class="duvidas">{itens}</div><p class="duvidas-cta"><a class="btn btn-wa" href="{wa}" target="_blank" rel="noopener">Agendar conversa sobre as condições</a></p></div></section>'''


def secao_prova(corretor: dict) -> str:
    provas = ''.join(f'<h3>{e(p["titulo"])}</h3><p>{e(p["texto"])}</p>' for p in corretor['provas'])
    return f'''<section class="secao"><div class="wrap sobre-grade">
<div class="sobre-foto">{foto_placeholder('Retrato de Igor Santiago', 'aspect-3-4')}</div>
<div class="sobre-texto"><h2>Quem acompanha você</h2><p>{bio_ou_aviso(corretor, 'bio_longa', 'Bio pendente')}</p>{provas}
<a class="link-seta" href="sobre.html">Sobre Igor Santiago</a></div></div></section>'''


def secao_nao_faco(corretor: dict) -> str:
    wa = e(wa_link(corretor, "Olá, Igor. Quero agendar uma conversa para conferir custos e documentos antes de visitar um imóvel."))
    return f'''<section class="secao"><div class="wrap"><h2>O que eu não faço</h2>
<ul class="lista-destaques lista-nao"><li>Não escondo encargos para o aluguel parecer menor.</li>
<li>Não prometo aprovação de cadastro ou garantia antes da análise.</li>
<li>Não altero fotos para mudar a percepção de tamanho ou estado do imóvel.</li>
<li>Não pressiono com prazo que não esteja informado na ficha.</li></ul>
<a class="btn btn-wa" href="{wa}" target="_blank" rel="noopener">Agendar e conferir as condições</a></div></section>'''


def formulario_lead(corretor: dict, publicar: bool) -> str:
    # B3/B5 não desaparecem apenas porque alguém passou --publicar.
    ativo = publicar and corretor.get('privacidade_revisada') is True and corretor.get('email') not in (None, '', PENDENTE)
    abertura = ('<form class="form-lead" name="quero-alugar" method="POST" data-netlify="true" netlify-honeypot="bot-field" action="/obrigado.html">'
                if ativo else '<div class="form-lead" role="group" aria-label="Formulário de interesse em prévia">')
    fim = '</form>' if ativo else '</div>'
    disabled = '' if ativo else ' disabled'
    opcoes = ['Sala comercial até R$ 2.000', 'Sala comercial R$ 2.000–3.000',
              'Apartamento ou casa até R$ 2.000', 'Apartamento ou casa R$ 2.000–3.000', 'Outro']
    options = ''.join(f'<option>{e(o)}</option>' for o in opcoes)
    return f'''<section class="secao" id="quero-alugar"><div class="wrap">
<h2>Conte o que você quer alugar</h2>{abertura}
<input type="hidden" name="form-name" value="quero-alugar"{disabled}>
<p class="escondido" aria-hidden="true"><label>Deixe este campo vazio<input name="bot-field" tabindex="-1" autocomplete="off"{disabled}></label></p>
<div class="form-campo"><label for="lead-nome">Nome</label><input id="lead-nome" name="nome" type="text" required autocomplete="name"{disabled}></div>
<div class="form-campo"><label for="lead-whatsapp">WhatsApp</label><input id="lead-whatsapp" name="whatsapp" type="tel" required inputmode="tel" autocomplete="tel" pattern="[+0-9\\(\\) .\\-]{{8,25}}"{disabled}></div>
<div class="form-campo"><label for="lead-procura">O que procura?</label><select id="lead-procura" name="procura" required{disabled}><option value="">Selecione</option>{options}</select></div>
<div class="consentimento"><input id="lead-consentimento" type="checkbox" name="consentimento" required{disabled}>
<label for="lead-consentimento">Autorizo Igor Santiago a me contatar por WhatsApp sobre imóveis para alugar. Meus dados não são repassados a terceiros para publicidade e posso pedir exclusão a qualquer momento.</label>
<a href="privacidade.html">Como meus dados são tratados</a></div>
<p>Resposta em até {e(corretor['resposta_prometida'])}, por mim mesmo.</p>
<button class="btn btn-principal" type="{'submit' if ativo else 'button'}"{disabled}>Pedir contato</button>
<p class="mini">{'Envio disponível após consentimento.' if ativo else 'Formulário ativo na publicação — após revisão de privacidade e configuração do e-mail.'}</p>
<p>{e(corretor['nome_pessoa'])} · {e(corretor['titulo_profissional'])} · {e(corretor['creci'])}</p>{fim}</div></section>'''


def pagina_obrigado(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
    texto = 'Obrigado pelo contato. Após o envio, respondo pelo WhatsApp em até ' + corretor['resposta_prometida'] + '.' if publicar else 'Página de confirmação em prévia. Nenhum dado foi enviado por este formulário.'
    corpo = f'<section class="secao"><div class="wrap"><h1>Contato sobre aluguel</h1><p>{e(texto)}</p><a class="btn btn-principal" href="imoveis.html">Ver imóveis para alugar</a></div></section>'
    return pagina('Contato — Igor Santiago Imóveis', 'Contato sobre aluguel.', corpo, corretor, imoveis, 'obrigado.html', publicar=publicar, jsonld=jsonld(corretor, imoveis, 'obrigado.html', []))


def pagina_segmento(corretor: dict, imoveis: list[dict], finalidade: str, publicar: bool = False) -> str:
    comercial = finalidade == 'comercial'
    nome = 'alugar-sala-comercial.html' if comercial else 'alugar-residencial.html'
    titulo = 'Sala ou ponto comercial para seu negócio' if comercial else 'Apartamento ou casa para morar'
    texto = ('Para abrir ou expandir seu negócio: confira metragem, custo mensal e viabilidade da atividade antes de contratar.' if comercial else 'Para seu primeiro aluguel ou uma mudança: confira custo mensal, mobília, pet e garantias antes da visita.')
    mensagem = corretor['mensagem_whatsapp_comercial'] if comercial else 'Olá, Igor. Quero agendar uma conversa para alugar um apartamento ou casa.'
    lista = [i for i in imoveis if i['operacao'] == 'locacao' and i['finalidade'] == finalidade and i.get('situacao') not in {'alugado', 'vendido'}]
    cards = ''.join(card(i, corretor) for i in lista)
    corpo = f'''<section class="cabeca-pagina"><div class="wrap"><h1>{titulo}</h1><p>{texto}</p>
<a class="btn btn-wa" href="{e(wa_link(corretor, mensagem))}" target="_blank" rel="noopener">Agendar pelo WhatsApp</a></div></section>
<section class="secao"><div class="wrap"><div class="grade-cards">{cards}</div>
<a class="link-seta" href="index.html#quero-alugar">Conte o que procura</a></div></section>{secao_passos()}{secao_objecoes(corretor)}'''
    return pagina(titulo + ' — Igor Santiago Imóveis', texto, corpo, corretor, imoveis, nome, mensagem_wa=mensagem, publicar=publicar, jsonld=jsonld(corretor, imoveis, nome, faq_global(corretor)))


def pagina_administracao(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
    msg = corretor['mensagem_whatsapp_administracao']
    corpo = f'''<section class="cabeca-pagina"><div class="wrap"><h1>Administração para quem tem imóvel</h1>
<p>Sou proprietário: quero organizar a locação e o acompanhamento do meu imóvel.</p>
<a class="btn btn-wa" href="{e(wa_link(corretor, msg))}" target="_blank" rel="noopener">Agendar conversa sobre administração</a></div></section>
<section class="secao"><div class="wrap"><h2>Definimos o serviço antes de começar</h2>
<p>Na conversa, levantamos a situação do imóvel e combinamos o escopo de acompanhamento, a prestação de contas e os honorários por escrito.</p>
<p>Seleção de interessados, contrato, vistoria e acompanhamento da locação entram na proposta conforme a necessidade. Não há promessa de renda garantida ou ausência de vacância.</p>
<p>O atendimento é comigo, Igor Santiago, {e(corretor['creci'])}.</p></div></section>'''
    return pagina('Administração de imóveis — Igor Santiago Imóveis', 'Administração de imóveis para proprietários em Feira de Santana.', corpo, corretor, imoveis, 'administracao.html', mensagem_wa=msg, publicar=publicar, jsonld=jsonld(corretor, imoveis, 'administracao.html', []))


def pagina_home(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
    destaques = [i for i in imoveis if i["operacao"] == "locacao" and i.get("situacao") not in {"alugado", "vendido"}][:3]
    cards = "".join(card(i, corretor, numero=n, atraso=(n - 1) * 90)
                    for n, i in enumerate(destaques, 1))
    corpo = f"""
<section class="hero">
  <img class="hero-marca-agua" src="assets/simbolo.png" alt="" aria-hidden="true" loading="lazy" />
  <div class="wrap hero-grade">
    <div class="hero-texto">
      <p class="sobrelinha" {reveal(0)}>{e(corretor['atuacao'])}</p>
      <h1 {reveal(1)}>Aluguel para morar ou abrir seu negócio, com o <span class="acento">custo mensal</span> na tela.</h1>
      <p class="faixa-preco">Aluguéis de {moeda(corretor['faixa_aluguel']['min'])} a {moeda(corretor['faixa_aluguel']['max'])}. Custo mensal total = aluguel + condomínio + IPTU mensalizado; contas inclusas não são cobradas novamente.</p>
      <p class="hero-sub" {reveal(2)}>{bio_ou_aviso(corretor, 'bio_curta',
        '[bio curta — Igor informar: uma frase sobre quem você é e como atende]')}</p>
      <div class="hero-assinatura" {reveal(3)}>
        <strong>{e(corretor['nome_pessoa'])}</strong>
        <span>{e(corretor['titulo_profissional'])} · {e(corretor['creci'])}</span>
        <span>{anos_mercado(corretor)}</span>
      </div>
      <div class="hero-botoes" {reveal(4)}>

        <a class="btn btn-wa" target="_blank" rel="noopener"
           href="{e(wa_link(corretor, corretor['mensagem_whatsapp_geral']))}">Agendar pelo WhatsApp</a>
        <a class="btn btn-claro" href="#quero-alugar">Conte o que procura</a>
      </div>
    </div>
    <div class="hero-foto" {reveal(2)}>
      {foto_placeholder('Retrato de Igor Santiago', 'aspect-3-4')}
      <span class="hero-selo-creci">{e(corretor['creci'])} · ativo</span>
      <p class="mini centro">Foto de Igor — pendente</p>
    </div>
  </div>
</section>

<div class="wrap"><p class="prova-imediata">{e(corretor['creci'])} · {anos_mercado(corretor)} · Feira de Santana</p></div>
{secao_dor()}
<section class="secao">
  <div class="wrap">
    <div class="secao-topo" {reveal(0)}>
      <h2>Imóveis para alugar</h2>
      <a class="link-seta" href="imoveis.html">Ver todos os imóveis</a>
    </div>
    <div class="grade-cards grade-cards--vitrine">{cards}</div>
  </div>
</section>

{secao_passos()}
{secao_objecoes(corretor)}
{secao_prova(corretor)}
{secao_nao_faco(corretor)}
{formulario_lead(corretor, publicar)}
<section class="secao"><div class="wrap"><h2>Vamos agendar o próximo passo?</h2>
<a class="btn btn-wa" href="{e(wa_link(corretor, 'Olá, Igor. Vi o custo mensal e quero agendar uma conversa para escolher meu aluguel.'))}" target="_blank" rel="noopener">Agendar pelo WhatsApp</a></div></section>
"""
    return pagina(
        titulo="Igor Santiago Imóveis — aluguel em Feira de Santana",
        descricao=("Corretor de imóveis em Feira de Santana, CRECI-BA 28.140. "
                   "Aluguel residencial e comercial, custo mensal visível e atendimento pessoal."),
        corpo=corpo, corretor=corretor, imoveis=imoveis,
        ativo="index.html", publicar=publicar,
        jsonld=jsonld(corretor, imoveis, "index.html", faq_global(corretor)))


def secao_mapa_bairros(imoveis: list[dict]) -> str:
    por_bairro: dict[str, list[dict]] = {}
    for i in imoveis:
        por_bairro.setdefault(f"{i['bairro']}|{i['cidade']}", []).append(i)

    cartoes = []
    for n, chave in enumerate(sorted(por_bairro)):
        coordenada = COORDENADAS_BAIRRO.get(chave)
        if not coordenada:
            continue
        lista = por_bairro[chave]
        bairro, cidade = lista[0]["bairro"], lista[0]["cidade"]
        lat, lon = coordenada
        delta = 0.012
        bbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"
        embed = (f"https://www.openstreetmap.org/export/embed.html"
                 f"?bbox={bbox}&layer=mapnik&marker={lat},{lon}")
        rotulo = "1 imóvel" if len(lista) == 1 else f"{len(lista)} imóveis"
        cartoes.append(f"""<a class="bairro-card" href="#lista" data-bairro-card="{e(bairro)}" {reveal(n, 80)}>
  <div class="bairro-frame"><iframe src="{e(embed)}" loading="lazy" tabindex="-1"
       title="Mapa de {e(bairro)}" referrerpolicy="no-referrer-when-downgrade"></iframe></div>
  <p class="bairro-nome">{e(bairro)}</p>
  <p class="bairro-qtd">{rotulo} · {e(cidade)}</p>
</a>""")

    if not cartoes:
        return ""
    return f"""
<section class="secao secao-bairros">
  <div class="wrap">
    <p class="sobrelinha" {reveal(0)}>Onde ficam</p>
    <h2 {reveal(1)}>Escolha pelo bairro, veja no mapa antes de abrir a ficha.</h2>
    <div class="bairros-grade">{"".join(cartoes)}</div>
  </div>
</section>
"""


def pagina_catalogo(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
    cards = "".join(card(i, corretor, numero=n, atraso=min(n - 1, 5) * 70)
                    for n, i in enumerate(imoveis, 1))

    def opcoes(chave: str) -> str:
        vistos = sorted({str(i[chave]) for i in imoveis})
        return "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in vistos)

    corpo = f"""
<section class="cabeca-pagina">
  <div class="wrap">
    <h1>Imóveis para alugar</h1>
    <p>Venda e locação em {e(corretor['atuacao'])}. Todos com preço à vista na tela —
       você sabe se cabe antes de me chamar.</p>
  </div>
</section>
{secao_mapa_bairros(imoveis)}
<section class="secao">
  <div class="wrap">
    <form class="filtros" id="filtros" aria-label="Filtrar imóveis">
      <label>Operação
        <select name="operacao">
          <option value="">Todas</option>
          <option value="venda">Venda</option>
          <option value="locacao" selected>Locação</option>
        </select>
      </label>
      <label>Tipo
        <select name="tipo"><option value="">Todos</option>{opcoes('tipo')}</select>
      </label>
      <label>Bairro
        <select name="bairro"><option value="">Todos</option>{opcoes('bairro')}</select>
      </label>
      <label>Finalidade
        <select name="finalidade"><option value="">Todas</option><option value="residencial">Residencial</option><option value="comercial">Comercial</option></select>
      </label>
      <label>Faixa de aluguel
        <select name="faixa"><option value="">Qualquer</option><option value="0-2000">Até R$ 2.000</option><option value="2000-3000">R$ 2.000–3.000</option><option value="3000-">Acima de R$ 3.000</option></select>
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
       ou <a href="index.html#quero-alugar">conte o que procura</a>.</p>
  </div>
</section>
"""
    return pagina(
        titulo="Imóveis à venda e para locação — Igor Santiago Imóveis",
        descricao="Aluguel residencial e comercial em Feira de Santana, com custo mensal visível.",
        corpo=corpo, publicar=publicar, jsonld=jsonld(corretor, imoveis, "imoveis.html", []), corretor=corretor, imoveis=imoveis,
        ativo="imoveis.html")


def galeria_carrossel(imovel: dict, n_fotos: int = 4) -> str:
    titulo = imovel["titulo"]
    slides = "".join(
        f'<div class="carrossel-slide{" ativo" if n == 1 else ""}">'
        f'{foto_placeholder(f"{titulo} — foto {n}", "aspect-16-10")}</div>'
        for n in range(1, n_fotos + 1))
    pontos = "".join(
        f'<button class="carrossel-ponto{" ativo" if n == 1 else ""}" type="button" '
        f'aria-label="Foto {n} de {n_fotos}" data-indice="{n - 1}"></button>'
        for n in range(1, n_fotos + 1))
    return f"""<div class="imovel-carrossel" data-carrossel>
  <div class="carrossel-trilho">{slides}</div>
  <button class="carrossel-seta carrossel-anterior" type="button" aria-label="Foto anterior" data-anterior>&#8249;</button>
  <button class="carrossel-seta carrossel-proxima" type="button" aria-label="Próxima foto" data-proxima>&#8250;</button>
  <div class="carrossel-pontos">{pontos}</div>
</div>"""


def pagina_imovel(corretor: dict, imovel: dict, imoveis: list[dict], publicar: bool = False) -> str:
    carrossel = galeria_carrossel(imovel)
    linhas_spec = "".join(
        f'<div class="spec"><dt>{e(k)}</dt><dd>{e(v)}</dd></div>' for k, v in specs(imovel))
    texto = "".join(f"<p>{e(p)}</p>" for p in imovel["descricao"])
    destaques = "".join(f"<li>{e(d)}</li>" for d in imovel["destaques"])
    duvidas = "".join(
        f'<details class="duvida"><summary>{e(d["pergunta"])}</summary>'
        f'<p>{e(d["resposta"])}</p></details>' for d in imovel["duvidas"])
    mapa = mapa_bairro(imovel)

    corpo = f"""
<nav class="migalha wrap" aria-label="Você está em">
  <a href="../index.html">Início</a> › <a href="../imoveis.html">Imóveis</a> ›
  <span>{e(imovel['bairro'])}</span>
</nav>

<section class="imovel-topo">
  <div class="wrap imovel-grade">
    {carrossel}
    {recibo_ficha(corretor, imovel)}
  </div>
</section>

<section class="secao">
  <div class="wrap imovel-conteudo">
    <div class="imovel-texto">
      <h2>Sobre o imóvel</h2>
      <p class="disponivel-em">{e(disponibilidade(imovel))}</p>
      {texto}
      <h2>Destaques</h2>
      <ul class="lista-destaques">{destaques}</ul>
    </div>
    <div class="imovel-lateral">
      <div class="imovel-specs">
        <h2>Ficha técnica</h2>
        <dl class="specs-grade">{linhas_spec}</dl>
        <p class="mini">Medidas e valores conferidos na documentação antes de qualquer
           proposta. Nada aqui substitui a certidão de matrícula, que eu levo na visita.</p>
      </div>
      {mapa}
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
        ativo="imoveis.html", prefixo="../", publicar=publicar,
        no_pagina=f"imovel/{imovel['slug']}.html",
        jsonld=jsonld(corretor, imoveis, f"imovel/{imovel['slug']}.html", imovel["duvidas"]),
        mensagem_wa=(f"Olá, Igor. Vi no seu site o imóvel \"{imovel['titulo']}\" "
                     f"e gostaria de agendar uma visita."))


def pagina_sobre(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
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
        <li>Você fala comigo do primeiro contato à assinatura. Não passo você adiante.</li>
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
                   "CRECI-BA 28.140. Locação residencial e comercial com atendimento pessoal."),
        corpo=corpo, publicar=publicar, jsonld=jsonld(corretor, imoveis, "sobre.html", []), corretor=corretor, imoveis=imoveis, ativo="sobre.html")


def pagina_vender(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
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
    corpo = f"""
<section class="cabeca-pagina cabeca-escura">
  <div class="wrap">
    <h1>Vender seu imóvel</h1>
    <p>Também trabalho com venda. Meu histórico inclui casa de R$ 200 mil; não apresento experiência de venda de alto padrão que ainda não tenho.</p>
    <p>Avaliação de mercado com o raciocínio na mesa. Preço inflado não vende — só faz o
       imóvel envelhecer no anúncio e perder valor de negociação.</p>
    <a class="btn btn-wa" href="{wa}" target="_blank" rel="noopener">Pedir avaliação</a>
  </div>
</section>

{secao_passos(passos)}

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
        corpo=corpo, publicar=publicar, jsonld=jsonld(corretor, imoveis, "vender.html", []), corretor=corretor, imoveis=imoveis, ativo="vender.html",
        mensagem_wa=corretor["mensagem_whatsapp_captacao"])


def pagina_privacidade(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
    ativo = publicar and corretor.get('privacidade_revisada') is True and corretor.get('email') not in (None, '', PENDENTE)
    aviso = ('Aviso de privacidade do atendimento imobiliário.' if ativo else
             'Rascunho — aguarda revisão jurídica e aprovação de Igor antes de o site ir ao ar.')
    estado_form = ('O formulário está disponível mediante seu consentimento.' if ativo else
                   'Nesta prévia ele está desativado: só será ativado após revisão jurídica e configuração do contato de Igor.')
    corpo = f"""
<section class="cabeca-pagina">
  <div class="wrap">
    <h1>Aviso de privacidade</h1>
    <p class="mini">{aviso}</p>
  </div>
</section>

<section class="secao">
  <div class="wrap texto-legal">
    <h2>Quem trata os seus dados</h2>
    <p>{e(corretor['nome_pessoa'])}, {e(corretor['titulo_profissional'])},
       {e(corretor['creci'])}, atuando em {e(corretor['atuacao'])}.
       Contato: {e(corretor['whatsapp_exibicao'])}.</p>

    <h2>Quais dados são coletados</h2>
    <p>O formulário de interesse solicita nome, WhatsApp e o tipo/faixa de imóvel que
       você procura, além do registro do consentimento. {estado_form}
       Você também pode iniciar uma conversa diretamente pelo WhatsApp.</p>

    <h2>Para que os dados são usados</h2>
    <p>Exclusivamente para atender ao seu contato: entender o que você procura, indicar
       imóveis e agendar visita. Para o formulário, a base prevista é o consentimento
       (art. 7º, I, da LGPD), que pode ser revogado. Procedimentos preliminares a contrato
       solicitados por você serão tratados conforme a base aplicável (art. 7º, V),
       sujeita à revisão jurídica deste aviso.</p>

    <h2>Compartilhamento</h2>
    <p>Quando ativado, o Netlify Forms processará e armazenará os envios como operador
       do formulário, com filtragem de spam. A notificação será enviada ao e-mail
       configurado de Igor, que registrará manualmente o contato no CRM de atendimento.
       O processamento pode ocorrer fora do Brasil; condições, suboperadores e transferência
       internacional precisam ser validados na revisão jurídica antes da ativação.</p>
    <p>Seus dados são compartilhados apenas com quem for necessário para a negociação que
       você mesmo pediu: proprietário do imóvel, cartório, banco ou administradora de
       condomínio. Não há venda de dados, não há repasse para lista de terceiros e não há
       disparo de mensagem em massa.</p>

    <h2>Por quanto tempo</h2>
    <p>Prazo proposto para contato que não avança: até 12 meses, sujeito à revisão jurídica.
       A exclusão deve abranger formulário, e-mail e CRM, salvo obrigação de conservação.
       Dados de negociação concluída são mantidos pelo prazo legal aplicável ao contrato.</p>

    <h2>Seus direitos</h2>
    <p>Você pode pedir a qualquer momento o acesso, a correção ou a exclusão dos seus
       dados, além de pedir para não ser mais contatado. Basta escrever no mesmo WhatsApp
       — o pedido é atendido sem que você precise justificar.</p>
    <p><a href="{e(wa_link(corretor, 'Olá, Igor. Quero solicitar acesso, correção ou exclusão dos meus dados.'))}">Solicitar acesso, correção ou exclusão pelo WhatsApp</a></p>
    <h2>Serviços carregados no navegador</h2>
    <p>Fontes do Google e mapas do OpenStreetMap podem receber dados técnicos da conexão,
       como endereço IP. WhatsApp e Instagram têm políticas próprias quando você abre
       seus links. Esses fluxos também integram a revisão de privacidade.</p>

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
        corpo=corpo, publicar=publicar, jsonld=jsonld(corretor, imoveis, "privacidade.html", []), corretor=corretor, imoveis=imoveis, ativo="privacidade.html")


def pagina_404(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
    corpo = """
<section class="cabeca-pagina">
  <div class="wrap">
    <h1>Página não encontrada</h1>
    <p>O endereço não existe ou o imóvel saiu do catálogo.</p>
    <a class="btn btn-principal" href="imoveis.html">Ver imóveis para alugar</a>
    <a class="btn btn-claro" href="index.html#quero-alugar">Conte o que procura</a>
  </div>
</section>
"""
    return pagina(titulo="Página não encontrada — Igor Santiago Imóveis",
                  descricao="Página não encontrada.", corpo=corpo, publicar=publicar, jsonld=jsonld(corretor, imoveis, "404.html", []),
                  corretor=corretor, imoveis=imoveis, ativo="")


# --------------------------------------------------------------------------
# arquivos auxiliares
# --------------------------------------------------------------------------

def jsonld(corretor: dict, imoveis: list[dict], no_pagina: str, faq: list[dict]) -> str:
    base = corretor['site_url'].rstrip('/')
    agente, pessoa, site = base + '/#agente', base + '/#pessoa', base + '/#site'
    url = base + '/' + no_pagina
    grafo = [
        {'@type': 'RealEstateAgent', '@id': agente, 'name': corretor['nome_marca'],
         'url': base + '/', 'telephone': '+' + corretor['whatsapp_e164'],
         'areaServed': ['Feira de Santana', 'Salvador'], 'founder': {'@id': pessoa}},
        {'@type': 'Person', '@id': pessoa, 'name': corretor['nome_pessoa'],
         'jobTitle': corretor['titulo_profissional'], 'identifier': corretor['creci'],
         'description': corretor['bio_longa']},
        {'@type': 'WebSite', '@id': site, 'name': corretor['nome_marca'], 'url': base + '/',
         'inLanguage': 'pt-BR', 'publisher': {'@id': agente}},
        {'@type': 'WebPage', '@id': url + '#pagina', 'url': url, 'inLanguage': 'pt-BR',
         'isPartOf': {'@id': site}, 'about': {'@id': agente}},
    ]
    for slug, nome, pagina_servico in [('locacao', 'Locação residencial e comercial', 'imoveis.html'),
                                      ('venda', 'Venda de imóveis', 'vender.html'),
                                      ('administracao', 'Administração de imóveis', 'administracao.html')]:
        grafo.append({'@type': 'Service', '@id': base + '/#' + slug, 'name': nome,
                      'serviceType': nome, 'provider': {'@id': agente},
                      'url': base + '/' + pagina_servico, 'areaServed': corretor['atuacao']})
    if faq:
        grafo.append({'@type': 'FAQPage', '@id': url + '#faq', 'mainEntity': [
            {'@type': 'Question', 'name': d['pergunta'],
             'acceptedAnswer': {'@type': 'Answer', 'text': d['resposta']}} for d in faq]})
    # Escape HTML delimiters without corrupting JSON; no demo Offer is emitted.
    texto = json.dumps({'@context': 'https://schema.org', '@graph': grafo}, ensure_ascii=False).replace('<', '\\u003c')
    return f'<script type="application/ld+json">{texto}</script>'


def escrever_llms_txt(corretor: dict, urls: list[str], publicar: bool) -> None:
    base = corretor['site_url'].rstrip('/')
    linhas = [f"# {corretor['nome_marca']}", '',
              '> ' + ('Site de corretagem.' if publicar else 'Prévia local: imóveis fictícios de demonstração. Não são ofertas reais.'),
              '', corretor['posicionamento'], corretor['creci'], '', '## Páginas', '']
    linhas.extend(f'- [{u}]({base}/{u})' for u in urls)
    (SAIDA / 'llms.txt').write_text('\n'.join(linhas) + '\n', encoding='utf-8')


def escrever_auxiliares(corretor: dict, imoveis: list[dict], publicar: bool) -> None:
    base = corretor["site_url"].rstrip("/")

    # Enquanto houver demo, robots.txt proibe tudo. So o build --publicar libera.
    if publicar:
        agentes = ['*', 'GPTBot', 'OAI-SearchBot', 'ClaudeBot', 'PerplexityBot', 'Google-Extended']
        robots = ''.join(f'User-agent: {agente}\nAllow: /\n\n' for agente in agentes)
        robots += f"Sitemap: {base}/sitemap.xml\n"
    else:
        robots = "User-agent: *\nDisallow: /\n"
    (SAIDA / "robots.txt").write_text(robots, encoding="utf-8")

    urls = sorted(p.relative_to(SAIDA).as_posix() for p in SAIDA.rglob('*.html')
                  if p.name not in {'404.html', 'obrigado.html'})
    # Timestamp real do artefato gerado, em vez de uma data inventada fixa.
    corpo = ''.join(f'  <url><loc>{e(base + "/" + u)}</loc><lastmod>'
                    f'{datetime.fromtimestamp((SAIDA / u).stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}'
                    '</lastmod></url>\n' for u in urls)
    escrever_llms_txt(corretor, urls, publicar)
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
    if not corretor.get("privacidade_revisada"):
        faltas.append("corretor.json → privacidade_revisada (B3: revisão jurídica antes de ativar formulário)")
    if not corretor.get("creci_confirmado_por_igor"):
        faltas.append("corretor.json → creci_confirmado_por_igor (Igor precisa confirmar "
                      f"que a grafia \"{corretor['creci']}\" bate com a carteirinha)")
    for imovel in imoveis:
        ficha = f"{imovel['_arquivo'].parent.name}/ficha.md"
        for campo, valores in ENUMS.items():
            if imovel.get(campo) and imovel[campo] not in valores:
                faltas.append(f"{ficha} → {campo} inválido: {imovel[campo]!r}")
        if imovel.get("operacao") == "locacao" and not imovel.get("garantias"):
            faltas.append(f"{ficha} → garantias (obrigatórias em locação)")
        d = imovel.get("disponivel_a_partir")
        if d and d < date.today():
            faltas.append(f"{ficha} → disponivel_a_partir vencida: {d.isoformat()}")
        bairro = f"{imovel['bairro']}|{imovel['cidade']}"
        if bairro not in COORDENADAS_BAIRRO:
            faltas.append(f"{ficha} → bairro sem coordenadas: {bairro}")
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
    # O console Windows em cp1252 não representa as setas das pendências.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
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

    if publicar and (corretor.get('privacidade_revisada') is not True
                     or corretor.get('email') in (None, '', PENDENTE)):
        print('RECUSADO: B3/B5 — revisão de privacidade e e-mail são necessários para ativar o formulário.', file=sys.stderr)
        return 2

    if SAIDA.exists():
        if SAIDA.resolve() != (ROOT / 'publico').resolve():
            raise ValueError(f'Saída fora do diretório de build autorizado: {SAIDA}')
        shutil.rmtree(SAIDA)
    (SAIDA / "imovel").mkdir(parents=True)

    shutil.copytree(ASSETS, SAIDA / "assets")

    paginas = {'index.html': pagina_home, 'imoveis.html': pagina_catalogo,
               'sobre.html': pagina_sobre, 'vender.html': pagina_vender,
               'privacidade.html': pagina_privacidade, '404.html': pagina_404,
               'obrigado.html': pagina_obrigado, 'administracao.html': pagina_administracao}
    for nome, render in paginas.items():
        (SAIDA / nome).write_text(render(corretor, imoveis, publicar=publicar), encoding='utf-8')
    for nome, finalidade in [('alugar-sala-comercial.html', 'comercial'), ('alugar-residencial.html', 'residencial')]:
        (SAIDA / nome).write_text(pagina_segmento(corretor, imoveis, finalidade, publicar), encoding='utf-8')
    for imovel in imoveis:
        (SAIDA / "imovel" / f"{imovel['slug']}.html").write_text(
            pagina_imovel(corretor, imovel, imoveis, publicar), encoding="utf-8")

    escrever_auxiliares(corretor, imoveis, publicar)

    faltas = pendencias(corretor, imoveis)
    print(f"OK -> {SAIDA / 'index.html'}")
    print(f"{len(imoveis)} imóveis · {len(list(SAIDA.rglob('*.html')))} páginas")
    if demos:
        print(f"AVISO: {len(demos)} imóvel(is) de demonstração no build. "
              "robots.txt está bloqueando tudo. Não publicar.")
    if faltas:
        print(f"{len(faltas)} pendência(s) — rode --check para a lista.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
