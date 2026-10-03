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


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Os testes não devem depender dos dados pessoais atuais do perfil local.
        cls.corretor = dict(b.ler_corretor(), foto=b.PENDENTE,
                            creci_confirmado_por_igor=False, regime=b.PENDENTE)
        cls.imoveis = b.ler_imoveis()

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

    def test_rascunhos_fora_do_build_e_listados_no_check(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            shutil.copytree(b.DADOS, raiz / 'dados')
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
        documentos = [b.pagina_home(self.corretor, self.imoveis)] + [b.pagina_segmento(self.corretor, self.imoveis, segmento) for segmento in ('comercial', 'residencial')]
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

    def test_builds_isolados_gates_seo_e_sitemap(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            shutil.copy2(b.ROOT / 'build_site.py', raiz)
            shutil.copytree(b.DADOS, raiz / 'dados')
            shutil.copytree(b.ASSETS, raiz / 'assets')

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
            self.assertIn('data-netlify="true"', (saida / 'index.html').read_text(encoding='utf-8'))
            robots = (saida / 'robots.txt').read_text()
            for agente in ('*', 'GPTBot', 'OAI-SearchBot', 'ClaudeBot', 'PerplexityBot', 'Google-Extended'):
                self.assertIn(f'User-agent: {agente}\nAllow: /', robots)
            sitemap = ElementTree.parse(saida / 'sitemap.xml')
            ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            base = corretor['site_url'].rstrip('/') + '/'
            urls = {n.text.removeprefix(base) for n in sitemap.findall('.//s:loc', ns)}
            paginas = {p.relative_to(saida).as_posix() for p in saida.rglob('*.html') if p.name not in {'404.html', 'obrigado.html'}}
            self.assertEqual(urls, paginas)
            self.assertEqual(len(sitemap.findall('.//s:lastmod', ns)), len(paginas))

    def test_gate_adicional_de_lancamento(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            shutil.copy2(b.ROOT / 'build_site.py', raiz)
            shutil.copytree(b.DADOS, raiz / 'dados')
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
