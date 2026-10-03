"""Testes do importador de fotos; arquivos são temporários e usam ffmpeg real."""
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import importar_fotos as imp


def exif_com_gps(jpeg: bytes) -> bytes:
    """Insere um bloco EXIF TIFF válido com latitude/longitude no JPEG."""
    inicio_gps = 26
    inicio_valores = inicio_gps + 2 + 5 * 12 + 4

    def entrada(tag, tipo, quantidade, valor):
        return struct.pack('<HHI', tag, tipo, quantidade) + valor

    ifd0 = struct.pack('<H', 1) + entrada(0x8825, 4, 1, struct.pack('<I', inicio_gps)) + b'\0\0\0\0'
    gps = struct.pack('<H', 5)
    gps += entrada(0x0000, 1, 4, b'\x02\x03\0\0')
    gps += entrada(0x0001, 2, 2, b'N\0\0\0')
    gps += entrada(0x0002, 5, 3, struct.pack('<I', inicio_valores))
    gps += entrada(0x0003, 2, 2, b'W\0\0\0')
    gps += entrada(0x0004, 5, 3, struct.pack('<I', inicio_valores + 24))
    gps += b'\0\0\0\0'
    racionais = b''.join(struct.pack('<II', n, 1) for n in (37, 46, 29, 122, 25, 9))
    tiff = b'II*\0' + struct.pack('<I', 8) + ifd0 + gps + racionais
    payload = b'Exif\0\0' + tiff
    segmento = b'\xff\xe1' + struct.pack('>H', len(payload) + 2) + payload
    return jpeg[:2] + segmento + jpeg[2:]


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe não instalados')
class ImportarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.temp.name)
        self.dados_original = imp.DADOS
        imp.DADOS = self.raiz / 'dados'
        shutil.copytree(self.dados_original / '_modelo', imp.DADOS / '_modelo')

    def tearDown(self):
        imp.DADOS = self.dados_original
        self.temp.cleanup()

    def gerar_jpg_gps(self, destino: Path, cor: str) -> None:
        base = destino.with_name(destino.stem + '-base.jpg')
        subprocess.run([
            shutil.which('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
            '-i', f'color=c={cor}:s=640x480', '-frames:v', '1', '-q:v', '2', '-y', str(base),
        ], check=True)
        destino.write_bytes(exif_com_gps(base.read_bytes()))
        base.unlink()

    def test_slug_invalido_recusado(self):
        with self.assertRaisesRegex(imp.ImportErrorFotos, 'slug inválido'):
            imp.validar_slug('../sala')

    def test_zip_slip_recusado(self):
        arquivo = self.raiz / 'malicioso.zip'
        with zipfile.ZipFile(arquivo, 'w') as pacote:
            pacote.writestr('../fora.jpg', b'nao extrair')
        with self.assertRaisesRegex(imp.ImportErrorFotos, 'zip-slip recusado'):
            imp.validar_zip(arquivo)

    def test_zip_gps_ordem_nomes_webp_e_rascunho(self):
        if not imp.tem_encoder_webp(shutil.which('ffmpeg')):
            self.skipTest('ffmpeg sem encoder libwebp')
        zip_path = self.raiz / 'album.zip'
        with zipfile.ZipFile(zip_path, 'w') as pacote:
            for nome, cor in [('Quarto.jpg', 'blue'), ('Fachada.jpg', 'red'), ('Sala.jpg', 'green')]:
                arquivo = self.raiz / nome
                self.gerar_jpg_gps(arquivo, cor)
                origem = arquivo.read_bytes()
                self.assertIn(b'Exif\0\0', origem)
                pacote.writestr(f'Fotos com espaço /{nome}', origem)

        self.assertEqual(imp.importar(zip_path, 'sala-centro-30m2'), 0)
        saida = imp.DADOS / 'imoveis' / 'sala-centro-30m2' / 'fotos-tratadas'
        fotos = sorted(saida.iterdir())
        self.assertEqual([p.name for p in fotos], [
            '01-fachada.webp', '02-quarto.webp', '03-sala.webp',
        ])
        for foto in fotos:
            self.assertLess(foto.stat().st_size, 500 * 1024)
            self.assertNotIn(b'Exif\0\0', foto.read_bytes())
            imp.verificar_sem_metadados(shutil.which('ffprobe'), foto)
        ficha = (saida.parent / 'ficha.md').read_text(encoding='utf-8')
        self.assertIn('rascunho: true', ficha)

    def test_nao_substitui_sem_flag(self):
        entrada = self.raiz / 'fotos'
        entrada.mkdir()
        saida = imp.DADOS / 'imoveis' / 'casa-centro' / 'fotos-tratadas'
        saida.mkdir(parents=True)
        (saida / '01-antiga.webp').write_bytes(b'antiga')
        with self.assertRaisesRegex(imp.ImportErrorFotos, 'use --substituir'):
            imp.importar(entrada, 'casa-centro')


if __name__ == '__main__':
    unittest.main(verbosity=2)
