"""Prepara vídeos locais para o site: MP4 H.264/AAC, sem GPS/metadados.

Uso: python importar_videos.py <pasta> --imovel <slug>
Originais preservados; exige destino vazio, usa ffmpeg/ffprobe existentes.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from importar_fotos import validar_slug

ROOT = Path(__file__).resolve().parent


def preparar(origem, slug):
    validar_slug(slug)
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise ValueError('ffmpeg e ffprobe precisam estar no PATH')
    base = (ROOT / 'dados/imoveis').resolve()
    destino = base / slug / 'videos-tratados'
    if not destino.resolve().is_relative_to(base):
        raise ValueError('Destino fora de dados/imoveis')
    if destino.exists() and any(destino.iterdir()):
        raise ValueError('Destino já contém vídeos; preserve-os e revise antes de substituir')
    fontes = sorted(p for p in Path(origem).rglob('*') if p.suffix.lower() in {'.mp4', '.mov'})
    if not fontes:
        raise ValueError('Nenhum vídeo encontrado')
    with tempfile.TemporaryDirectory(prefix='is-videos-') as temp:
        for n, fonte in enumerate(fontes, 1):
            saida = Path(temp) / f'{n:02d}-visita.mp4'
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                '-i', str(fonte), '-map', '0:v:0', '-map', '0:a:0?',
                '-map_metadata', '-1', '-map_chapters', '-1',
                '-vf', "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30",
                '-c:v', 'libx264', '-preset', 'medium', '-crf', '26', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart', str(saida)],
                check=True, capture_output=True)
            dados = json.loads(subprocess.run([ffprobe, '-v', 'error', '-show_format',
                '-show_streams', '-of', 'json', str(saida)], capture_output=True, text=True,
                check=True).stdout)
            # MP4 exige etiquetas técnicas de contêiner; rejeitar dados de origem.
            permitidas = {'major_brand', 'minor_version', 'compatible_brands', 'encoder',
                          'language', 'handler_name', 'vendor_id'}
            for objeto in [dados.get('format', {}), *dados.get('streams', [])]:
                if set(objeto.get('tags', {})) - permitidas:
                    raise ValueError('Metadados de origem permaneceram no vídeo')
            if any(s['codec_type'] not in {'video', 'audio'} for s in dados['streams']):
                raise ValueError('Stream de dados permaneceu no vídeo')
            if saida.stat().st_size > 40 * 1024 * 1024:
                raise ValueError('Vídeo acima de 40 MB; revisar compressão')
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', '0.5',
                '-i', str(saida), '-frames:v', '1', '-map_metadata', '-1', '-c:v', 'libwebp',
                '-quality', '75', str(saida.with_suffix('.webp'))], check=True, capture_output=True)
            print(f'{n:02d}: {float(dados["format"]["duration"]):.1f}s, {saida.stat().st_size // 1024} KB, metadados conferidos')
        destino.mkdir(parents=True, exist_ok=True)
        for arquivo in Path(temp).iterdir():
            shutil.copy2(arquivo, destino / arquivo.name)
    return len(fontes)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pasta')
    parser.add_argument('--imovel', required=True)
    args = parser.parse_args()
    print(f'{preparar(args.pasta, args.imovel)} vídeos preparados')
