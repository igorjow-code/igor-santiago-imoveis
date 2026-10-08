#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Importa fotos de imóveis, remove metadados e converte para WebP.

Requer ffmpeg e ffprobe no PATH; o restante usa apenas a biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
DADOS = ROOT / "dados"
ENTRADA = ROOT / "entrada-fotos"
IMAGENS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
SLUG_RE = re.compile(r"^[a-z0-9-]+$")


class ImportErrorFotos(Exception):
    """Erro que deve ser apresentado sem traceback ao operador."""


def validar_slug(slug: str) -> str:
    if not SLUG_RE.fullmatch(slug):
        raise ImportErrorFotos("slug inválido; use apenas letras minúsculas, números e hífens")
    return slug


def validar_zip(caminho: Path) -> None:
    """Recusa caminhos absolutos, traversal e nomes que escapam do diretório temporário."""
    with zipfile.ZipFile(caminho) as arquivo:
        for item in arquivo.infolist():
            nome = item.filename.replace("\\", "/")
            relativo = PurePosixPath(nome)
            if relativo.is_absolute() or ".." in relativo.parts or ":" in nome:
                raise ImportErrorFotos(f"zip-slip recusado: {item.filename!r}")
            modo = item.external_attr >> 16
            if (modo & 0o170000) == 0o120000:
                raise ImportErrorFotos(f"link simbólico recusado no ZIP: {item.filename!r}")


def coletar_entradas(origem: Path, temporario: Path) -> list[tuple[str, Path]]:
    if origem.is_file() and origem.suffix.lower() == ".zip":
        validar_zip(origem)
        destino = temporario / "extraido"
        destino.mkdir()
        arquivos = []
        with zipfile.ZipFile(origem) as arquivo:
            for item in arquivo.infolist():
                relativo = PurePosixPath(item.filename.replace("\\", "/"))
                if item.is_dir() or relativo.suffix.lower() not in IMAGENS:
                    continue
                # Nomes temporários simples evitam caracteres e pastas do ZIP
                # incompatíveis com Windows (espaço/ponto final, nomes reservados).
                copia = destino / f"{len(arquivos):08d}{relativo.suffix.lower()}"
                with arquivo.open(item) as entrada, copia.open("wb") as saida:
                    shutil.copyfileobj(entrada, saida)
                arquivos.append((item.filename, copia))
        return sorted(arquivos, key=lambda item: (item[0].casefold(), item[0]))
    elif origem.is_dir():
        raiz = origem
    else:
        raise ImportErrorFotos(f"entrada não encontrada ou não é ZIP/pasta: {origem}")

    arquivos = []
    for caminho in raiz.rglob("*"):
        if caminho.is_file() and not caminho.is_symlink() and caminho.suffix.lower() in IMAGENS:
            arquivos.append((caminho.relative_to(raiz).as_posix(), caminho))
    return sorted(arquivos, key=lambda item: (item[0].casefold(), item[0]))


def nome_seguro(nome: str) -> str:
    base = unicodedata.normalize("NFKD", Path(nome).stem)
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return (base or "foto")[:70].rstrip("-") or "foto"


def tem_encoder_webp(ffmpeg: str) -> bool:
    resultado = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
    return resultado.returncode == 0 and "libwebp" in resultado.stdout


def verificar_sem_metadados(ffprobe: str, caminho: Path) -> None:
    resultado = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format_tags:stream_tags", "-of", "json", str(caminho)],
        capture_output=True, text=True,
    )
    if resultado.returncode:
        raise ImportErrorFotos(f"ffprobe falhou em {caminho.name}: {resultado.stderr.strip()}")
    try:
        dados = json.loads(resultado.stdout)
    except json.JSONDecodeError as erro:
        raise ImportErrorFotos(f"resposta inválida do ffprobe em {caminho.name}") from erro
    tags = dict(dados.get("format", {}).get("tags", {}))
    for stream in dados.get("streams", []):
        tags.update(stream.get("tags", {}))
    if tags:
        raise ImportErrorFotos(f"metadados permaneceram em {caminho.name}: {', '.join(tags)}")


def converter(ffmpeg: str, origem: Path, destino: Path, formato: str) -> None:
    filtro = "scale=w='min(1600,iw)':h='min(1600,ih)':force_original_aspect_ratio=decrease"
    comando = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(origem),
               # HEIC em mosaico já usa um grafo interno no ffmpeg. O filtro
               # complexo preserva a imagem completa montada pelo decodificador.
               "-filter_complex", filtro + "[foto]", "-map", "[foto]",
               "-map_metadata", "-1", "-frames:v", "1"]
    if formato == "webp":
        comando += ["-c:v", "libwebp", "-quality", "80", "-compression_level", "6"]
    else:
        comando += ["-q:v", "3"]
    comando.append(str(destino))
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode:
        raise ImportErrorFotos(resultado.stderr.strip() or "ffmpeg não conseguiu converter a imagem")


def converter_miniatura(ffmpeg: str, origem: Path, destino: Path) -> None:
    """Capa para cartões; preserva a foto integral na galeria do imóvel."""
    filtro = "scale=w='min(800,iw)':h='min(800,ih)':force_original_aspect_ratio=decrease"
    resultado = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(origem),
        "-filter_complex", filtro + "[capa]", "-map", "[capa]", "-map_metadata", "-1",
        "-frames:v", "1", "-c:v", "libwebp", "-quality", "78",
        "-compression_level", "6", str(destino),
    ], capture_output=True, text=True)
    if resultado.returncode:
        raise ImportErrorFotos("não foi possível preparar a miniatura do cartão")


def importar(origem: Path, slug: str, substituir: bool = False, dry_run: bool = False) -> int:
    validar_slug(slug)
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ImportErrorFotos("ffmpeg e ffprobe precisam estar disponíveis no PATH")

    pasta_imoveis = DADOS / "imoveis"
    pasta_imoveis.mkdir(parents=True, exist_ok=True)
    if not pasta_imoveis.resolve().is_relative_to(DADOS.resolve()):
        raise ImportErrorFotos("pasta dados/imoveis aponta para fora de dados/")
    destino_imovel = pasta_imoveis / slug
    if not destino_imovel.resolve().is_relative_to(pasta_imoveis.resolve()):
        raise ImportErrorFotos("destino fora de dados/imoveis")
    saida = destino_imovel / "fotos-tratadas"
    if saida.is_symlink() or (saida.exists() and not saida.is_dir()):
        raise ImportErrorFotos("fotos-tratadas precisa ser uma pasta real dentro do imóvel")
    if saida.exists() and not saida.resolve().is_relative_to(destino_imovel.resolve()):
        raise ImportErrorFotos("fotos-tratadas aponta para fora da pasta do imóvel")
    if saida.exists() and any(saida.iterdir()) and not substituir:
        raise ImportErrorFotos(f"{saida} já contém arquivos; use --substituir para trocar as fotos")

    with tempfile.TemporaryDirectory(prefix="is-imoveis-fotos-") as temp:
        temporario = Path(temp)
        entradas = coletar_entradas(origem, temporario)
        if not entradas:
            raise ImportErrorFotos("nenhuma imagem JPG, PNG, WebP ou HEIC foi encontrada")
        webp = tem_encoder_webp(ffmpeg)
        extensao = ".webp" if webp else ".jpg"
        if dry_run:
            print(f"Prévia: {len(entradas)} foto(s) para {slug}; formato {extensao[1:]}. Nenhum arquivo alterado.")
            for i, (nome, _) in enumerate(entradas, 1):
                print(f"  {i:02d}-{nome_seguro(nome)}{extensao}")
            return 0

        preparadas = temporario / "preparadas"
        preparadas.mkdir()
        falhas: list[tuple[str, str]] = []
        concluidas: list[Path] = []
        for numero, (nome, caminho) in enumerate(entradas, 1):
            arquivo_saida = preparadas / f"{numero:02d}-{nome_seguro(nome)}{extensao}"
            try:
                converter(ffmpeg, caminho, arquivo_saida, "webp" if webp else "jpg")
                verificar_sem_metadados(ffprobe, arquivo_saida)
                concluidas.append(arquivo_saida)
            except ImportErrorFotos as erro:
                falhas.append((nome, str(erro)))
                arquivo_saida.unlink(missing_ok=True)

        if not concluidas:
            print("Nenhuma imagem foi convertida; as fotos existentes foram preservadas.")
            for nome, erro in falhas:
                print(f"  - {nome}: {erro}")
            return 1

        if saida.exists() and substituir:
            shutil.rmtree(saida)
        saida.mkdir(parents=True, exist_ok=True)
        for caminho in concluidas:
            shutil.move(str(caminho), str(saida / caminho.name))

        if webp:
            temporaria_capa = temporario / "capa.webp"
            try:
                converter_miniatura(ffmpeg, saida / concluidas[0].name, temporaria_capa)
                verificar_sem_metadados(ffprobe, temporaria_capa)
                miniaturas = saida / "_miniaturas"
                miniaturas.mkdir(exist_ok=True)
                shutil.move(str(temporaria_capa), str(miniaturas / "capa.webp"))
                print(f"Miniatura otimizada para cartões: {(miniaturas / 'capa.webp').stat().st_size // 1024} KB.")
            except ImportErrorFotos as erro:
                print(f"AVISO: miniatura não preparada ({erro}); o site usará a foto integral.")

        ficha = destino_imovel / "ficha.md"
        if not ficha.exists():
            modelo = DADOS / "_modelo" / "ficha.md"
            if not modelo.is_file():
                raise ImportErrorFotos(f"modelo de ficha não encontrado: {modelo}")
            ficha.write_text(modelo.read_text(encoding="utf-8").replace(
                "slug: __PREENCHER__", f"slug: {slug}"
            ), encoding="utf-8")

        print(f"Importadas {len(concluidas)} foto(s) em {saida} ({'WebP' if webp else 'JPG'}).")
        for caminho in sorted(saida.iterdir()):
            if caminho.is_file() and caminho.suffix.lower() in {".webp", ".jpg", ".jpeg"}:
                if caminho.stat().st_size > 500 * 1024:
                    print(f"AVISO: {caminho.name} tem {caminho.stat().st_size // 1024} KB (> 500 KB).")
        if len(concluidas) > 25:
            print(f"AVISO: {len(concluidas)} fotos; recomenda-se no máximo 25 por imóvel.")
        if falhas:
            print(f"Não convertidas ({len(falhas)}):")
            for nome, erro in falhas:
                print(f"  - {nome}: {erro}")
        return 1 if falhas else 0


def processar_lote() -> int:
    if not ENTRADA.is_dir():
        raise ImportErrorFotos(f"pasta de entrada não encontrada: {ENTRADA}")
    fontes = sorted(ENTRADA.iterdir(), key=lambda p: p.name.casefold())
    fontes = [p for p in fontes if (p.is_dir() or (p.is_file() and p.suffix.lower() == ".zip"))]
    if not fontes:
        raise ImportErrorFotos(f"nenhum .zip ou subdiretório em {ENTRADA}")
    status = 0
    for fonte in fontes:
        slug = fonte.stem if fonte.is_file() else fonte.name
        print(f"\n== {slug} ==")
        try:
            status = max(status, importar(fonte, slug))
        except ImportErrorFotos as erro:
            print(f"ERRO: {erro}", file=sys.stderr)
            status = 1
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origem", nargs="?", help="arquivo .zip ou pasta com fotos")
    parser.add_argument("--imovel", help="slug do imóvel para uma importação individual")
    parser.add_argument("--entrada", action="store_true", help="processa entrada-fotos/<slug>.zip e subpastas")
    parser.add_argument("--substituir", action="store_true", help="substitui as fotos já importadas")
    parser.add_argument("--dry-run", action="store_true", help="lista o que seria feito sem escrever arquivos")
    args = parser.parse_args(argv)
    try:
        if args.entrada:
            if args.origem or args.imovel:
                parser.error("--entrada não aceita origem nem --imovel")
            return processar_lote()
        if not args.origem or not args.imovel:
            parser.error("informe <arquivo.zip|pasta> e --imovel <slug>, ou use --entrada")
        return importar(Path(args.origem).resolve(), args.imovel, args.substituir, args.dry_run)
    except ImportErrorFotos as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
