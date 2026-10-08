import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_site as b
import notificar_busca as busca


class BuscaTests(unittest.TestCase):
    def test_recusa_urls_externas_e_parametros_e_paginas_privadas(self):
        for url in ['https://outro.example/imovel.html', '/?email=lead', '/obrigado.html', '/404.html', '/imovel/../privado']:
            with self.assertRaises(ValueError):
                busca.payload('https://imoveis.example/', '12345678', [url])
        dados = busca.payload('https://imoveis.example/', '12345678', ['/', '/', '/imoveis.html'])
        self.assertEqual(dados['urlList'], ['https://imoveis.example/', 'https://imoveis.example/imoveis.html'])

    def test_recusa_envio_quando_chave_publicada_nao_corresponde(self):
        with patch.object(busca, 'urlopen') as abrir:
            abrir.return_value.__enter__.return_value.read.return_value = b'outra-chave'
            with self.assertRaisesRegex(ValueError, 'deploy'):
                busca.enviar(busca.payload('https://imoveis.example/', '12345678', ['/']))
            self.assertEqual(abrir.call_count, 1)

    def test_duas_ofertas_na_mesma_ficha_e_video_sem_autoplay(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / 'ficha.md'
            arquivo.write_text('---\nslug: teste\ntitulo: Apartamento teste\noperacao: locacao\nfinalidade: residencial\ntipo: Apartamento\nbairro: Centro\ncidade: Feira de Santana\npreco: 3100\npreco_venda: 370000\ncontas_inclusas: condominio\niptu_nao_incluido: sim\n---\n', encoding='utf-8')
            imovel = b.ler_ficha(arquivo)
            videos = Path(pasta) / 'videos-tratados'
            videos.mkdir()
            (videos / '01.mp4').write_bytes(b'fixture')
            (videos / '01.webp').write_bytes(b'fixture')
            corretor = b.ler_corretor()
            documento = b.pagina_imovel(corretor, imovel, [imovel])
            self.assertEqual(b.custo_mensal(imovel), 3100)
            self.assertIn('Aluguel</span><span class="selo selo-venda">Venda', documento)
            self.assertIn('R$ 370.000', documento)
            self.assertIn('Não incluído', documento)
            self.assertIn('controls playsinline preload="none"', documento)
            self.assertNotIn('autoplay', documento)
            self.assertIn('Conversar sobre a compra', documento)
            self.assertNotIn('conta-mobile', documento)
            self.assertEqual(documento.count('<dt>Aluguel</dt>'), 1)
            catalogo = b.pagina_catalogo(corretor, [imovel])
            self.assertEqual(catalogo.count('<article class="card'), 1)


if __name__ == '__main__':
    unittest.main()
