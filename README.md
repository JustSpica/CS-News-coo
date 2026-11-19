# News Coo

**Português** | [English](README-EN.md)

Um coletor de notícias que busca feeds RSS do Google News, organiza as notícias por tópico e salva cada execução como um resumo em JSON. As fontes e os tópicos são declarados em um único arquivo YAML; o coletor monta uma busca no Google News por tópico combinando todas as fontes, busca todos os tópicos em paralelo e mantém os resultados mais bem ranqueados pelo Google.

## Sumário

- [Funcionalidades](#funcionalidades)
- [Requisitos](#requisitos)
- [Início rápido](#início-rápido)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Configuração](#configuração)
  - [Parâmetros](#parâmetros)
  - [Tópicos e fontes](#tópicos-e-fontes)
- [Uso](#uso)
- [Scripts](#scripts)

## Funcionalidades

- **Configuração declarativa dos feeds.** Os tópicos e as fontes são definidos em `config/feeds.yaml`. Adicionar uma nova fonte é uma entrada de duas linhas no YAML (nome + domínio), sem mudar o código. O coletor monta a URL RSS do Google News automaticamente a partir das palavras-chave do tópico, dos domínios das fontes e do idioma.
- **Coleta em paralelo.** Todos os tópicos são buscados ao mesmo tempo com `asyncio.gather`. Cada tópico gera uma única busca no Google News que combina todas as suas fontes com `(site:a.com OR site:b.com)`, aproveitando o próprio ranking do Google.
- **Ranking do Google.** Cada tópico mantém os primeiros `max_articles_per_topic` resultados da busca combinada, na ordem do Google News.
- **Coleta defensiva.** A configuração dos feeds é validada na inicialização, as URLs do Google News são codificadas a partir de parâmetros estruturados e os downloads de RSS têm tempo limite, novas tentativas em falhas temporárias e limite de tamanho da resposta.
- **Resumo em JSON e no terminal.** Cada execução imprime um resumo por tópico e grava `output/digest-<data e hora UTC>.json` de forma atômica, então uma execução interrompida nunca deixa um arquivo pela metade.

## Requisitos

- Python 3.14+
- Dependências de coleta, testes e lint listadas em `requirements.txt`.

## Início rápido

```bash
git clone git@github.com:JustSpica/CS-News-coo.git
cd CS-News-coo

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py
```

Um resumo por tópico é impresso no terminal e o arquivo JSON é salvo em `output/` (o caminho aparece no log).

## Estrutura do projeto

```text
.
├── _scripts/
│   ├── collect.sh            # Executa uma coleta de notícias (python main.py)
│   ├── test.sh               # Executa o pytest
│   └── lint.sh               # Executa ruff check --fix + ruff format
├── config/
│   ├── settings.py           # Constantes de caminho (config dos feeds, pasta de saída)
│   └── feeds.yaml            # Declaração dos tópicos e das fontes
├── core/
│   ├── models.py             # Dataclasses do domínio (Article, Topic, Source etc.)
│   ├── feed_loader.py        # FeedConfigLoader: leitura e validação do YAML
│   ├── feed_downloader.py    # GoogleNewsFeedDownloader: download HTTP com timeout e retry
│   ├── collector.py          # FeedCollector: busca dos tópicos em paralelo e parsing do RSS
│   └── digest_exporter.py    # Classe base DigestExporter e exportadores JSON e de terminal
├── tests/
│   ├── test_collector.py     # Coleta, parsing, ranking e montagem da URL
│   ├── test_digest_exporter.py  # Classe base, formato do JSON, escrita atômica e resumo no terminal
│   ├── test_feed_downloader.py  # Limite de tamanho e esquema da URL no download
│   ├── test_feed_loader.py   # Leitura do YAML, valores padrão e erros de validação
│   └── test_main.py          # NewsCollectionRunner e códigos de saída do programa
├── main.py                   # Ponto de entrada: main() e NewsCollectionRunner
├── ruff.toml                 # Configuração do linter e do formatador
└── requirements.txt          # Dependências fixadas de coleta, testes e lint
```

`core/` contém os modelos de domínio, a coleta dos feeds e os exportadores. `main.py` é o ponto de entrada: `main()` carrega a configuração, cria o coletor e os exportadores, e o `NewsCollectionRunner` executa uma coleta e entrega o resultado a cada exportador. `config/` centraliza toda a configuração.

## Configuração

### Parâmetros

O `config/feeds.yaml` aceita uma chave `settings` no nível principal com as seguintes opções:

| Chave | Padrão | Descrição |
|---|---|---|
| `max_articles_per_topic` | `15` | Quantidade máxima de artigos mantidos por tópico após a coleta. Deve estar entre `1` e `50`. |

### Tópicos e fontes

Cada tópico tem um `display_name`, uma lista não vazia de `keywords` para a busca, um `language` suportado (`en` quando omitido), que define a região do Google News, e uma lista não vazia de `sources` (nome + domínio). Parâmetros desconhecidos, campos desconhecidos em tópicos ou fontes, idiomas não suportados, palavras-chave vazias, fontes vazias e domínios mal formados interrompem a execução logo no início com um erro de configuração. O coletor combina as entradas válidas em uma única URL RSS por tópico.

```yaml
topics:
  world_economy:
    display_name: "Economia Mundial"
    keywords:
      - "global economy"
      - "world markets"
      - "trade"
    language: en
    sources:
      - name: Reuters
        domain: reuters.com
      - name: Financial Times
        domain: ft.com
```

A URL RSS combinada do Google News segue este formato:

```
https://news.google.com/rss/search?q={keyword1}+OR+{keyword2}+(site:{domain1}+OR+site:{domain2})+when:7d&hl={hl}&gl={gl}&ceid={ceid}
```

Idiomas suportados: `en` (região dos EUA) e `pt` (região do Brasil). O sufixo `when:7d` restringe os resultados aos últimos 7 dias. Os downloads de RSS têm tempo limite de 30 segundos, repetem até duas vezes em erros temporários de rede ou de tempo esgotado e rejeitam respostas maiores que 2 MB.

## Uso

```bash
python main.py            # ou ./_scripts/collect.sh
```

Todos os tópicos configurados são buscados em paralelo e o resultado é entregue a cada exportador em `main.py`. O `main()` cria um `FeedConfigLoader` para ler o YAML e um `FeedCollector` que recebe um `GoogleNewsFeedDownloader` para fazer os downloads. O `ConsoleDigestExporter` imprime um resumo por tópico e o `JsonDigestExporter` grava `output/digest-YYYYMMDDTHHMMSSZ.json` (UTC). Os dois herdam de `DigestExporter`, então um novo destino só precisa de uma nova subclasse. O processo termina com código `0` em caso de sucesso e `1` quando a configuração dos feeds não existe ou é inválida, ou quando o arquivo não pode ser gravado. Um tópico que falha no download não interrompe a execução; todas as fontes dele aparecem em `failed_sources` no JSON e na última linha do resumo. Uma fonte que falha em vários tópicos aparece uma vez para cada tópico. Quando nenhum tópico falha, a linha `Failed sources` não é impressa e `failed_sources` fica vazio, como nos exemplos abaixo.

Resumo no terminal:

```text
Collected 105 articles across 7 topics:
  - Economia Mundial: 15 articles
  - Economia Brasileira: 15 articles
  ...
```

Arquivo JSON:

```json
{
  "collected_at": "2026-11-05T21:05:58+00:00",
  "total_articles": 105,
  "failed_sources": [],
  "topics": [
    {
      "key": "world_economy",
      "display_name": "Economia Mundial",
      "article_count": 15,
      "failed_sources": [],
      "articles": [
        {
          "title": "Global markets were already fragile... - Reuters",
          "url": "https://news.google.com/rss/articles/...",
          "source_name": "Reuters",
          "published_at": "2026-11-03T05:14:39+00:00"
        }
      ]
    }
  ]
}
```

`published_at` é `null` quando a notícia no feed não tem uma data válida.

## Scripts

Todos os scripts ficam em `_scripts/` e ativam o ambiente virtual automaticamente.

| Script | Uso | Descrição |
|---|---|---|
| `collect.sh` | `./_scripts/collect.sh` | Executa uma coleta, imprime o resumo e salva o arquivo JSON. |
| `test.sh` | `./_scripts/test.sh [-v]` | Executa os testes. Aceita qualquer argumento do pytest. |
| `lint.sh` | `./_scripts/lint.sh [--check]` | Executa `ruff check --fix` e `ruff format`. Use `--check` para apenas verificar, sem alterar arquivos. |
