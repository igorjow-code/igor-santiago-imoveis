# Igor Santiago Imóveis

Site do corretor Igor Santiago (CRECI-BA 28.140), Feira de Santana, BA.
Gerador estático em Python (stdlib), sem framework, sem dependência.

**Painel de negócio, decisões e roadmap:** vivem no repositório privado `igris-os`,
em `clientes/is-imoveis/`. Este repositório é só o código do site — link único de
verdade para as decisões é o BOARD.md de lá, não aqui.

## Estrutura

```
build_site.py     gerador (lê dados/, escreve publico/)
dados/
  corretor.json   dados do corretor (CRECI, WhatsApp, Instagram, bio)
  imoveis/        uma pasta por imóvel, ficha.md com front-matter + descrição
assets/           CSS, JS, favicon
publico/          saída gerada (não versionada — Netlify gera a cada deploy)
```

Fotos reais: use `importar_fotos.py` para converter um ZIP ou pasta exportados do Google
Fotos. O script reduz as imagens, remove metadados e grava em
`dados/imoveis/<slug>/fotos-tratadas/`, em ordem pelo nome original. Para uma pasta/ZIP:
`python importar_fotos.py caminho/para/album.zip --imovel <slug>`; para processar tudo em
`entrada-fotos/`, use `python importar_fotos.py --entrada`. Originais em
`entrada-fotos/` são ignorados pelo Git. O build mantém o contrato de leitura existente e
copia as fotos para `publico/assets/imoveis/<slug>/`. Sem arquivos, não há bloco de foto
nem carrossel. Sem `ficha.md`, o importador cria uma ficha rascunho a partir de
`dados/_modelo/ficha.md`.
Os testes do importador com ZIP e GPS real de fixture rodam junto da suíte:
`python -m unittest -v test_site.py test_visual.py test_importar.py`.
O retrato usa o caminho local em `corretor.json` → `foto`, dentro de `assets/`.
Não inserir imagens de demonstração para preencher espaços vazios.

Verificação local: `python -m unittest -v test_site.py test_visual.py`.

## Rodar local

```
python build_site.py            # build normal
python build_site.py --check    # lista o que falta preencher
python build_site.py --publicar # build de publicação — recusa se houver imóvel demo
python -m http.server 8000 --directory publico
```

## Deploy

Netlify, ligado a este repositório GitHub. Toda vez que a branch principal
recebe um push, o Netlify roda `python3 build_site.py` e publica `publico/`.
Configuração em `netlify.toml`.

**Enquanto o catálogo tiver imóvel com `demo: true`**, toda página carrega uma barra
vermelha de aviso e leva `noindex`. Isso é intencional — nenhum destes imóveis existe.
