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
import hashlib
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
SITEMAP_STATE = DADOS / "sitemap-state.json"

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
             "preco", "preco_venda", "condominio", "iptu")
BOOLEANOS = ("destaque", "demo", "rascunho")
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


def ler_imoveis(incluir_rascunhos: bool = False) -> list[dict]:
    pasta = DADOS / "imoveis"
    if not pasta.is_dir():
        return []
    imoveis = [ler_ficha(f / "ficha.md")
               for f in sorted(pasta.iterdir())
               if not f.name.startswith("_") and (f / "ficha.md").is_file()]
    if not incluir_rascunhos:
        imoveis = [i for i in imoveis if not i.get("rascunho")]
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
    if imovel.get("situacao") == "reservado":
        msg = f'Olá, Igor. Quero ser avisado quando liberar o imóvel "{imovel["titulo"]}".'
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
    elif imovel.get('area_referencia'):
        itens.append(('Área da planta padrão', imovel['area_referencia']))
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
    if imovel.get("garantia_detalhe"):
        itens.append(("Garantia", imovel["garantia_detalhe"]))
    elif imovel.get("garantias"):
        nomes = {"seguro-fianca": "seguro-fiança", "caucao": "caução", "agua": "água"}
        itens.append(("Garantias aceitas", ", ".join(
            nomes.get(v, v) for v in imovel["garantias"])))
    if imovel.get("contas_inclusas"):
        nomes = {"seguro-fianca": "seguro-fiança", "caucao": "caução", "agua": "água"}
        itens.append(("Contas inclusas", ", ".join(
            nomes.get(v, v) for v in imovel["contas_inclusas"])))
    return itens


def resumo(imovel: dict) -> str:
    partes = []
    if imovel.get("area"):
        partes.append(f"{imovel['area']} m²")
    if imovel.get("quartos") and imovel.get("finalidade") != "comercial":
        quartos = imovel["quartos"]
        partes.append(f"{quartos} {'quarto' if quartos == 1 else 'quartos'}")
    if imovel.get("suites") and imovel.get("finalidade") != "comercial":
        suites = imovel["suites"]
        partes.append(f"{suites} {'suíte' if suites == 1 else 'suítes'}")
    if imovel.get("vagas"):
        partes.append(f"{imovel['vagas']} {'vaga' if imovel['vagas'] == 1 else 'vagas'}")
    return " · ".join(partes)


# --------------------------------------------------------------------------
# blocos de HTML
# --------------------------------------------------------------------------

def reveal(n: int = 0, passo_ms: int = 80) -> str:
    """Atributo de revelação escalonada: n-ésimo elemento de um grupo visual.
    Sem JS ou com "reduzir movimento", não faz nada (ver script no <head>)."""
    return f'data-reveal style="--atraso:{n * passo_ms}ms"'


def fotos_imovel(imovel: dict) -> list[Path]:
    """Fotos reais exportadas: pasta fotos-tratadas ao lado da ficha."""
    ficha = imovel.get("_arquivo")
    if not ficha:
        return []
    pasta = Path(ficha).parent / "fotos-tratadas"
    if not pasta.is_dir():
        return []
    return [f for f in sorted(pasta.iterdir()) if f.is_file() and not f.is_symlink()
            and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]


def dimensoes_imagem(arquivo: Path) -> tuple[int, int] | None:
    """Lê dimensões PNG/JPEG/WebP sem pacote de imagem no build do Netlify."""
    try:
        with arquivo.open("rb") as imagem:
            inicio = imagem.read(32)
            if inicio.startswith(b"\x89PNG\r\n\x1a\n") and len(inicio) >= 24:
                import struct
                return struct.unpack(">II", inicio[16:24])
            if inicio[:4] == b"RIFF" and inicio[8:12] == b"WEBP":
                import struct
                tipo, tamanho = inicio[12:16], int.from_bytes(inicio[16:20], "little")
                dados = inicio[20:20 + min(tamanho, 10)]
                if tipo == b"VP8X" and len(dados) >= 10:
                    largura = 1 + int.from_bytes(dados[4:7], "little")
                    altura = 1 + int.from_bytes(dados[7:10], "little")
                    return largura, altura
                if tipo == b"VP8L" and len(dados) >= 5 and dados[0] == 0x2F:
                    bits = int.from_bytes(dados[1:5], "little")
                    return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
                if tipo == b"VP8 " and len(dados) >= 10 and dados[3:6] == b"\x9d\x01\x2a":
                    largura = int.from_bytes(dados[6:8], "little") & 0x3FFF
                    altura = int.from_bytes(dados[8:10], "little") & 0x3FFF
                    return largura, altura
                return None
            if inicio[:2] != b"\xff\xd8":
                return None
            marcadores_sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6,
                              0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
            imagem.seek(2)
            while True:
                byte = imagem.read(1)
                if not byte:
                    return None
                if byte != b"\xff":
                    continue
                while byte == b"\xff":
                    byte = imagem.read(1)
                if not byte:
                    return None
                marcador = byte[0]
                if marcador in {0xD8, 0xD9}:
                    continue
                tamanho_bytes = imagem.read(2)
                if len(tamanho_bytes) != 2:
                    return None
                tamanho = int.from_bytes(tamanho_bytes, "big")
                if marcador in marcadores_sof:
                    dados = imagem.read(5)
                    if len(dados) != 5:
                        return None
                    altura = int.from_bytes(dados[1:3], "big")
                    largura = int.from_bytes(dados[3:5], "big")
                    return (largura, altura) if largura and altura else None
                if marcador == 0xDA:
                    return None
                imagem.seek(tamanho - 2, 1)
    except OSError:
        return None


def foto_url(imovel: dict, foto: Path, prefixo: str = "") -> str:
    return prefixo + "assets/imoveis/" + quote(imovel["slug"], safe="") + "/" + quote(foto.name)


def foto_card_url(imovel: dict, foto: Path, prefixo: str = "") -> str:
    miniatura = foto.parent / "_miniaturas" / "capa.webp"
    if miniatura.is_file():
        return prefixo + "assets/imoveis/" + quote(imovel["slug"], safe="") + "/capa.webp"
    return foto_url(imovel, foto, prefixo)


def retrato(corretor: dict, classe: str = "sobre-retrato") -> str:
    valor = corretor.get("foto", PENDENTE)
    if not valor or valor == PENDENTE:
        return ""
    arquivo = (ROOT / valor).resolve()
    if not arquivo.is_relative_to(ASSETS.resolve()) or not arquivo.is_file():
        return ""
    url = quote(arquivo.relative_to(ROOT).as_posix(), safe="/")
    dimensoes = dimensoes_imagem(arquivo)
    tamanho_html = (f'width="{dimensoes[0]}" height="{dimensoes[1]}" '
                    if dimensoes else "")
    return (f'<img class="{classe}" src="{e(url)}" {tamanho_html}'
            'alt="Igor Santiago, corretor de imóveis" loading="lazy" />')


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
    classe = "topo" if ativo == "index.html" else "topo topo--fixado"
    return f"""<header class="{classe}">
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


def wa_fixo(corretor: dict, mensagem: str, imovel: dict | None = None) -> str:
    valor = ""
    if imovel:
        locacao = imovel["operacao"] == "locacao"
        total = custo_mensal(imovel) if locacao else imovel["preco"]
        valor = (f'<div class="barra-mobile-custo"><strong>{moeda(total)}</strong>'
                 f'<span>{"/mês · aluguel + encargos informados" if locacao else "valor de venda"}</span></div>')
        mensagem = (f'Olá, Igor. Vi o imóvel "{imovel["titulo"]}" por {moeda(total)}'
                    + ("/mês com os encargos informados. " if locacao else ". ")
                    + ("Quero ser avisado quando liberar." if imovel.get("situacao") == "reservado"
                       else "Quero agendar uma visita."))
    return (f'<div class="barra-mobile">{valor}<a class="btn btn-wa" '
            f'href="{e(wa_link(corretor, mensagem))}" target="_blank" rel="noopener">'
            f'{"WhatsApp" if imovel else "Falar com Igor"}</a></div>')


def pagina(titulo: str, descricao: str, corpo: str, corretor: dict,
           imoveis: list[dict], ativo: str, prefixo: str = "",
           mensagem_wa: str | None = None, extra_js: str = "",
           publicar: bool = False, jsonld: str = "", no_pagina: str | None = None,
           imovel: dict | None = None) -> str:
    mensagem_wa = mensagem_wa or corretor["mensagem_whatsapp_geral"]
    no_pagina = no_pagina or ativo or "404.html"
    indexar = publicar and no_pagina not in {"obrigado.html", "404.html"}
    base = corretor["site_url"].rstrip("/")
    caminho_canonico = "" if no_pagina == "index.html" else no_pagina
    canonical = base + "/" + caminho_canonico
    imagem = base + "/assets/simbolo.png"
    imagem_alt = corretor["nome_marca"]
    if imovel:
        fotos = fotos_imovel(imovel)
        if fotos:
            imagem = base + "/" + foto_url(imovel, fotos[0])
            imagem_alt = f"{imovel['tipo']} em {imovel['bairro']}, {imovel['cidade']}"
    preload_imagem = (f'<link rel="preload" as="image" href="{e(imagem)}" fetchpriority="high" />'
                      if imovel else '')
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao)}" />
<meta name="theme-color" content="#0a0a0a" />
<meta name="robots" content="{'index, follow' if indexar else 'noindex, nofollow'}" />
{verificacao_busca() if publicar else ''}
<link rel="canonical" href="{e(canonical)}" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="{e(corretor['nome_marca'])}" />
<meta property="og:locale" content="pt_BR" />
<meta property="og:title" content="{e(titulo)}" />
<meta property="og:description" content="{e(descricao)}" />
<meta property="og:url" content="{e(canonical)}" />
<meta property="og:image" content="{e(imagem)}" />
<meta property="og:image:alt" content="{e(imagem_alt)}" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{e(titulo)}" />
<meta name="twitter:description" content="{e(descricao)}" />
<meta name="twitter:image" content="{e(imagem)}" />
{jsonld}
{preload_imagem}
<link rel="preload" href="{prefixo}assets/fonts/manrope-latin.woff2" as="font" type="font/woff2" crossorigin />
<link rel="preload" href="{prefixo}assets/fonts/archivo-latin.woff2" as="font" type="font/woff2" crossorigin />
<link rel="stylesheet" href="{prefixo}assets/styles.css?v=20261009-local-fonts" />
<link rel="icon" href="{prefixo}assets/favicon.png" type="image/png" />
<link rel="apple-touch-icon" href="{prefixo}assets/favicon-512.png" />
<script>
  if (!window.matchMedia || !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {{
    if ("IntersectionObserver" in window) document.documentElement.className += " js";
  }}
</script>
</head>
<body class="{'pagina-home' if ativo == 'index.html' else 'pagina-clara'}">
<a class="skip-link" href="#conteudo">Pular para o conteúdo</a>
<span class="topo-sentinela" aria-hidden="true"></span>
{barra_demo(imoveis)}
{cabecalho(corretor, ativo, prefixo)}
<main id="conteudo">
{corpo}
</main>
{rodape(corretor, prefixo)}
{wa_fixo(corretor, mensagem_wa, imovel)}
<script src="{prefixo}assets/script.js"></script>
{extra_js}
</body>
</html>
"""


def card(imovel: dict, corretor: dict, prefixo: str = "",
         numero: int | None = None, atraso: int = 0) -> str:
    marca_reservado = ('<span class="selo selo-reservado">Reservado</span>'
                       if imovel.get("situacao") == "reservado" else "")
    operacao = "Aluguel" if imovel["operacao"] == "locacao" else "Venda"
    venda = '<span class="selo selo-venda">Venda</span>' if imovel.get('preco_venda') else ''
    valor_venda = f'<p class="card-venda">Também à venda: <strong>{moeda(imovel["preco_venda"])}</strong></p>' if venda else ''
    lote = f'<span class="card-lote">{numero:02d}</span>' if numero else ""
    fotos = fotos_imovel(imovel)
    dimensoes = dimensoes_imagem(fotos[0]) if fotos else None
    tamanho_html = (f'width="{dimensoes[0]}" height="{dimensoes[1]}" '
                    if dimensoes else "")
    foto = (f'<div class="card-foto"><img src="{e(foto_card_url(imovel, fotos[0], prefixo))}" '
            f'alt="{e(imovel["tipo"])} em {e(imovel["bairro"])}, foto 1 de {len(fotos)}" '
            f'{tamanho_html}loading="lazy" decoding="async" /></div>') if fotos else ''
    custo = conta(imovel, 'selo') if imovel['operacao'] == 'locacao' else ''
    quando = disponibilidade(imovel)
    quando = f'<p class="disponivel-em">{e(quando)}</p>' if quando else ''
    return f"""<article class="card{' card--sem-foto' if not fotos else ''}" data-operacao="{e(imovel['operacao'])}"
         data-tipo="{e(imovel['tipo'])}" data-bairro="{e(imovel['bairro'])}" data-finalidade="{e(imovel['finalidade'])}"
         data-quartos="{imovel.get('quartos', 0)}" data-preco="{imovel['preco']}"
         data-reveal style="--atraso:{atraso}ms">
  <a class="card-link" href="{prefixo}imovel/{e(imovel['slug'])}.html">
    {foto}
    <div class="card-corpo">
      <div class="card-selos"><span class="selo selo-op">{operacao}</span>{venda}{marca_reservado}</div>
      <h3 class="card-titulo">{e(imovel['titulo'])}</h3>
      <p class="card-local">{e(imovel['bairro'])} · {e(imovel['cidade'])}</p>
      {custo}
      <p class="card-preco{' card-preco--base' if imovel['operacao'] == 'locacao' else ''}">{preco_rotulo(imovel)}</p>
      {valor_venda}
      {quando}
      <p class="card-specs">{e(resumo(imovel))}</p>
    </div>
  </a>
  <a class="card-wa" href="{e(wa_imovel(corretor, imovel))}" target="_blank" rel="noopener">
    {'Avisar quando liberar' if imovel.get('situacao') == 'reservado' else 'Agendar visita pelo WhatsApp'}
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





def numero_extenso(n: int) -> str:
    pequeno = ('zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze', 'catorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove')
    if n < 20:
        return pequeno[n]
    if n < 100:
        dezena = ('', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa')[n // 10]
        return dezena + (' e ' + numero_extenso(n % 10) if n % 10 else '')
    if n == 100:
        return 'cem'
    if n < 1000:
        centena = ('', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos')[n // 100]
        return centena + (' e ' + numero_extenso(n % 100) if n % 100 else '')
    for limite, singular, plural in [(1000000, 'um milhão', ' milhões'), (1000, 'mil', ' mil')]:
        if n >= limite:
            grupo, resto = divmod(n, limite)
            base = singular if grupo == 1 else numero_extenso(grupo) + plural
            return base + ((' e ' if resto < 100 or resto % 100 == 0 else ' ') + numero_extenso(resto) if resto else '')


def conta(imovel: dict, variante: str = 'cena', atraso_base: int = 0) -> str:
    locacao = imovel['operacao'] == 'locacao'
    total = custo_mensal(imovel) if locacao else imovel['preco']
    if variante == 'selo':
        return (f'<p class="conta--selo"><span>Custo mensal informado</span><strong>{moeda(total)}<small>/mês</small></strong></p>'
                '<p class="conta-nota">Aluguel + encargos informados. Consumos e garantia à parte, quando aplicáveis.</p>')
    inclusas = imovel.get('contas_inclusas', [])
    linhas = [('Aluguel' if locacao else 'Preço de venda', moeda(imovel['preco']))]
    for chave, rotulo, divisor in [('condominio', 'Condomínio', 1), ('iptu', 'IPTU ÷ 12', 12)]:
        valor = ('Incluso no aluguel' if locacao and chave in inclusas else
                 moeda(imovel[chave] // divisor) if chave in imovel else 'Consultar')
        if chave == 'iptu' and imovel.get('iptu_nao_incluido') == 'sim' and chave not in imovel:
            rotulo, valor = 'IPTU', 'Não incluído'
        linhas.append((rotulo, valor))
    def animar(atraso):
        return f'data-reveal style="--atraso:{atraso_base + atraso}ms"' if variante == 'cena' else ''
    itens = ''.join(f'<div class="conta-linha" {animar(n * 130)}><dt>{e(k)}</dt><dd>{e(v)}</dd></div>' for n, (k, v) in enumerate(linhas))
    legenda = 'Você paga por mês' if locacao else 'Valor de venda'
    acessivel = legenda + ': ' + numero_extenso(total) + (' real' if total == 1 else ' reais')
    nota = ('*Aluguel + encargos informados. IPTU dividido por 12, arredondado para baixo. Consumos e garantia à parte, quando aplicáveis.' if locacao else 'Condomínio e IPTU são encargos mensais, além do preço de venda.')
    revelar = 'data-reveal' if variante == 'painel' else ''
    return f'''<div class="conta conta--{variante}" {revelar}>
<p class="conta-imovel">{e(imovel['tipo'])} · {e(imovel['bairro'])}</p>
<dl class="conta-linhas">{itens}</dl>
<div class="conta-regua" aria-hidden="true" {animar(390)}></div>
<p class="conta-total" aria-label="{e(acessivel)}" {animar(520)}><span class="conta-legenda">{legenda}:</span> <strong>{moeda(total)}</strong></p>
<p class="conta-nota">{nota}</p></div>'''


def recibo_ficha(corretor: dict, imovel: dict) -> str:
    reservado = imovel.get('situacao') == 'reservado'
    aviso = '<p class="aviso-reservado">Proposta em análise — posso registrar seu interesse como segunda opção.</p>' if reservado else ''
    venda = ''
    if imovel.get('preco_venda'):
        mensagem = f'Olá, Igor. Tenho interesse na compra do imóvel "{imovel["titulo"]}", anunciado por {moeda(imovel["preco_venda"])}. Podemos conversar?'
        venda = f'<div class="opcao-venda"><h3>Também disponível para compra</h3><p class="valor-venda">{moeda(imovel["preco_venda"])}</p><a class="btn btn-largo" href="{e(wa_link(corretor, mensagem))}" target="_blank" rel="noopener">Conversar sobre a compra</a></div>'
    return f'''<aside class="recibo-ficha"><h2>Conta do imóvel</h2>
{conta(imovel, 'painel')}{aviso}
<a class="btn btn-wa btn-largo" target="_blank" rel="noopener" href="{e(wa_imovel(corretor, imovel))}">{'Avisar quando liberar' if reservado else 'Falar sobre este imóvel'}</a>
{venda}
<p class="painel-creci">{e(corretor['nome_pessoa'])} · {e(corretor['titulo_profissional'])} · <strong>{e(corretor['creci'])}</strong></p></aside>'''


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








def secao_percurso(passos: list[tuple[str, str]] | None = None, conta_de: dict | None = None) -> str:
    passos = passos or [
        ('Você me diz o que precisa e quanto cabe', 'Me conte o bairro, o tipo de imóvel e seu orçamento. Começamos pelo que faz sentido para você, por mensagem no WhatsApp.'),
        ('Você conhece os custos antes da visita', 'Aluguel, condomínio e IPTU somados — antes da visita, não depois.'),
        ('Entendemos as opções de garantia', 'Cada imóvel tem suas condições. Eu explico as garantias aceitas e a documentação necessária para a análise, antes de você apresentar uma proposta.'),
        ('Visita marcada e contrato conferido', 'Acompanho a visita e esclareço as condições do contrato com você, para que a assinatura seja uma decisão bem informada.')]
    itens = []
    for n, (titulo, texto) in enumerate(passos, 1):
        cena = conta(conta_de, 'cena') if n == 2 and conta_de else ''
        apoio = ('<p class="sobrelinha">Preço sem letra miúda</p>' if cena else '')
        detalhe = ('<p class="percurso-contexto">Compare o custo mensal informado com seu orçamento. Depois, visitamos as opções que fazem sentido para você.</p>' if cena else '')
        itens.append(f'<li class="passo" data-passo="{n}"><span class="passo-num" aria-hidden="true">{n:02d}</span><div class="passo-conteudo"><div class="passo-texto" {reveal()}>{apoio}<h3>{e(titulo)}</h3><p>{e(texto)}</p>{detalhe}</div>{cena}</div></li>')
    return '<section class="secao secao-percurso"><div class="wrap"><h2>O percurso até a chave</h2><ol class="percurso">' + ''.join(itens) + '</ol></div></section>'


def faq_global(corretor: dict) -> list[dict]:
    return [
        {"pergunta": "Qual é a condição de entrada no aluguel?", "resposta": "Primeiro aluguel mais dois meses de caução no ato: três valores de aluguel no total. Confirmamos os documentos e as condições do contrato antes da proposta."},
        {"pergunta": "É meu primeiro aluguel e não tenho comprovação tradicional. Posso conversar?", "resposta": "Sim. Vamos entender sua situação e conferir os documentos aceitos pelo imóvel de seu interesse. A aprovação depende da análise cadastral e da garantia escolhida."},
        {"pergunta": "Posso levar meu pet?", "resposta": "Consulte o campo de pet da ficha. Quando estiver como consultar, verifico as condições do imóvel antes da visita."},
        {"pergunta": "Posso procurar uma sala sem ter CNPJ ainda?", "resposta": "Sim. Podemos agendar uma conversa sobre o espaço e a atividade pretendida. A viabilidade do uso e os documentos precisam ser conferidos antes da contratação."},
        {"pergunta": "Há opções mobiliadas?", "resposta": "As fichas indicam se o imóvel é mobiliado, semimobiliado ou sem mobília. A relação de itens deve ser conferida na vistoria e no contrato."},
        {"pergunta": "Quem paga o quê além do aluguel?", "resposta": "O custo mensal mostrado soma aluguel, condomínio não incluso e IPTU anual dividido por 12, arredondado para baixo. Contas declaradas inclusas não são somadas novamente. Consumos e custos da garantia podem ser adicionais; confirmamos valores e responsabilidades no contrato."}]


def secao_objecoes(corretor: dict) -> str:
    itens = ''.join(f'<details class="duvida"><summary>{e(d["pergunta"])}</summary><p>{e(d["resposta"])}</p></details>' for d in faq_global(corretor))
    wa = e(wa_link(corretor, "Olá, Igor. Quero agendar uma conversa para tirar dúvidas sobre garantia e custos do aluguel."))
    return f'''<section class="secao secao-alt"><div class="wrap"><h2>Antes de alugar</h2>
<div class="duvidas">{itens}</div><p class="duvidas-cta"><a class="btn btn-wa" href="{wa}" target="_blank" rel="noopener">Tirar minhas dúvidas com Igor</a></p></div></section>'''


def secao_prova(corretor: dict) -> str:
    provas = ''.join(f'<div class="credencial"><h3>{e(p["titulo"])}</h3><p>{e(p["texto"])}</p></div>' for p in corretor['provas'])
    foto = retrato(corretor)
    classe = 'sobre-grade' if foto else 'sobre-grade sobre-grade--sem-foto'
    return f'''<section class="secao" id="quem-acompanha"><div class="wrap {classe}">
{foto}
<div class="sobre-texto"><h2>Experiência para orientar sua escolha</h2>
<p class="sobre-bio">{bio_ou_aviso(corretor, 'bio_curta', 'Bio pendente')}</p>
<p class="sobre-bio">{e(corretor.get('bio_abordagem', ''))}</p>
<div class="credenciais-grade">{provas}</div>
<a class="link-seta" href="sobre.html">Conheça minha trajetória</a></div></div></section>'''


def secao_nao_faco(corretor: dict) -> str:
    wa = e(wa_link(corretor, "Olá, Igor. Quero agendar uma conversa para conferir custos e documentos antes de visitar um imóvel."))
    return f'''<section class="secao"><div class="wrap"><h2>Clareza em cada etapa</h2>
<ul class="lista-destaques lista-nao"><li>Aluguel e encargos apresentados para você comparar o custo mensal.</li>
<li>Condições de cadastro e garantia explicadas antes da proposta.</li>
<li>Fotos que respeitam o tamanho e o estado real do imóvel.</li>
<li>Disponibilidade informada a partir da situação de cada imóvel.</li></ul>
<a class="btn btn-wa" href="{wa}" target="_blank" rel="noopener">Conversar sobre meu aluguel</a></div></section>'''


def formulario_lead(corretor: dict, publicar: bool) -> str:
    # B3/B5 não desaparecem apenas porque alguém passou --publicar.
    ativo = publicar and corretor.get('privacidade_revisada') is True and corretor.get('email') not in (None, '', PENDENTE)
    abertura = ('<form class="form-lead" name="quero-alugar" method="POST" data-netlify="true" netlify-honeypot="bot-field" action="/obrigado.html">'
                if ativo else '<div class="form-lead" role="group" aria-label="Formulário de interesse em prévia">')
    fim = '</form>' if ativo else '</div>'
    disabled = '' if ativo else ' disabled'
    opcoes = ['Sala comercial até R$ 2.000', 'Sala comercial R$ 2.000–3.000',
              'Sala comercial acima de R$ 3.000', 'Apartamento ou casa até R$ 2.000',
              'Apartamento ou casa R$ 2.000–3.000',
              'Apartamento ou casa acima de R$ 3.000', 'Outro']
    options = ''.join(f'<option>{e(o)}</option>' for o in opcoes)
    return f'''<section class="secao" id="quero-alugar"><div class="wrap">
<h2>Conte o que você quer alugar</h2>{abertura}
<input type="hidden" name="form-name" value="quero-alugar"{disabled}>
<input type="hidden" name="privacidade-versao" value="2026-10-05-telegram-v1"{disabled}>
<p class="escondido" aria-hidden="true"><label>Deixe este campo vazio<input name="bot-field" tabindex="-1" autocomplete="off"{disabled}></label></p>
<div class="form-campo"><label for="lead-nome">Nome</label><input id="lead-nome" name="nome" type="text" required autocomplete="name"{disabled}></div>
<div class="form-campo"><label for="lead-whatsapp">WhatsApp</label><input id="lead-whatsapp" name="whatsapp" type="tel" required inputmode="tel" autocomplete="tel" pattern="[+0-9\\(\\) .\\-]{{8,25}}"{disabled}></div>
<div class="form-campo"><label for="lead-procura">O que procura?</label><select id="lead-procura" name="procura" required{disabled}><option value="">Selecione</option>{options}</select></div>
<div class="consentimento"><input id="lead-consentimento" type="checkbox" name="consentimento" required{disabled}>
<label for="lead-consentimento">Autorizo Igor Santiago a usar os dados deste formulário para me atender por WhatsApp sobre imóveis para alugar, inclusive em um alerta privado de atendimento no Telegram, conforme o aviso de privacidade. Não há repasse para publicidade de terceiros e posso revogar o consentimento ou pedir exclusão.</label>
<a href="privacidade.html">Como meus dados são tratados</a></div>
<p>Resposta em até {e(corretor['resposta_prometida'])}, por mim mesmo.</p>
<button class="btn btn-principal" type="{'submit' if ativo else 'button'}"{disabled}>Quero falar com Igor</button>
<p class="mini">{'Uso seus dados para responder à sua procura por um imóvel.' if ativo else 'Formulário indisponível nesta prévia. Você pode conversar comigo pelo WhatsApp.'}</p>
<p>{e(corretor['nome_pessoa'])} · {e(corretor['titulo_profissional'])} · {e(corretor['creci'])}</p>{fim}</div></section>'''


def pagina_obrigado(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
    texto = 'Obrigado pelo contato. Após o envio, respondo pelo WhatsApp em até ' + corretor['resposta_prometida'] + '.' if publicar else 'Página de confirmação em prévia. Nenhum dado foi enviado por este formulário.'
    corpo = f'<section class="secao"><div class="wrap"><h1>Contato sobre aluguel</h1><p>{e(texto)}</p><a class="btn btn-principal" href="imoveis.html">Ver imóveis para alugar</a></div></section>'
    return pagina('Contato — Igor Santiago Imóveis', 'Contato sobre aluguel.', corpo, corretor, imoveis, 'obrigado.html', publicar=publicar, jsonld=jsonld(corretor, imoveis, 'obrigado.html', []))


def pagina_segmento(corretor: dict, imoveis: list[dict], finalidade: str, publicar: bool = False) -> str:
    comercial = finalidade == 'comercial'
    nome = 'alugar-sala-comercial.html' if comercial else 'alugar-residencial.html'
    titulo = ('Salas comerciais para alugar em Feira de Santana' if comercial
              else 'Aluguel residencial em Feira de Santana')
    texto = ('Encontre uma sala comercial para alugar em Feira de Santana. Compare localização, metragem e custo mensal; depois, conferimos juntos as condições para a atividade que você pretende exercer.' if comercial else 'Procura apartamento ou casa para alugar em Feira de Santana? Compare bairros, custo mensal e características como mobília e espaço para seu pet antes de marcar a visita.')
    mensagem = corretor['mensagem_whatsapp_comercial'] if comercial else 'Olá, Igor. Quero agendar uma conversa para alugar um apartamento ou casa.'
    lista = [i for i in imoveis if i['operacao'] == 'locacao' and i['finalidade'] == finalidade and i.get('situacao') not in {'alugado', 'vendido'}]
    cards = ''.join(card(i, corretor) for i in lista)
    corpo = f'''<section class="cabeca-pagina"><div class="wrap"><h1>{titulo}</h1><p>{texto}</p>
<a class="btn btn-wa" href="{e(wa_link(corretor, mensagem))}" target="_blank" rel="noopener">Falar com Igor</a></div></section>
<section class="secao"><div class="wrap"><div class="grade-cards">{cards}</div>
<a class="link-seta" href="index.html#quero-alugar">Conte o que procura</a></div></section>{secao_percurso(conta_de=lista[0] if lista else None)}{secao_objecoes(corretor)}'''
    return pagina(titulo + ' — Igor Santiago Imóveis', texto, corpo, corretor, imoveis, nome, mensagem_wa=mensagem, publicar=publicar, jsonld=jsonld(corretor, imoveis, nome, faq_global(corretor)))


def pagina_administracao(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
    msg = corretor['mensagem_whatsapp_administracao']
    corpo = f'''<section class="cabeca-pagina"><div class="wrap"><h1>Seu imóvel, com acompanhamento próximo</h1>
<p>Da preparação para alugar ao acompanhamento da locação, conversamos sobre o que seu imóvel precisa e definimos as responsabilidades de cada etapa.</p>
<a class="btn btn-wa" href="{e(wa_link(corretor, msg))}" target="_blank" rel="noopener">Conversar sobre meu imóvel</a></div></section>
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
  <img class="hero-marca-agua" src="assets/simbolo-leve.webp" alt="" aria-hidden="true" width="400" height="453" decoding="async" />
  <div class="wrap hero-texto">
    <div class="percurso-pontos" aria-hidden="true"><span class="ativo"></span><span></span><span></span><span></span></div>
    <p class="sobrelinha" {reveal(0)}>Aluguel em Feira de Santana</p>
    <h1 {reveal(1)}>Da primeira mensagem à <span class="acento">chave na mão</span></h1>
    <p class="hero-sub" {reveal(2)}>Aluguel residencial e comercial em Feira de Santana, com opções para diferentes orçamentos e os encargos apresentados antes da visita.</p>
    <div class="hero-botoes" {reveal(3)}>
      <a class="btn btn-principal" target="_blank" rel="noopener" href="{e(wa_link(corretor, corretor['mensagem_whatsapp_geral']))}">Falar com Igor</a>
      <a class="btn btn-contorno" href="imoveis.html">Ver imóveis para alugar</a>
    </div>
    <div class="hero-assinatura" {reveal(4)}>{retrato(corretor, 'hero-retrato')}<div><strong>{e(corretor['nome_pessoa'])}</strong><span>Corretor · {e(corretor['creci'])} · {e(corretor['anos_de_mercado'])} anos</span></div></div>
  </div>
</section>

<section class="secao">
  <div class="wrap">
    <div class="secao-topo" {reveal(0)}>
      <h2>Imóveis para alugar</h2>
      <a class="link-seta" href="imoveis.html">Ver todos os imóveis</a>
    </div>
    <div class="grade-cards grade-cards--vitrine">{cards}</div>
  </div>
</section>

{secao_percurso(conta_de=destaques[0] if destaques else None)}
{secao_objecoes(corretor)}
{secao_prova(corretor)}
{secao_nao_faco(corretor)}
{formulario_lead(corretor, publicar)}
<section class="secao"><div class="wrap"><h2>Onde começa seu próximo capítulo?</h2><p class="sub">Me conte o que procura e quanto pretende investir por mês. Vamos conversar sobre os imóveis e as condições que combinam com sua busca.</p>
<a class="btn btn-wa" href="{e(wa_link(corretor, 'Olá, Igor. Vi o custo mensal e quero agendar uma conversa para escolher meu aluguel.'))}" target="_blank" rel="noopener">Falar com Igor</a></div></section>
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
        if len(cartoes) == 6:
            break
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
    locacoes = [i for i in imoveis if i['operacao'] == 'locacao'
                and i.get('situacao') not in {'alugado', 'vendido'}]
    cards = "".join(card(i, corretor, numero=n, atraso=min(n - 1, 5) * 70)
                    for n, i in enumerate(locacoes, 1))

    def opcoes(chave: str) -> str:
        vistos = sorted({str(i[chave]) for i in locacoes})
        return "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in vistos)

    corpo = f"""
<section class="cabeca-pagina">
  <div class="wrap">
    <h1>Imóveis para alugar</h1>
    <p>Compare bairro, metragem e custo mensal antes de marcar uma visita.
       Veja opções residenciais e comerciais e confira as condições de cada aluguel.</p>
  </div>
</section>
{secao_mapa_bairros(imoveis)}
<section class="secao">
  <div class="wrap">
    <form class="filtros" id="filtros" aria-label="Filtrar imóveis">
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
        <select name="faixa"><option value="">Qualquer</option><option value="0-2000">Até R$ 2.000</option><option value="2000-3000">R$ 2.000–3.000</option><option value="3000-">Acima de R$ 3.000</option></select><span class="faixa-aviso mini" hidden>só para locação</span>
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
        titulo="Imóveis para alugar em Feira de Santana | Igor Santiago Imóveis",
        descricao="Aluguel residencial e comercial em Feira de Santana. Compare bairros, custos mensais e condições; fale direto com Igor Santiago, CRECI-BA 28.140.",
        corpo=corpo, publicar=publicar, jsonld=jsonld(corretor, imoveis, "imoveis.html", []), corretor=corretor, imoveis=imoveis,
        ativo="imoveis.html")


def galeria_carrossel(imovel: dict) -> str:
    fotos = fotos_imovel(imovel)
    if not fotos:
        return ""
    total = len(fotos)
    partes = []
    for n, foto in enumerate(fotos, 1):
        carga = 'fetchpriority="high"' if n == 1 else 'loading="lazy"'
        dimensoes = dimensoes_imagem(foto)
        tamanho_html = (f'width="{dimensoes[0]}" height="{dimensoes[1]}" '
                        if dimensoes else "")
        partes.append(f'<div class="carrossel-slide"><img src="{e(foto_url(imovel, foto, "../"))}" alt="{e(imovel["tipo"])} em {e(imovel["bairro"])}, foto {n} de {total}" {tamanho_html}{carga} decoding="async" /></div>')
    slides = ''.join(partes)
    pontos_lista = []
    for n in range(total):
        classe = ' ativo' if n == 0 else ''
        pontos_lista.append(f'<button class="carrossel-ponto{classe}" type="button" aria-label="Foto {n + 1} de {total}" data-indice="{n}"></button>')
    pontos = ''.join(pontos_lista)
    return f'''<div class="imovel-carrossel" data-carrossel><div class="carrossel-trilho">{slides}</div>
<button class="carrossel-seta carrossel-anterior" type="button" aria-label="Foto anterior" data-anterior>&#8249;</button>
<button class="carrossel-seta carrossel-proxima" type="button" aria-label="Próxima foto" data-proxima>&#8250;</button><div class="carrossel-pontos">{pontos}</div></div>'''


def videos_imovel(imovel: dict) -> list[Path]:
    pasta = imovel['_arquivo'].parent / 'videos-tratados'
    return sorted(pasta.glob('*.mp4')) if pasta.is_dir() else []


def galeria_videos(imovel: dict) -> str:
    videos = videos_imovel(imovel)
    if not videos:
        return ''
    itens = []
    for n, video in enumerate(videos, 1):
        caminho = f'../assets/imoveis/{imovel["slug"]}/videos/{video.name}'
        poster = video.with_suffix('.webp')
        poster_attr = f' poster="{e(caminho[:-4] + ".webp")}"' if poster.exists() else ''
        itens.append(f'<figure><video controls playsinline preload="none"{poster_attr} aria-label="Vídeo {n} do imóvel"><source src="{e(caminho)}" type="video/mp4" />Seu navegador não suporta este vídeo. <a href="{e(caminho)}">Abrir vídeo {n}</a></video><figcaption>Vídeo {n} · {e(imovel["tipo"])} em {e(imovel["bairro"])}</figcaption></figure>')
    return '<section class="secao secao-videos"><div class="wrap"><h2>Conheça o imóvel em vídeo</h2><p class="sub">Toque para assistir aos ambientes antes da visita.</p><div class="videos-grade">' + ''.join(itens) + '</div></div></section>'


def nome_predio(imovel: dict) -> str:
    if imovel.get('empreendimento'):
        return str(imovel['empreendimento']).strip()
    titulo = imovel.get('titulo', '')
    achado = re.search(r'\bno\s+(.+?)(?:,\s*(?:Santa Mônica|Capuchinhos|Centro|Getúlio Vargas|Feira de Santana)\b|$)',
                       titulo, flags=re.IGNORECASE)
    return achado.group(1).strip() if achado else ''


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
    selos = '<span class="selo selo-op">Aluguel</span>'
    if imovel.get('preco_venda'):
        selos += '<span class="selo selo-venda">Venda</span>'
    videos = galeria_videos(imovel)
    meta_venda = f' Também à venda por {moeda(imovel["preco_venda"])}.' if imovel.get('preco_venda') else ''

    corpo = f"""
<nav class="migalha wrap" aria-label="Você está em">
  <a href="../index.html">Início</a> › <a href="../imoveis.html">Imóveis</a> ›
  <span>{e(imovel['bairro'])}</span>
</nav>

<section class="imovel-topo">
  <div class="wrap"><div class="card-selos">{selos}</div><h1 class="imovel-titulo">{e(imovel['titulo'])}</h1><p class="imovel-local">Para alugar{' ou comprar' if imovel.get('preco_venda') else ''} · {e(imovel['bairro'])} · {e(imovel['cidade'])}</p></div>
  <div class="wrap imovel-grade{' imovel-grade--sem-foto' if not carrossel else ''}">
    {carrossel}
    {recibo_ficha(corretor, imovel)}
  </div>
</section>

{videos}

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
    predio = nome_predio(imovel)
    complemento_predio = f" {predio}" if predio else ""
    titulo_seo = (f"Aluguel {imovel['tipo']}{complemento_predio} – {imovel['bairro']}, "
                  f"{imovel['cidade']} | {moeda(imovel['preco'])}")
    descricao_seo = (f"Aluguel de {imovel['tipo'].lower()}"
                     + (f" no {predio}" if predio else "")
                     + f" – {imovel['bairro']}, {imovel['cidade']}: {moeda(imovel['preco'])}/mês. "
                     + f"{resumo(imovel)}. {corretor['creci']}.{meta_venda}")
    return pagina(
        titulo=titulo_seo,
        descricao=descricao_seo,
        corpo=corpo, corretor=corretor, imoveis=imoveis,
        ativo="imoveis.html", prefixo="../", publicar=publicar, imovel=imovel,
        no_pagina=f"imovel/{imovel['slug']}.html",
        jsonld=jsonld(corretor, imoveis, f"imovel/{imovel['slug']}.html", imovel["duvidas"]),
        mensagem_wa=(f"Olá, Igor. Vi no seu site o imóvel \"{imovel['titulo']}\" "
                     f"e gostaria de agendar uma visita."))


def pagina_sobre(corretor: dict, imoveis: list[dict], publicar: bool = False) -> str:
    provas = "".join(
        f'<div class="credencial"><h3>{e(p["titulo"])}</h3><p>{e(p["texto"])}</p></div>'
        for p in corretor["provas"])
    bio = bio_ou_aviso(
        corretor, "bio_longa",
        "[bio longa — Igor informar: como começou na corretagem, quantos anos de mercado, "
        "o que os 2 anos nos Estados Unidos mudaram no seu jeito de atender, e o tipo de "
        "cliente que você atende hoje]")

    corpo = f"""
<section class="cabeca-pagina">
  <div class="wrap">
    <h1>Conheça Igor Santiago</h1>
    <p>Experiência local e acompanhamento pessoal para uma decisão que faz parte da sua história.</p>
  </div>
</section>

<section class="secao">
  <div class="wrap sobre-grade{' sobre-grade--sem-foto' if not retrato(corretor) else ''}">
    {retrato(corretor)}
    <div class="sobre-texto">
      <h2>{e(corretor['nome_pessoa'])}</h2>
      <p class="sobre-credencial">{e(corretor['titulo_profissional'])} ·
         <strong>{e(corretor['creci'])}</strong> · {anos_mercado(corretor)}</p>
      <p class="sobre-bio">{bio.replace(chr(10) * 2, '</p><p class="sobre-bio">')}</p>
      <h3>Como eu trabalho</h3>
      <ul class="lista-destaques">
        <li>Você fala diretamente comigo, do primeiro contato à assinatura.</li>
        <li>Você conhece o aluguel e os encargos informados antes de marcar a visita.</li>
        <li>Matrícula e certidões conferidas antes de qualquer proposta ser apresentada.</li>
        <li>Quando uma informação depende de confirmação, eu verifico e explico antes de você decidir.</li>
      </ul>
      <a class="btn btn-wa" target="_blank" rel="noopener"
         href="{e(wa_link(corretor, corretor['mensagem_whatsapp_geral']))}">Falar no WhatsApp</a>
    </div>
  </div>
</section>

<section class="secao secao-credenciais">
  <div class="wrap credenciais-grade">{provas}</div>
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
    <p>Um bom preço começa com uma análise do imóvel e do mercado ao redor. Vamos entender os diferenciais, conferir a documentação e definir uma faixa de anúncio com fundamento.</p>
    <p>Você recebe a análise por escrito e entende os critérios usados para chegar ao preço. Assim, pode decidir o próximo passo com mais informação.</p>
    <a class="btn btn-wa" href="{wa}" target="_blank" rel="noopener">Pedir avaliação</a>
  </div>
</section>

{secao_percurso(passos).replace('O percurso até a chave', 'Da análise ao anúncio')}

<section class="secao secao-alt">
  <div class="wrap">
    <h2>Clareza em cada etapa</h2>
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
    <p>O Netlify Forms processa e armazena os envios, com filtragem de spam, e envia
       uma notificação ao e-mail de Igor. Para organizar o atendimento, uma automação
       executada no GitHub Actions consulta os envios verificados e encaminha ao chat
       privado de Igor no Telegram apenas nome, WhatsApp, tipo/faixa procurada, data e
       hora e registro do consentimento. O alerta não contém o e-mail bruto, IP ou
       outros metadados técnicos. O contato com você é feito manualmente por Igor;
       o cadastro no CRM de atendimento também é manual.
       Netlify, GitHub e Telegram podem processar dados fora do Brasil. Condições,
       papéis desses serviços e mecanismo de transferência internacional devem ser
       validados na revisão jurídica desta atualização antes de ativar a automação.</p>
    <p>Seus dados são compartilhados apenas com quem for necessário para a negociação que
       você mesmo pediu: proprietário do imóvel, cartório, banco ou administradora de
       condomínio. Não há venda de dados, não há repasse para lista de terceiros e não há
       disparo de mensagem em massa.</p>

    <h2>Por quanto tempo</h2>
    <p>Prazo proposto para contato que não avança: até 12 meses, sujeito à revisão jurídica.
       A exclusão deve abranger formulário, e-mail, mensagens do Telegram e CRM, salvo obrigação de conservação.
       Dados de negociação concluída são mantidos pelo prazo legal aplicável ao contrato.</p>

    <h2>Seus direitos</h2>
    <p>Você pode pedir a qualquer momento o acesso, a correção ou a exclusão dos seus
       dados, além de pedir para não ser mais contatado. Basta escrever no mesmo WhatsApp
       — o pedido é atendido sem que você precise justificar.</p>
    <p><a href="{e(wa_link(corretor, 'Olá, Igor. Quero solicitar acesso, correção ou exclusão dos meus dados.'))}">Solicitar acesso, correção ou exclusão pelo WhatsApp</a></p>
    <h2>Serviços carregados no navegador</h2>
    <p>Mapas do OpenStreetMap podem receber dados técnicos da conexão,
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
    url = base + '/' + ('' if no_pagina == 'index.html' else no_pagina)
    foto_corretor = corretor.get('foto')
    imagem_corretor = base + '/' + foto_corretor if foto_corretor and foto_corretor != PENDENTE else base + '/assets/simbolo.png'
    redes = [f"https://www.instagram.com/{corretor['instagram']}/"] if corretor.get('instagram') else []
    perfil_google = corretor.get('perfil_google_url', '')
    if isinstance(perfil_google, str) and perfil_google.startswith('https://'):
        redes.append(perfil_google)
    grafo = [
        {'@type': 'RealEstateAgent', '@id': agente, 'name': corretor['nome_marca'],
         'url': base + '/', 'telephone': '+' + corretor['whatsapp_e164'],
         'logo': base + '/assets/simbolo.png', 'image': imagem_corretor,
         'sameAs': redes, 'areaServed': corretor['atuacao'], 'founder': {'@id': pessoa}},
        {'@type': 'Person', '@id': pessoa, 'name': corretor['nome_pessoa'],
         'jobTitle': corretor['titulo_profissional'], 'identifier': corretor['creci'],
         'description': corretor['bio_longa']},
        {'@type': 'WebSite', '@id': site, 'name': corretor['nome_marca'], 'url': base + '/',
         'inLanguage': 'pt-BR', 'publisher': {'@id': agente}},
        {'@type': 'WebPage', '@id': url + '#pagina', 'url': url, 'inLanguage': 'pt-BR',
         'isPartOf': {'@id': site}, 'about': {'@id': agente}},
    ]
    for slug, nome, pagina_servico in [('locacao', 'Locação residencial e comercial', 'imoveis.html'),
                                      ('administracao', 'Administração de imóveis', 'administracao.html')]:
        grafo.append({'@type': 'Service', '@id': base + '/#' + slug, 'name': nome,
                      'serviceType': nome, 'provider': {'@id': agente},
                      'url': base + '/' + pagina_servico, 'areaServed': corretor['atuacao']})
    if faq:
        grafo.append({'@type': 'FAQPage', '@id': url + '#faq', 'mainEntity': [
            {'@type': 'Question', 'name': d['pergunta'],
             'acceptedAnswer': {'@type': 'Answer', 'text': d['resposta']}} for d in faq]})
    ficha = next((i for i in imoveis if no_pagina == f"imovel/{i['slug']}.html"), None)
    if ficha:
        fotos = fotos_imovel(ficha)
        imagens = [base + '/' + foto_url(ficha, foto) for foto in fotos]
        tipo_imovel = ('Apartment' if ficha.get('tipo') == 'Apartamento' else
                       'House' if ficha.get('tipo') in {'Casa', 'Casa em condomínio'} else 'Place')
        item = {'@type': tipo_imovel, 'name': ficha['titulo'],
                'address': {'@type': 'PostalAddress', 'addressLocality': ficha['cidade'],
                            'addressRegion': corretor.get('uf', 'BA'),
                            'addressCountry': 'BR'},
                'containedInPlace': {'@type': 'Place', 'name': ficha['bairro']}}
        if imagens:
            item['image'] = imagens
        if ficha.get('finalidade') != 'comercial' and ficha.get('quartos'):
            item['numberOfBedrooms'] = ficha['quartos']
            item['numberOfRooms'] = ficha['quartos']
        if ficha.get('vagas'):
            item['numberOfParkingSpaces'] = ficha['vagas']
        # area só existe no campo confirmado da ficha; area_referencia nunca vira metragem da unidade.
        if ficha.get('area'):
            item['floorSize'] = {'@type': 'QuantitativeValue', 'value': ficha['area'], 'unitCode': 'MTK'}
        offer = {'@type': 'Offer', 'price': str(ficha['preco']), 'priceCurrency': 'BRL',
                 'availability': 'https://schema.org/' + ('InStock' if ficha.get('situacao') == 'disponivel' else 'LimitedAvailability'),
                 'url': url, 'itemOffered': item, 'seller': {'@id': agente}}
        grafo.extend([
            {'@type': 'RealEstateListing', '@id': url + '#anuncio', 'url': url,
             'name': ficha['titulo'], 'description': ' '.join(ficha.get('descricao', [])),
             'image': imagens, 'mainEntity': item, 'offers': offer},
            {'@type': 'BreadcrumbList', '@id': url + '#breadcrumb', 'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'name': 'Início', 'item': base + '/'},
                {'@type': 'ListItem', 'position': 2, 'name': 'Imóveis', 'item': base + '/imoveis.html'},
                {'@type': 'ListItem', 'position': 3, 'name': ficha['bairro'], 'item': url}]},
        ])
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


def verificacao_busca() -> str:
    caminho = DADOS / 'busca.json'
    config = json.loads(caminho.read_text(encoding='utf-8')) if caminho.exists() else {}
    return '\n'.join(f'<meta name="{nome}" content="{e(config[campo])}" />'
                     for campo, nome in [('google', 'google-site-verification'),
                                         ('bing', 'msvalidate.01')] if config.get(campo))


def escrever_auxiliares(corretor: dict, imoveis: list[dict], publicar: bool) -> None:
    base = corretor["site_url"].rstrip("/")
    busca = DADOS / 'busca.json'
    if publicar and busca.exists():
        chave = json.loads(busca.read_text(encoding='utf-8')).get('indexnow', '')
        if chave:
            if not re.fullmatch(r'[a-zA-Z0-9-]{8,128}', chave):
                raise ValueError('Chave pública IndexNow inválida')
            (SAIDA / f'{chave}.txt').write_text(chave, encoding='utf-8')

    # Enquanto houver demo, robots.txt proibe tudo. So o build --publicar libera.
    if publicar:
        agentes = ['*', 'GPTBot', 'OAI-SearchBot', 'ClaudeBot', 'PerplexityBot', 'Google-Extended']
        robots = ''.join(f'User-agent: {agente}\nAllow: /\n\n' for agente in agentes)
        robots += f"Sitemap: {base}/sitemap.xml\n"
    else:
        robots = "User-agent: *\nDisallow: /\n"
    (SAIDA / "robots.txt").write_text(robots, encoding="utf-8")

    arquivos = sorted(p.relative_to(SAIDA).as_posix() for p in SAIDA.rglob('*.html')
                      if p.name not in {'404.html', 'obrigado.html'})
    urls = ['' if u == 'index.html' else u for u in arquivos]
    try:
        estado_anterior = json.loads(SITEMAP_STATE.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        estado_anterior = {}
    estado_atual = {}
    hoje = datetime.now(timezone.utc).date().isoformat()
    registros = []
    for url, arquivo in zip(urls, arquivos):
        conteudo_hash = hashlib.sha256((SAIDA / arquivo).read_bytes()).hexdigest()
        anterior = estado_anterior.get(arquivo, {})
        lastmod = (anterior.get('lastmod') if anterior.get('sha256') == conteudo_hash
                   else hoje)
        estado_atual[arquivo] = {'sha256': conteudo_hash, 'lastmod': lastmod}
        registros.append(f'  <url><loc>{e(base + "/" + url)}</loc><lastmod>{lastmod}</lastmod></url>\n')
    SITEMAP_STATE.write_text(json.dumps(estado_atual, ensure_ascii=False, indent=2) + '\n',
                             encoding='utf-8')
    corpo = ''.join(registros)
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
        if imovel.get("rascunho"):
            faltas.append(f"{ficha} → rascunho — falta revisar ficha")
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
    imoveis = ler_imoveis(incluir_rascunhos=checar or publicar)

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

    if publicar:
        retrato_path = corretor.get("foto")
        retrato_ok = False
        if retrato_path not in (None, "", PENDENTE):
            foto = (ROOT / retrato_path).resolve()
            retrato_ok = foto.is_relative_to(ASSETS.resolve()) and foto.is_file()
        liberados = [i for i in imoveis if not i.get("demo") and not i.get("rascunho")]
        bloqueios = []
        if corretor.get("creci_confirmado_por_igor") is not True:
            bloqueios.append("CRECI ainda não confirmado por Igor")
        if corretor.get("regime") in (None, "", PENDENTE):
            bloqueios.append("regime profissional pendente")
        if not retrato_ok:
            bloqueios.append("retrato válido ausente em assets/")
        if not liberados:
            bloqueios.append("nenhum imóvel real fora de rascunho")
        if bloqueios:
            print("RECUSADO: preparação do lançamento incompleta — " + "; ".join(bloqueios) + ".",
                  file=sys.stderr)
            return 2
        # Rascunhos são lidos para que o gate possa explicar o bloqueio,
        # mas nunca entram na saída publicável.
        imoveis = [i for i in imoveis if not i.get("rascunho")]

    if SAIDA.exists():
        if SAIDA.resolve() != (ROOT / 'publico').resolve():
            raise ValueError(f'Saída fora do diretório de build autorizado: {SAIDA}')
        shutil.rmtree(SAIDA)
    (SAIDA / "imovel").mkdir(parents=True)

    shutil.copytree(ASSETS, SAIDA / "assets")
    for imovel in imoveis:
        fotos = fotos_imovel(imovel)
        if fotos:
            destino = SAIDA / "assets" / "imoveis" / imovel['slug']
            if not destino.resolve().is_relative_to((SAIDA / "assets" / "imoveis").resolve()):
                raise ValueError("Slug inválido para fotos")
            destino.mkdir(parents=True, exist_ok=True)
            for foto in fotos:
                shutil.copy2(foto, destino / foto.name)
            miniatura = fotos[0].parent / "_miniaturas" / "capa.webp"
            if miniatura.is_file():
                shutil.copy2(miniatura, destino / "capa.webp")
        videos = videos_imovel(imovel)
        if videos:
            destino_video = SAIDA / 'assets/imoveis' / imovel['slug'] / 'videos'
            if not destino_video.resolve().is_relative_to((SAIDA / 'assets/imoveis').resolve()):
                raise ValueError('Slug inválido para vídeos')
            destino_video.mkdir(parents=True, exist_ok=True)
            for video in videos:
                shutil.copy2(video, destino_video / video.name)
                poster = video.with_suffix('.webp')
                if poster.exists():
                    shutil.copy2(poster, destino_video / poster.name)

    paginas = {'index.html': pagina_home, 'imoveis.html': pagina_catalogo,
               'sobre.html': pagina_sobre,
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
