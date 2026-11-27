"""Regressões do gerador; builds e alterações de fichas só em pasta temporária."""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from html import unescape
from pathlib import Path
from xml.etree import ElementTree

import build_site as b

FIXTURE_IMOVEIS = b.ROOT / 'tests' / 'fixtures' / 'imoveis'


def copiar_dados_teste(destino):
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copytree(b.DADOS / '_modelo', destino / '_modelo')
    corretor = b.ler_corretor()
    corretor.update(privacidade_revisada=False, email=b.PENDENTE,
                    creci_confirmado_por_igor=False, regime=b.PENDENTE,
                    foto=b.PENDENTE)
    (destino / 'corretor.json').write_text(
        json.dumps(corretor, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copytree(FIXTURE_IMOVEIS, destino / 'imoveis')


def ler_imoveis_fixture():
    imoveis = [b.ler_ficha(p) for p in sorted(FIXTURE_IMOVEIS.glob('*/ficha.md'))]
    imoveis.sort(key=lambda i: (i.get('operacao') != 'locacao',
                                i.get('preco', 0) if i.get('operacao') == 'locacao'
                                else -i.get('preco', 0)))
    return imoveis


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Os testes não devem depender dos dados pessoais atuais do perfil local.
        cls.corretor = dict(b.ler_corretor(), foto=b.PENDENTE,
                            creci_confirmado_por_igor=False, regime=b.PENDENTE)
        cls.imoveis = ler_imoveis_fixture()

    def ficha(self, pasta, texto):
        caminho = Path(pasta) / 'caso' / 'ficha.md'
        caminho.parent.mkdir(exist_ok=True)
        caminho.write_text('---\n' + texto + '\n---\n', encoding='utf-8')
        return caminho

    def test_aliases_inferencia_e_erros_nomeados(self):
        with tempfile.TemporaryDirectory() as pasta:
            for alias in ('aluguel', 'valor_aluguel'):
                caminho = self.ficha(pasta, f'{alias}: 1500\ntaxa_condominio: 100\ntipo: Sala comercial\ngarantias: fiador, caucao\ndisponivel_a_partir: 2026-10-01')
                ficha = b.ler_ficha(caminho)
                self.assertEqual((ficha['preco'], ficha['condominio'], ficha['finalidade']), (1500, 100, 'comercial'))
                self.assertEqual(ficha['garantias'], ['fiador', 'caucao'])
                self.assertEqual(ficha['disponivel_a_partir'], date(2026, 10, 1))
            for campo, valor in [('aluguel', 'R$ 1.500'), ('preco', 'R$ 1.500'), ('disponivel_a_partir', '2026-02-30')]:
                caminho = self.ficha(pasta, f'{campo}: {valor}')
                with self.assertRaises(ValueError) as erro:
                    b.ler_ficha(caminho)
                self.assertIn(str(caminho), str(erro.exception))
                self.assertIn(campo, str(erro.exception))
            caminho = self.ficha(pasta, 'preco: 1600\naluguel: 1500')
            with self.assertRaisesRegex(ValueError, 'conflitantes'):
                b.ler_ficha(caminho)

    def test_datas_expiradas_futuras_e_pendencias(self):
        hoje = date.today()
        imovel = dict(self.imoveis[0])
        imovel.update(disponivel_a_partir=hoje - timedelta(days=1))
        self.assertEqual(b.disponibilidade(imovel), '')
        self.assertTrue(any('disponivel_a_partir vencida' in p for p in b.pendencias(self.corretor, [imovel])))
        imovel['disponivel_a_partir'] = hoje + timedelta(days=1)
        self.assertIn(str(imovel['disponivel_a_partir'].year), b.disponibilidade(imovel))
        self.assertFalse(any('disponivel_a_partir vencida' in p for p in b.pendencias(self.corretor, [imovel])))
        for situacao in ('alugado', 'vendido'):
            imovel['situacao'] = situacao
            self.assertEqual(b.disponibilidade(imovel), '')
        self.assertEqual(b.data_br(date(2026, 10, 1)), '1º de outubro')

    def test_enum_invalido_nao_quebra_parser_e_bairro_sem_mapa_avisa(self):
        with tempfile.TemporaryDirectory() as pasta:
            texto = self.imoveis[0]['_arquivo'].read_text(encoding='utf-8')
            texto = texto.replace('situacao: disponivel', 'situacao: typo')
            caminho = Path(pasta) / 'ficha.md'
            caminho.write_text(texto, encoding='utf-8')
            imovel = b.ler_ficha(caminho)
            self.assertEqual(imovel['situacao'], 'typo')
            imovel['bairro'] = 'Bairro sem coordenada'
            faltas = b.pendencias(self.corretor, [imovel])
            self.assertTrue(any('situacao inválido' in p for p in faltas))
            self.assertTrue(any('bairro sem coordenadas' in p for p in faltas))

    def test_custo_sem_duplicar_contas_inclusas(self):
        imovel = {'preco': 1500, 'condominio': 200, 'iptu': 1201}
        for inclusas, esperado in [([], 1800), (['condominio'], 1600), (['iptu'], 1700), (['condominio', 'iptu', 'agua'], 1500)]:
            imovel['contas_inclusas'] = inclusas
            self.assertEqual(b.custo_mensal(imovel), esperado)

    def test_catalogo_ordenacao_e_specs_comerciais(self):
        alugueis = [i for i in self.imoveis if i['operacao'] == 'locacao']
        self.assertEqual(self.imoveis[:len(alugueis)], alugueis)
        self.assertEqual([i['preco'] for i in alugueis], sorted(i['preco'] for i in alugueis))
        vendas = self.imoveis[len(alugueis):]
        self.assertEqual([i['preco'] for i in vendas], sorted((i['preco'] for i in vendas), reverse=True))
        imovel = dict(self.imoveis[0], finalidade='comercial', quartos=3, suites=1)
        self.assertFalse({'Quartos', 'Suítes'} & {rotulo for rotulo, _ in b.specs(imovel)})
        self.assertIn('1 suíte', b.resumo(dict(self.imoveis[0], suites=1, finalidade='residencial')))

    def test_catalogo_publico_e_apenas_de_alugueis(self):
        # IS-42 (26/11/2026) trouxe a venda de volta ao site: o menu e o rodapé falam
        # de venda em toda página. O que continua valendo é a LISTA do catálogo de
        # aluguel não misturar imóvel à venda.
        documento = b.pagina_catalogo(self.corretor, self.imoveis, publicar=True)
        self.assertIn('Imóveis para alugar em Feira de Santana', documento)
        self.assertNotIn('data-operacao="venda"', documento)
        lista = documento.split('id="lista"', 1)[1].split('</section>', 1)[0]
        for imovel in self.imoveis:
            if imovel['operacao'] == 'venda':
                self.assertNotIn(imovel['slug'], lista)
        self.assertIn('Compra e venda de imóveis', b.jsonld(self.corretor, self.imoveis, 'imoveis.html', []))

    def test_capa_so_tem_venda_e_aluguel_fica_nas_paginas_de_aluguel(self):
        capa = b.pagina_home(self.corretor, self.imoveis)
        self.assertIn('pagina-capa', capa)
        self.assertNotIn('class="card', capa)
        self.assertNotIn('quero-alugar', capa)
        vendas = [i for i in self.imoveis if i['operacao'] == 'venda' or i.get('preco_venda')]
        alugueis = [i for i in self.imoveis if i['operacao'] == 'locacao' and not i.get('preco_venda')]
        self.assertTrue(vendas and alugueis)
        for imovel in vendas:
            self.assertIn(f'href="imovel/{imovel["slug"]}.html"', capa)
        for imovel in alugueis:
            self.assertNotIn(f'imovel/{imovel["slug"]}.html', capa)
        # a capa só aponta para o aluguel, com o menor custo calculado dos dados
        for finalidade, pagina in (('residencial', 'alugar-residencial.html'), ('comercial', 'alugar-sala-comercial.html')):
            menor, _ = b.menor_aluguel(self.imoveis, finalidade)
            self.assertIn(f'href="{pagina}"', capa)
            self.assertIn(b.moeda(menor), capa)
            segmento = b.pagina_segmento(self.corretor, self.imoveis, finalidade)
            self.assertIn('id="quero-alugar"', segmento)
            for imovel in alugueis:
                self.assertEqual(f'imovel/{imovel["slug"]}.html' in segmento, imovel['finalidade'] == finalidade)
        # ordem: do maior para o menor valor de venda
        posicoes = [capa.index(f'href="imovel/{i["slug"]}.html"') for i in b.a_venda(self.imoveis)]
        self.assertEqual(posicoes, sorted(posicoes))

    def test_capa_sem_foto_nao_prende_palco_nem_inventa_imagem(self):
        capa = b.pagina_home(self.corretor, self.imoveis)
        self.assertIn('abre--sem-foto', capa)
        self.assertNotIn('<image ', capa)
        self.assertNotIn('class="destaque"', capa)
        self.assertNotIn('class="linha-foto"', capa)
        self.assertIn('<h1 style="--larg:', capa)

    def test_capa_com_foto_passeio_e_tela_sem_movimento(self):
        with tempfile.TemporaryDirectory() as pasta:
            ficha = Path(pasta) / 'casa' / 'ficha.md'
            fotos = ficha.parent / 'fotos-tratadas'
            fotos.mkdir(parents=True)
            (fotos / '01-fachada.webp').write_bytes(
                b'RIFF\x00\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00' + b'\x00\x00\x00\x00'
                + (1209).to_bytes(3, 'little') + (1599).to_bytes(3, 'little'))
            casa = dict(next(i for i in self.imoveis if i['operacao'] == 'venda'),
                        slug='casa-teste', destaque=True, area=236.91, area_terreno=200,
                        passeio_url='https://passeio.example.invalid/', foco_capa='50% 46%',
                        _arquivo=ficha)
            capa = b.pagina_home(self.corretor, [casa] + self.imoveis)
            # com movimento: máscara SVG; sem movimento ou sem JS: a mesma foto num <img> comum
            self.assertIn('<img class="abre-foto" src="assets/imoveis/casa-teste/01-fachada.webp" width="1210" height="1600"', capa)
            self.assertIn('<image href="assets/imoveis/casa-teste/01-fachada.webp"', capa)
            self.assertIn('data-foto-l="1210" data-foto-a="1600" data-foco="50% 46%"', capa)
            self.assertIn('<link rel="preload" as="image" href="assets/imoveis/casa-teste/01-fachada.webp" fetchpriority="high" />', capa)
            self.assertIn('236,91 m² construídos · terreno de 200 m²', capa)
            self.assertEqual(capa.count('href="https://passeio.example.invalid/" target="_blank" rel="noopener"'), 3)
            pagina_ficha = b.pagina_imovel(self.corretor, casa, [casa])
            self.assertIn('href="https://passeio.example.invalid/"', pagina_ficha)
            self.assertIn('<span class="etiqueta">À venda</span>', pagina_ficha)
            self.assertNotIn('Para alugar', pagina_ficha)
            self.assertRegex(pagina_ficha, r'<title>[^<]* à venda[^<]*</title>')
        css = (b.ASSETS / 'styles.css').read_text(encoding='utf-8')
        # nada da capa nasce invisível fora do modo .js (movimento reduzido não recebe .js)
        capa_css = re.sub(r'/\*.*?\*/', '', css.split('CAPA — redesenho', 1)[1], flags=re.S)
        achadas = 0
        for regra in re.findall(r'([^{}]+)\{([^{}]*opacity:\s*0[;\s}][^{}]*)\}', capa_css):
            seletores = [s.strip() for s in regra[0].split(',')]
            if all(re.fullmatch(r'from|to|[\d.]+%', s) for s in seletores):
                continue  # passo de @keyframes: só roda dentro de regra .js
            achadas += 1
            self.assertTrue(all(s.startswith('.js ') or '.nav' in s or '.topo' in s for s in seletores), regra[0])
        self.assertGreater(achadas, 3)

    def test_comprar_lista_so_o_que_esta_a_venda_com_a_pele_nova(self):
        pagina = b.pagina_comprar(self.corretor, self.imoveis)
        self.assertIn('class="pagina-capa pagina-interna pagina-comprar"', pagina)
        self.assertNotIn('class="card', pagina)
        self.assertIn('<a href="comprar.html" class="ativo">Comprar</a>', pagina)
        vendas = b.a_venda(self.imoveis)
        alugueis = [i for i in self.imoveis if i['operacao'] == 'locacao' and not i.get('preco_venda')]
        self.assertTrue(vendas and alugueis)
        for imovel in vendas:
            self.assertIn(f'id="v-{imovel["slug"]}"', pagina)
            self.assertIn(f'href="imovel/{imovel["slug"]}.html"', pagina)
            self.assertIn(b.moeda(b.valor_venda(imovel)), pagina)
        for imovel in alugueis:
            self.assertNotIn(f'imovel/{imovel["slug"]}.html', pagina)
        posicoes = [pagina.index(f'id="v-{i["slug"]}"') for i in vendas]
        self.assertEqual(posicoes, sorted(posicoes))
        # o menu e o rodapé de toda página apontam para a página nova
        capa = b.pagina_home(self.corretor, self.imoveis)
        self.assertIn('<a href="comprar.html">Comprar</a>', capa)
        self.assertNotIn('index.html#a-venda', capa)
        # dados estruturados: a lista e o serviço de venda moram em comprar.html
        grafo = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', pagina, re.S)[1])['@graph']
        lista = next(no for no in grafo if no['@type'] == 'ItemList')
        self.assertEqual(lista['numberOfItems'], len(vendas))
        self.assertEqual([i['url'].rsplit('/', 1)[1] for i in lista['itemListElement']],
                         [f'{i["slug"]}.html' for i in vendas])
        etapas = next(no for no in grafo if no['@type'] == 'HowTo')['step']
        visiveis = re.findall(r'<li class="etapa"[^>]*><span class="etapa-n">\d\d</span><h3>(.*?)</h3><p>(.*?)</p></li>', pagina)
        self.assertEqual([(unescape(n), unescape(x)) for n, x in visiveis], [(s['name'], s['text']) for s in etapas])
        self.assertEqual(len(etapas), 4)
        servico = next(no for no in grafo if no['@id'].endswith('/#venda'))
        self.assertTrue(servico['url'].endswith('/comprar.html'))
        # CRECI na página, além do rodapé
        self.assertGreaterEqual(pagina.count(self.corretor['creci']), 3)

    def test_comprar_cartaz_com_passeio_sem_passeio_e_pagina_vazia(self):
        with tempfile.TemporaryDirectory() as pasta:
            ficha = Path(pasta) / 'casa' / 'ficha.md'
            fotos = ficha.parent / 'fotos-tratadas'
            fotos.mkdir(parents=True)
            for nome in ('01-fachada', '02-sala', '03-cozinha', '04-suite', '05-piscina'):
                (fotos / f'{nome}.webp').write_bytes(
                    b'RIFF\x00\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00' + b'\x00\x00\x00\x00'
                    + (1209).to_bytes(3, 'little') + (1599).to_bytes(3, 'little'))
            base = next(i for i in self.imoveis if i['operacao'] == 'venda')
            casa = dict(base, slug='casa-teste', destaque=True, area=236.91, area_terreno=200,
                        passeio_url='https://passeio.example.invalid/', fotos_cartaz=['05', '03', '02'],
                        _arquivo=ficha)
            cartaz = b.cartaz_imovel(self.corretor, casa)
            self.assertIn('cartaz--destaque', cartaz)
            self.assertIn('cartaz--com-trio', cartaz)
            self.assertEqual(cartaz.count('class="vitrine-quadro"'), 3)
            # as três fotos de dentro saem na ordem pedida na ficha, e nunca repetem a fachada
            ordem = re.findall(r'casa-teste/(\d\d)-', cartaz.split('class="vitrine"', 1)[1])
            self.assertEqual(ordem, ['05', '03', '02'])
            self.assertIn('5 fotos reais na ficha', cartaz)
            self.assertEqual(cartaz.count('href="https://passeio.example.invalid/" target="_blank" rel="noopener"'), 2)
            # o botão cheio é o passo mais rico (passeio); o de contorno é sempre a visita
            self.assertIn('>Passear pela casa</a><a class="bt bt-fino" href="https://wa.me/', cartaz)
            self.assertIn('>Agendar visita</a>', cartaz)
            self.assertIn('<span class="etiqueta"', cartaz)
            self.assertNotIn('À venda ·', cartaz)   # a página já diz "à venda" no título
            self.assertIn('<dt>Área construída</dt><dd>236,91 m²</dd>', cartaz)
            self.assertEqual(cartaz.count('fetchpriority="high"'), 1)
            self.assertEqual(b.cartaz_imovel(self.corretor, casa, 1).count('fetchpriority="high"'), 0)
            # sem passeio: a ficha é o passo principal e a visita vai para o WhatsApp
            sem = b.cartaz_imovel(self.corretor, dict(casa, passeio_url=''))
            self.assertNotIn('vitrine', sem)
            self.assertIn('>Ver a ficha · 5 fotos</a><a class="bt bt-fino" href="https://wa.me/', sem)
            self.assertNotIn('cartaz-legenda', sem)   # um caminho só para a ficha
            self.assertIn('>Agendar visita</a>', sem)
            pagina = b.pagina_comprar(self.corretor, [casa] + self.imoveis)
            self.assertIn('Onde há passeio', pagina)
            self.assertIn('<link rel="preload" as="image" href="assets/imoveis/casa-teste/01-fachada.webp" fetchpriority="high" />', pagina)
        # imóvel sem foto não reserva bloco de imagem
        sem_foto = b.cartaz_imovel(self.corretor, dict(base, _arquivo=None))
        self.assertIn('cartaz--sem-foto', sem_foto)
        self.assertNotIn('<img', sem_foto)
        # catálogo sem nada à venda: a página existe, diz isso e mantém o convite
        alugueis = [i for i in self.imoveis if i['operacao'] == 'locacao' and not i.get('preco_venda')]
        vazia = b.pagina_comprar(self.corretor, alugueis)
        self.assertIn('Nenhum imóvel à venda publicado', vazia)
        self.assertNotIn('class="cartaz', vazia)
        self.assertNotIn('"ItemList"', vazia)
        self.assertNotIn('Onde há passeio', vazia)
        self.assertIn('class="bloco fecho"', vazia)

    def test_ficha_com_a_pele_nova_tira_folha_e_passeio(self):
        with tempfile.TemporaryDirectory() as pasta:
            ficha = Path(pasta) / 'casa' / 'ficha.md'
            fotos = ficha.parent / 'fotos-tratadas'
            fotos.mkdir(parents=True)
            for nome, (largura, altura) in (('01-fachada', (1210, 1600)), ('02-sala', (1448, 1086)),
                                            ('03-cozinha', (900, 1600)), ('04-suite', (1200, 1600))):
                (fotos / f'{nome}.webp').write_bytes(
                    b'RIFF\x00\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00' + b'\x00\x00\x00\x00'
                    + (largura - 1).to_bytes(3, 'little') + (altura - 1).to_bytes(3, 'little'))
            base = next(i for i in self.imoveis if i['operacao'] == 'venda')
            casa = dict(base, slug='casa-teste', tipo='Casa', titulo='Casa de 4 suítes no Jardim Teste',
                        nome_curto='Jardim Teste', passeio_url='https://passeio.example.invalid/',
                        fotos_cartaz=['04', '03', '02'], _arquivo=ficha)
            pagina = b.pagina_imovel(self.corretor, casa, [casa])
            self.assertIn('class="pagina-capa pagina-interna pagina-ficha"', pagina)
            for antiga in ('imovel-carrossel', 'recibo-ficha', 'class="selo', 'class="btn btn-principal"'):
                self.assertNotIn(antiga, pagina)
            # menu, trilha visível e trilha dos dados estruturados apontam para a mesma lista
            self.assertIn('<a href="../comprar.html" class="ativo">Comprar</a>', pagina)
            self.assertIn('<a href="../comprar.html">Comprar</a><i aria-hidden="true">/</i><span>Jardim Teste</span>', pagina)
            grafo = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', pagina, re.S)[1])['@graph']
            trilha = next(no for no in grafo if no['@type'] == 'BreadcrumbList')['itemListElement']
            self.assertTrue(trilha[1]['item'].endswith('/comprar.html'))
            self.assertEqual(trilha[2]['name'], 'Jardim Teste')
            # o nome grande e o título inteiro moram no mesmo <h1>
            h1 = re.search(r'<h1 class="ficha-h1"[^>]*>(.*?)</h1>', pagina, re.S)[1]
            self.assertIn('Jardim Teste', h1)
            self.assertIn('Casa de 4 suítes no Jardim Teste', h1)
            self.assertEqual(pagina.count('<h1'), 1)
            # a tira: cada foto na proporção em que foi tirada, a primeira com prioridade
            tira = pagina.split('data-tira', 1)[1].split('class="tira-pe"', 1)[0]
            self.assertEqual(re.findall(r'--r:([\d.]+)', tira), ['0.7562', '1.3333', '0.5625', '0.7500', '.75'])
            self.assertEqual(tira.count('fetchpriority="high"'), 1)
            self.assertEqual(tira.count('loading="lazy"'), 3)
            self.assertIn('foto 4 de 4', tira)
            self.assertIn('<link rel="preload" as="image" href="../assets/imoveis/casa-teste/01-fachada.webp" fetchpriority="high" />', pagina)
            # o botão cheio é o passo mais rico (passeio); o fim da tira e a faixa levam ao mesmo lugar
            self.assertIn('>Passear pela casa</a><a class="bt bt-fino" href="https://wa.me/', pagina)
            self.assertEqual(pagina.count('href="https://passeio.example.invalid/" target="_blank" rel="noopener"'), 3)
            self.assertIn('class="tira-quadro tira-fim"', tira)
            # a faixa do passeio não repete as fotos que a pessoa acabou de ver na tira
            self.assertIn('id="passeio"', pagina)
            self.assertNotIn('vitrine-quadro', pagina)
            # venda: a folha mostra o valor, não uma conta de aluguel
            self.assertIn('<p class="valor-rotulo" data-reveal>Valor de venda</p>', pagina)
            self.assertNotIn('conta-linha', pagina)
            self.assertIn(b.moeda(casa['preco']), pagina)
            # dúvidas visíveis iguais às dos dados estruturados; CRECI além do rodapé
            faq = next(no for no in grafo if no['@type'] == 'FAQPage')['mainEntity']
            visiveis = re.findall(r'<details class="duvida"><summary>(.*?)</summary><p>(.*?)</p></details>', pagina, re.S)
            self.assertEqual([(unescape(p), unescape(r)) for p, r in visiveis],
                             [(p['name'], p['acceptedAnswer']['text']) for p in faq])
            self.assertGreaterEqual(pagina.count(self.corretor['creci']), 3)
            # sem passeio: a visita é o passo principal, no topo e no fim da tira
            sem = b.pagina_imovel(self.corretor, dict(casa, passeio_url=''), [casa])
            self.assertNotIn('passeio.example.invalid', sem)
            self.assertNotIn('id="passeio"', sem)
            self.assertIn('<div class="acoes ficha-acoes"><a class="bt bt-cheio" href="https://wa.me/', sem)
            self.assertIn('Agora,<br />de perto.', sem)
            # reservado: nenhum convite de visita; a conversa é para ser avisado
            reservado = b.pagina_imovel(self.corretor, dict(casa, passeio_url='', situacao='reservado'), [casa])
            self.assertIn('<span class="etiqueta">Reservado</span>', reservado)
            self.assertNotIn('tira-fim', reservado)
            self.assertNotIn('Agendar visita', reservado)
            self.assertIn('quando%20liberar', reservado)
        # aluguel: a conta soma até o custo mensal, e a barra do celular diz o que acontece
        aluguel = dict(next(i for i in self.imoveis if i['operacao'] == 'locacao' and i['finalidade'] == 'residencial'),
                       preco=1700, condominio=240, iptu=840, contas_inclusas=[], _arquivo=None)
        pagina = b.pagina_imovel(self.corretor, aluguel, [aluguel])
        self.assertIn('<span class="etiqueta">Aluguel</span>', pagina)
        self.assertIn('<a href="../alugar-residencial.html" class="ativo">Alugar</a>', pagina)
        self.assertIn('data-total="2010" data-parcelas="3"', pagina)
        self.assertIn('IPTU dividido por 12', pagina)
        # sem parcela além do aluguel não há soma para animar nem nota sobre IPTU dividido
        so_aluguel = b.conta(dict(aluguel, contas_inclusas=['condominio'], iptu=0, iptu_nao_incluido='sim'))
        self.assertIn('data-parcelas="1"', so_aluguel)
        self.assertNotIn('IPTU dividido por 12', so_aluguel)
        self.assertIn('R$ 2.010/mês com os encargos informados', pagina)
        self.assertIn('<a class="bt bt-fino" href="#conta">Ver a conta do mês</a>', pagina)
        self.assertIn('>Agendar visita</a></div>', pagina.split('class="barra-mobile"', 1)[1])
        # sem foto não existe tira nem imagem de imóvel reservada
        self.assertIn('ficha-topo--sem-foto', pagina)
        self.assertNotIn('data-tira', pagina)
        comercial = dict(next(i for i in self.imoveis if i['finalidade'] == 'comercial'), _arquivo=None)
        self.assertIn('<a href="../alugar-sala-comercial.html" class="ativo">Comercial</a>',
                      b.pagina_imovel(self.corretor, comercial, [comercial]))
        self.assertEqual(b.partir_nome('Parque Fonte das Águas'), ('Parque Fonte', 'das Águas'))
        self.assertEqual(b.partir_nome('Terra Azul'), ('Terra Azul',))
        # nada da ficha nasce invisível fora do modo .js (movimento reduzido não recebe .js)
        css = (b.ASSETS / 'styles.css').read_text(encoding='utf-8')
        ficha_css = re.sub(r'/\*.*?\*/', '', css.split('FICHA DO IMÓVEL', 1)[1], flags=re.S)
        achadas = 0
        for regra in re.findall(r'([^{}]+)\{([^{}]*(?:opacity:\s*0[;\s}]|scale[XY]\(0\))[^{}]*)\}', ficha_css):
            seletores = [s.strip() for s in regra[0].split(',')]
            if all(re.fullmatch(r'from|to|[\d.]+%', s) for s in seletores):
                continue
            achadas += 1
            # fora do .js só o fundo laranja do último quadro (que enche no toque) começa recolhido
            self.assertTrue(all(s.startswith('.js ') or s == '.tira-fim a::before' for s in seletores), regra[0])
        self.assertGreater(achadas, 3)

    def test_metragem_com_virgula_e_valor_de_venda(self):
        with tempfile.TemporaryDirectory() as pasta:
            ficha = b.ler_ficha(self.ficha(pasta, 'area: 236,91\narea_terreno: 200\npreco: 1600000\noperacao: venda\ntipo: Casa'))
            self.assertEqual((ficha['area'], ficha['area_terreno']), (236.91, 200))
            self.assertEqual(b.metragem(ficha['area']), '236,91')
            self.assertEqual(b.metragem(ficha['area_terreno']), '200')
            self.assertIn(('Área construída', '236,91 m²'), b.specs(ficha))
            self.assertEqual(b.valor_venda(ficha), 1600000)
            with self.assertRaises(ValueError):
                b.ler_ficha(self.ficha(pasta, 'preco: 1600,50'))

    def test_metadata_social_e_canonical_da_home(self):
        home = b.pagina_home(self.corretor, self.imoveis, publicar=True)
        self.assertIn('<link rel="canonical" href="https://igorsantiagoimoveis.com.br/" />', home)
        self.assertIn('<meta property="og:url" content="https://igorsantiagoimoveis.com.br/" />', home)
        self.assertIn('<meta name="twitter:card" content="summary_large_image" />', home)
        self.assertNotIn('fonts.googleapis.com', home)
        self.assertIn('Apartamento ou casa acima de R$ 3.000', b.formulario_lead(
            dict(self.corretor, privacidade_revisada=True, email='qa@example.invalid'), True))

    def test_dimensoes_png_jpeg_webp_e_reserva_de_layout(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            png = raiz / 'foto.png'
            png.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR'
                            + (565).to_bytes(4, 'big') + (640).to_bytes(4, 'big'))
            jpeg = raiz / 'foto.jpg'
            jpeg.write_bytes(b'\xff\xd8\xff\xc0\x00\x07\x08\x02\x58\x03\x20')
            webp = raiz / 'foto.webp'
            webp.write_bytes(b'RIFF\x00\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00'
                             + b'\x00\x00\x00\x00' + (799).to_bytes(3, 'little')
                             + (599).to_bytes(3, 'little'))
            self.assertEqual(b.dimensoes_imagem(png), (565, 640))
            self.assertEqual(b.dimensoes_imagem(jpeg), (800, 600))
            self.assertEqual(b.dimensoes_imagem(webp), (800, 600))

            pasta_fotos = raiz / 'imovel' / 'fotos-tratadas'
            pasta_fotos.mkdir(parents=True)
            shutil.copy2(png, pasta_fotos / '01-capa.png')
            ficha = dict(self.imoveis[0], _arquivo=pasta_fotos.parent / 'ficha.md')
            html = b.card(ficha, self.corretor)
            self.assertIn('width="565" height="640"', html)
            miniaturas = pasta_fotos / '_miniaturas'
            miniaturas.mkdir()
            (miniaturas / 'capa.webp').write_bytes(b'capa otimizada')
            html = b.card(ficha, self.corretor)
            self.assertIn('assets/imoveis/' + ficha['slug'] + '/capa.webp', html)

    def test_rascunhos_fora_do_build_e_listados_no_check(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            copiar_dados_teste(raiz / 'dados')
            ficha = raiz / 'dados' / 'imoveis' / 'novo-imovel' / 'ficha.md'
            ficha.parent.mkdir()
            shutil.copy2(b.DADOS / '_modelo' / 'ficha.md', ficha)
            shutil.copy2(b.ROOT / 'build_site.py', raiz / 'build_site.py')
            imoveis = b.ler_imoveis()
            self.assertNotIn('novo-imovel', [i['slug'] for i in imoveis])
            check = subprocess.run([sys.executable, str(raiz / 'build_site.py'), '--check'],
                                   capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn('novo-imovel/ficha.md → rascunho — falta revisar ficha', check.stdout)
            # A leitura do modo --check inclui o rascunho para explicar o bloqueio.
            orig_dados = b.DADOS
            try:
                b.DADOS = raiz / 'dados'
                lidos = b.ler_imoveis(incluir_rascunhos=True)
                self.assertNotIn('__modelo__', [i['slug'] for i in lidos])
                self.assertTrue(any('rascunho — falta revisar ficha' in p
                                    for p in b.pendencias(self.corretor, lidos)))
            finally:
                b.DADOS = orig_dados

    def test_previa_compila_sem_imoveis_publicaveis(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            shutil.copy2(b.ROOT / 'build_site.py', raiz / 'build_site.py')
            shutil.copytree(b.ASSETS, raiz / 'assets')
            (raiz / 'dados' / '_modelo').mkdir(parents=True)
            shutil.copy2(b.DADOS / '_modelo' / 'ficha.md', raiz / 'dados' / '_modelo' / 'ficha.md')
            shutil.copy2(b.DADOS / 'corretor.json', raiz / 'dados' / 'corretor.json')
            ficha = raiz / 'dados' / 'imoveis' / 'unico-rascunho' / 'ficha.md'
            ficha.parent.mkdir(parents=True)
            ficha.write_text(
                (raiz / 'dados' / '_modelo' / 'ficha.md').read_text(encoding='utf-8')
                .replace('slug: __PREENCHER__', 'slug: unico-rascunho'),
                encoding='utf-8')

            resultado = subprocess.run([sys.executable, str(raiz / 'build_site.py')],
                                       capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            self.assertTrue((raiz / 'publico' / 'index.html').is_file())
            self.assertFalse((raiz / 'publico' / 'imovel' / 'unico-rascunho.html').exists())

    def test_formulario_exige_tres_gates(self):
        for publicar in (False, True):
            for revisada in (False, True, 'true'):
                for email in ('', b.PENDENTE, 'teste@example.invalid'):
                    corretor = dict(self.corretor, privacidade_revisada=revisada, email=email)
                    documento = b.formulario_lead(corretor, publicar)
                    ativo = publicar and revisada is True and email == 'teste@example.invalid'
                    self.assertEqual('<form ' in documento, ativo)
                    self.assertEqual('data-netlify=' in documento, ativo)
                    campos = re.findall(r'<(?:input|select|button)\b[^>]*>', documento)
                    self.assertTrue(campos)
                    self.assertTrue(all(('disabled' in campo) != ativo for campo in campos))
                    if ativo:
                        self.assertIn('name="form-name" value="quero-alugar"', documento)
                        self.assertIn('netlify-honeypot="bot-field"', documento)
                        self.assertIn('action="/obrigado.html"', documento)

    def test_faq_visivel_igual_jsonld(self):
        documentos = [b.pagina_home(self.corretor, self.imoveis), b.pagina_comprar(self.corretor, self.imoveis)] + [b.pagina_segmento(self.corretor, self.imoveis, segmento) for segmento in ('comercial', 'residencial')]
        for documento in documentos:
            grafo = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', documento, re.S)[1])['@graph']
            faq = next(no for no in grafo if no['@type'] == 'FAQPage')['mainEntity']
            visiveis = re.findall(r'<details class="duvida"><summary>(.*?)</summary><p>(.*?)</p></details>', documento, re.S)
            self.assertEqual([(unescape(p), unescape(r)) for p, r in visiveis], [(p['name'], p['acceptedAnswer']['text']) for p in faq])

    def test_privacidade_descreve_o_estado_real_do_formulario(self):
        for publicar in (False, True):
            c = dict(self.corretor, privacidade_revisada=True, email='qa@example.invalid')
            documento = b.pagina_privacidade(c, self.imoveis, publicar=publicar)
            self.assertEqual('Nesta prévia ele está desativado' in documento, not publicar)
            self.assertEqual('Rascunho — aguarda revisão jurídica' in documento, not publicar)

    def test_consentimento_alerta_privado_e_versao_registrada(self):
        c = dict(self.corretor, privacidade_revisada=True, email='qa@example.invalid')
        documento = b.formulario_lead(c, publicar=True)
        self.assertIn('name="privacidade-versao" value="2026-10-05-telegram-v1"', documento)
        self.assertIn('name="consentimento" required', documento)
        self.assertIn('alerta privado de atendimento no Telegram', documento)
        policy = b.pagina_privacidade(c, self.imoveis, publicar=True)
        self.assertIn('GitHub Actions', policy)
        self.assertIn('mensagens do Telegram', policy)
        self.assertIn('O alerta não contém o e-mail bruto, IP', policy)

    def test_builds_isolados_gates_seo_e_sitemap(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            shutil.copy2(b.ROOT / 'build_site.py', raiz)
            copiar_dados_teste(raiz / 'dados')
            shutil.copytree(b.ASSETS, raiz / 'assets')
            rascunho = raiz / 'dados' / 'imoveis' / 'rascunho-interno' / 'ficha.md'
            rascunho.parent.mkdir()
            shutil.copy2(raiz / 'dados' / '_modelo' / 'ficha.md', rascunho)
            rascunho.write_text(rascunho.read_text(encoding='utf-8').replace(
                'slug: __PREENCHER__', 'slug: rascunho-interno'), encoding='utf-8')

            def executar(*args):
                return subprocess.run([sys.executable, str(raiz / 'build_site.py'), *args], capture_output=True, text=True, encoding='utf-8')

            def hashes():
                return {p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in (raiz / 'publico').rglob('*') if p.is_file()}

            resultado = executar()
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            saida = raiz / 'publico'
            for p in saida.rglob('*.html'):
                documento = p.read_text(encoding='utf-8')
                self.assertIn('noindex, nofollow', documento, str(p))
                self.assertIn('CRECI-BA 28.140', documento, str(p))
                for bloco in re.findall(r'<script type="application/ld\+json">(.*?)</script>', documento, re.S):
                    self.assertTrue(json.loads(bloco)['@graph'])
            self.assertEqual((saida / 'robots.txt').read_text(), 'User-agent: *\nDisallow: /\n')
            antes = hashes()
            recusado = executar('--publicar')
            self.assertEqual(recusado.returncode, 2)
            self.assertIn('RECUSADO', recusado.stderr)
            self.assertEqual(hashes(), antes)

            # Simulação de dados reais exclusivamente na cópia temporária.
            for p in (raiz / 'dados' / 'imoveis').glob('*/ficha.md'):
                p.write_text(p.read_text(encoding='utf-8').replace('demo: true', 'demo: false'), encoding='utf-8')
            recusado = executar('--publicar')
            self.assertEqual(recusado.returncode, 2)
            self.assertIn('B3/B5', recusado.stderr)
            self.assertEqual(hashes(), antes)
            corretor = dict(self.corretor, privacidade_revisada=True, email='teste@example.invalid',
                            creci_confirmado_por_igor=True, regime='autônomo', foto='assets/retrato.jpg')
            (raiz / 'dados' / 'corretor.json').write_text(json.dumps(corretor), encoding='utf-8')
            (raiz / 'assets' / 'retrato.jpg').write_bytes(b'retrato de teste')
            # A publicação só passa quando existe ao menos uma ficha real revisada.
            ficha_real = next((raiz / 'dados' / 'imoveis').glob('*/ficha.md'))
            ficha_real.write_text(ficha_real.read_text(encoding='utf-8').replace('demo: true', 'demo: false'), encoding='utf-8')
            resultado = executar('--publicar')
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            for p in saida.rglob('*.html'):
                documento = p.read_text(encoding='utf-8')
                self.assertIn('noindex, nofollow' if p.name in {'404.html', 'obrigado.html'} else 'content="index, follow"', documento, str(p))
                self.assertIn('<link rel="canonical"', documento)
                self.assertNotIn('fonts.googleapis.com', documento)
            # o formulário de aluguel saiu da capa (capa só venda, IS-43) e mora nas páginas de aluguel
            self.assertIn('data-netlify="true"', (saida / 'alugar-residencial.html').read_text(encoding='utf-8'))
            home = (saida / 'index.html').read_text(encoding='utf-8')
            self.assertNotIn('data-netlify', home)
            # todo endereço que existia antes do redesenho continua existindo
            for antiga in ('index.html', 'imoveis.html', 'alugar-residencial.html', 'alugar-sala-comercial.html',
                           'administracao.html', 'sobre.html', 'privacidade.html', 'obrigado.html', '404.html'):
                self.assertTrue((saida / antiga).is_file(), antiga)
            # nenhum link interno da capa aponta para página que o build não gerou
            for href in re.findall(r'href="([^"#:]+\.html)(?:#[^"]*)?"', home):
                self.assertTrue((saida / href).is_file(), href)
            self.assertIn('<link rel="canonical" href="https://igorsantiagoimoveis.com.br/" />', home)
            self.assertIn('<meta property="og:image"', home)
            catalogo = (saida / 'imoveis.html').read_text(encoding='utf-8')
            self.assertIn('Imóveis para alugar em Feira de Santana', catalogo)
            self.assertNotIn('Vender meu imóvel', catalogo)
            self.assertFalse((saida / 'vender.html').exists())
            robots = (saida / 'robots.txt').read_text()
            for agente in ('*', 'GPTBot', 'OAI-SearchBot', 'ClaudeBot', 'PerplexityBot', 'Google-Extended'):
                self.assertIn(f'User-agent: {agente}\nAllow: /', robots)
            sitemap = ElementTree.parse(saida / 'sitemap.xml')
            ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            base = corretor['site_url'].rstrip('/') + '/'
            urls = {n.text.removeprefix(base) for n in sitemap.findall('.//s:loc', ns)}
            paginas = {'' if p.name == 'index.html' else p.relative_to(saida).as_posix()
                       for p in saida.rglob('*.html') if p.name not in {'404.html', 'obrigado.html'}}
            self.assertEqual(urls, paginas)
            self.assertNotIn('imovel/rascunho-interno/index.html', paginas)
            self.assertEqual(len(sitemap.findall('.//s:lastmod', ns)), len(paginas))
            lastmods = {url.find('s:loc', ns).text: url.find('s:lastmod', ns).text
                        for url in sitemap.findall('.//s:url', ns)}
            for p in (saida / 'imovel').glob('*.html'):
                documento = p.read_text(encoding='utf-8')
                dados_jsonld = [json.loads(bloco) for bloco in re.findall(
                    r'<script type="application/ld\+json">(.*?)</script>', documento, re.S)]
                grafo = [obj for dados in dados_jsonld for obj in dados['@graph']]
                anuncio = next(obj for obj in grafo if obj.get('@type') == 'RealEstateListing')
                self.assertEqual(anuncio['offers']['@type'], 'Offer')
                self.assertEqual(anuncio['offers']['priceCurrency'], 'BRL')
                self.assertEqual(anuncio['offers']['itemOffered']['address']['addressLocality'], 'Feira de Santana')
                self.assertNotIn('streetAddress', json.dumps(anuncio, ensure_ascii=False))
                self.assertTrue(any(obj.get('@type') == 'BreadcrumbList' for obj in grafo))
            repetido = executar()
            self.assertEqual(repetido.returncode, 0, repetido.stderr)
            sitemap_repetido = ElementTree.parse(saida / 'sitemap.xml')
            lastmods_repetidos = {url.find('s:loc', ns).text: url.find('s:lastmod', ns).text
                                  for url in sitemap_repetido.findall('.//s:url', ns)}
            self.assertEqual(lastmods_repetidos, lastmods)

    def test_jsonld_agent_area_sameas_listing_sem_area_referencial(self):
        imovel = dict(self.imoveis[0], slug='santana-flex', titulo='Apartamento no Santana Flex',
                      bairro='Capuchinhos', cidade='Feira de Santana', area=None,
                      area_referencia='48,98 m² de planta padrão', quartos=1, vagas=1,
                      _arquivo=Path('ficha.md'))
        dados = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',
                                    b.jsonld(self.corretor, [imovel], 'imovel/santana-flex.html', []), re.S).group(1))
        agente = next(item for item in dados['@graph'] if item['@type'] == 'RealEstateAgent')
        self.assertEqual(agente['areaServed'], self.corretor['atuacao'])
        self.assertIn('https://www.instagram.com/igorsantiagoimoveis/', agente['sameAs'])
        anuncio = next(item for item in dados['@graph'] if item['@type'] == 'RealEstateListing')
        self.assertNotIn('floorSize', anuncio['mainEntity'])
        self.assertNotIn('streetAddress', json.dumps(dados, ensure_ascii=False))
        self.assertIn('logo', agente)
        self.assertIn('image', agente)

    def test_titulo_ficha_usa_predio_bairro_cidade_e_preco(self):
        imovel = dict(self.imoveis[0], tipo='Apartamento',
                      titulo='Apartamento mobiliado de 1 quarto no Santana Flex, Capuchinhos',
                      bairro='Capuchinhos', cidade='Feira de Santana', preco=3100,
                      slug='santana-flex', _arquivo=Path('ficha.md'))
        html = b.pagina_imovel(self.corretor, imovel, [imovel])
        self.assertIn('<title>Aluguel Apartamento Santana Flex – Capuchinhos, Feira de Santana | R$ 3.100</title>', html)

    def test_fontes_locais_e_preload_da_capa(self):
        css = (b.ASSETS / 'styles.css').read_text(encoding='utf-8')
        self.assertIn('url("fonts/manrope-latin.woff2")', css)
        self.assertIn('url("fonts/archivo-latin.woff2")', css)
        with tempfile.TemporaryDirectory() as pasta:
            ficha = Path(pasta) / 'apartamento' / 'ficha.md'
            fotos = ficha.parent / 'fotos-tratadas'
            fotos.mkdir(parents=True)
            (fotos / '01-capa.webp').write_bytes(b'capa')
            imovel = dict(self.imoveis[0], slug='santana-flex', _arquivo=ficha)
            documento = b.pagina('Teste', 'Descrição', '', self.corretor, [imovel],
                                 ativo='imoveis.html', imovel=imovel,
                                 no_pagina='imovel/santana-flex.html')
            self.assertIn('rel="preload" as="image"', documento)
            self.assertIn('assets/fonts/manrope-latin.woff2', documento)
            self.assertIn('assets/fonts/archivo-latin.woff2', documento)

    def test_gate_adicional_de_lancamento(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            shutil.copy2(b.ROOT / 'build_site.py', raiz)
            copiar_dados_teste(raiz / 'dados')
            shutil.copytree(b.ASSETS, raiz / 'assets')
            for caminho in (raiz / 'dados' / 'imoveis').glob('*/ficha.md'):
                caminho.write_text(caminho.read_text(encoding='utf-8').replace('demo: true', 'demo: false'), encoding='utf-8')
            corretor = json.loads((raiz / 'dados' / 'corretor.json').read_text(encoding='utf-8'))
            corretor.update(privacidade_revisada=True, email='teste@example.invalid',
                            creci_confirmado_por_igor=False, regime=b.PENDENTE,
                            foto=b.PENDENTE)
            (raiz / 'dados' / 'corretor.json').write_text(json.dumps(corretor), encoding='utf-8')
            resultado = subprocess.run([sys.executable, str(raiz / 'build_site.py'), '--publicar'],
                                       capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(resultado.returncode, 2)
            self.assertIn('preparação do lançamento incompleta', resultado.stderr)
            self.assertIn('CRECI ainda não confirmado', resultado.stderr)
            self.assertIn('regime profissional pendente', resultado.stderr)
            self.assertIn('retrato válido ausente', resultado.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
