"""IndexNow grátis, só URLs públicas alteradas, depois de confirmar o deploy.

Prévia: python notificar_busca.py / /imoveis.html /imovel/<slug>.html
Enviar: acrescente --enviar. --sitemap para o primeiro envio do site inteiro.
Chave em dados/busca.json é pública por definição do protocolo, não é credencial.
"""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
ENDPOINT = 'https://api.indexnow.org/indexnow'


def payload(base, chave, caminhos):
    dominio = urlsplit(base)
    if dominio.scheme != 'https' or dominio.path not in ('', '/') or dominio.query or dominio.fragment or dominio.username:
        raise ValueError('Base precisa ser a raiz HTTPS pública')
    if not re.fullmatch(r'[a-zA-Z0-9-]{8,128}', chave):
        raise ValueError('Chave pública IndexNow inválida')
    urls = []
    for caminho in caminhos:
        url = caminho if caminho.startswith('https://') else base.rstrip('/') + caminho
        partes = urlsplit(url)
        if partes.scheme != 'https' or partes.netloc != dominio.netloc or partes.query or partes.fragment:
            raise ValueError('Somente URLs canônicas do próprio domínio, sem parâmetros')
        if not partes.path.startswith('/') or '..' in partes.path or partes.path.endswith(('/obrigado', '/obrigado.html', '/404.html')):
            raise ValueError('URL interna, de agradecimento ou inválida')
        urls.append(url)
    urls = list(dict.fromkeys(urls))
    if not 1 <= len(urls) <= 10000:
        raise ValueError('Informe entre 1 e 10000 URLs')
    return {'host': dominio.netloc, 'key': chave,
            'keyLocation': base.rstrip('/') + '/' + chave + '.txt', 'urlList': urls}


def enviar(dados):
    # Nunca submeter antes de a prova pública de domínio estar no deploy.
    with urlopen(dados['keyLocation'], timeout=30) as resposta:
        if resposta.read(1024).decode('utf-8').strip() != dados['key']:
            raise ValueError('Chave pública ainda não corresponde ao deploy')
    request = Request(ENDPOINT, data=json.dumps(dados).encode('utf-8'),
                      headers={'Content-Type': 'application/json; charset=utf-8'}, method='POST')
    with urlopen(request, timeout=30) as resposta:
        return resposta.status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('urls', nargs='*')
    parser.add_argument('--sitemap', action='store_true')
    parser.add_argument('--enviar', action='store_true')
    args = parser.parse_args()
    base = json.loads((ROOT / 'dados/corretor.json').read_text(encoding='utf-8'))['site_url']
    chave = json.loads((ROOT / 'dados/busca.json').read_text(encoding='utf-8'))['indexnow']
    urls = args.urls
    if args.sitemap:
        urls += [no.text for no in ElementTree.parse(ROOT / 'publico/sitemap.xml').iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
    dados = payload(base, chave, urls)
    print(f'{len(dados["urlList"])} URLs públicas de {dados["host"]}')
    for url in dados['urlList']:
        print(url)
    if args.enviar:
        print(f'IndexNow HTTP {enviar(dados)} — recebimento não garante indexação ou posição.')
    else:
        print('Prévia; nenhum envio efetuado. Acrescente --enviar após verificar o deploy.')


if __name__ == '__main__':
    main()
