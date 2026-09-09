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
