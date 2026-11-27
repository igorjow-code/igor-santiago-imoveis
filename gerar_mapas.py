"""Gera a imagem fixa do mapa de cada bairro (decisão de Igor em 26/11/2026, IS-52).

A ficha do imóvel mostrava um quadro vivo do OpenStreetMap. Agora mostra uma imagem
do bairro, em cinza, com corte de telhado. Este script roda **uma vez por bairro**, na
máquina de quem mantém o site; o build não acessa a internet.

    python gerar_mapas.py            # gera só os mapas que faltam
    python gerar_mapas.py --refazer  # gera todos de novo

Saída: assets/mapas/<bairro>.webp (1280x960, em cinza). A imagem é centrada no ponto
aproximado do bairro (COORDENADAS_BAIRRO do build_site.py), nunca no endereço do imóvel.

Dados do mapa: (c) colaboradores do OpenStreetMap (ODbL). A página que usa a imagem
precisa manter o crédito visível (o build_site.py já escreve).
Requer ffmpeg no PATH; o restante usa apenas a biblioteca padrão.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import build_site as b

ZOOM = 15                 # ~3 km de largura: o bairro e o que há em volta
LARGURA, ALTURA = 640, 480   # recorte na escala do mapa; a saída sai com o dobro
LADRILHO = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
AGENTE = "static-map-builder/1.0"
PASTA = b.ASSETS / "mapas"


def ponto_global(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Latitude e longitude -> pixel na projeção do mapa (ladrilhos de 256 px)."""
    n = 256 * 2 ** zoom
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def baixar(url: str, destino: Path) -> None:
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(pedido, timeout=30) as resposta:
        destino.write_bytes(resposta.read())


def gerar(chave: str, lat: float, lon: float, destino: Path, ffmpeg: str) -> None:
    cx, cy = ponto_global(lat, lon, ZOOM)
    esquerda, topo = cx - LARGURA / 2, cy - ALTURA / 2
    x0, y0 = int(esquerda // 256), int(topo // 256)
    x1, y1 = int((esquerda + LARGURA - 1) // 256), int((topo + ALTURA - 1) // 256)
    colunas, linhas = x1 - x0 + 1, y1 - y0 + 1
    with tempfile.TemporaryDirectory() as temp:
        entradas, posicoes = [], []
        for linha in range(linhas):
            for coluna in range(colunas):
                arquivo = Path(temp) / f"{coluna}-{linha}.png"
                baixar(LADRILHO.format(z=ZOOM, x=x0 + coluna, y=y0 + linha), arquivo)
                time.sleep(.3)   # uso leve do servidor de ladrilhos
                entradas += ["-i", str(arquivo)]
                posicoes.append(f"{coluna * 256}_{linha * 256}")
        total = colunas * linhas
        juntar = "".join(f"[{n}:v]" for n in range(total)) + (
            f"xstack=inputs={total}:layout={'|'.join(posicoes)}" if total > 1 else "null")
        # cinza, com o chão claro e as ruas e quadras mais marcadas; depois dobra o tamanho
        filtro = (f"{juntar},crop={LARGURA}:{ALTURA}:{esquerda - x0 * 256:.0f}:{topo - y0 * 256:.0f},"
                  "format=gray,curves=all='0/0 0.70/0.42 0.86/0.70 0.95/0.93 1/1',"
                  f"scale={LARGURA * 2}:{ALTURA * 2}:flags=lanczos")
        comando = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *entradas,
                   "-filter_complex", filtro, "-frames:v", "1", "-c:v", "libwebp",
                   "-quality", "78", str(destino)]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode:
            raise RuntimeError(resultado.stderr.strip() or "ffmpeg não gerou o mapa")
    print(f"OK -> {destino.relative_to(b.ROOT)}  ({chave})")


def main(argv: list[str]) -> int:
    for saida in (sys.stdout, sys.stderr):
        if hasattr(saida, "reconfigure"):
            saida.reconfigure(encoding="utf-8")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg não encontrado no PATH.", file=sys.stderr)
        return 2
    PASTA.mkdir(parents=True, exist_ok=True)
    refazer = "--refazer" in argv
    for chave, (lat, lon) in b.COORDENADAS_BAIRRO.items():
        destino = b.mapa_bairro_arquivo(chave)
        if destino.exists() and not refazer:
            continue
        gerar(chave, lat, lon, destino, ffmpeg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
