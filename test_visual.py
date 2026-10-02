"""Regressões das fotos reais e do custo acessível; fixtures só em temporários."""
import tempfile
import unittest
from pathlib import Path
import build_site as b


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.imovel = dict(b.ler_imoveis()[0])
        self.corretor = b.ler_corretor()

    def test_sem_foto_nao_reserva_bloco(self):
        self.imovel.pop('_arquivo', None)
        self.assertEqual(b.galeria_carrossel(self.imovel), '')
        self.assertIn('card--sem-foto', b.card(self.imovel, self.corretor))
        self.assertNotIn('card-foto', b.card(self.imovel, self.corretor))
        self.assertEqual(b.retrato(self.corretor), '')

    def test_fotos_reais_ordenadas_alt_e_prioridade(self):
        with tempfile.TemporaryDirectory() as temp:
            pasta = Path(temp) / 'fotos-tratadas'
            pasta.mkdir()
            for nome in ('02.jpg', '01.webp', 'nao-foto.txt'):
                (pasta / nome).write_bytes(b'fixture de caminho, sem imagem publicada')
            self.imovel['_arquivo'] = Path(temp) / 'ficha.md'
            self.assertEqual([p.name for p in b.fotos_imovel(self.imovel)], ['01.webp', '02.jpg'])
            galeria = b.galeria_carrossel(self.imovel)
            self.assertEqual(galeria.count('fetchpriority="high"'), 1)
            self.assertEqual(galeria.count('loading="lazy"'), 1)
            self.assertIn('foto 1 de 2', galeria)
            self.assertIn('../assets/imoveis/', galeria)

    def test_conta_nao_duplica_inclusos_e_total_extenso(self):
        self.imovel.update(preco=1700, condominio=240, iptu=840, contas_inclusas=[])
        conta = b.conta(self.imovel)
        self.assertIn('Você paga por mês: dois mil e dez reais', conta)
        self.assertIn('<dt>IPTU ÷ 12</dt><dd>R$ 70</dd>', conta)
        self.imovel['contas_inclusas'] = ['condominio', 'iptu']
        self.assertIn('mil e setecentos reais', b.conta(self.imovel))
        self.assertEqual(b.conta(self.imovel).count('Incluso no aluguel'), 2)
        for atraso in (0, 130, 260, 390, 520):
            self.assertIn(f'--atraso:{atraso}ms', conta)

    def test_reservado_muda_cta_e_mensagem(self):
        self.imovel['situacao'] = 'reservado'
        self.assertIn('Avisar quando liberar', b.card(self.imovel, self.corretor))
        self.assertIn('quando%20liberar', b.wa_imovel(self.corretor, self.imovel))
        self.assertIn('quando%20liberar', b.wa_fixo(self.corretor, '', self.imovel))


if __name__ == '__main__':
    unittest.main()
