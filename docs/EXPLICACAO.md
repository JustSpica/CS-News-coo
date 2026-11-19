# Como o News Coo funciona, passo a passo

Este documento explica o projeto inteiro na ordem em que o código roda: do comando `python main.py` até o programa terminar. Cada classe, atributo e método aparece no momento em que entra em ação, com o que recebe, o que devolve e o que acontece quando algo dá errado.

## Sumário

1. [O que o programa faz](#1-o-que-o-programa-faz)
2. [Mapa dos arquivos](#2-mapa-dos-arquivos)
3. [As peças de dados (`core/models.py`)](#3-as-peças-de-dados-coremodelspy)
4. [Passo 1: o comando `python main.py`](#4-passo-1-o-comando-python-mainpy)
5. [Passo 2: `main()` liga o log](#5-passo-2-main-liga-o-log)
6. [Passo 3: leitura e validação do YAML (`FeedConfigLoader`)](#6-passo-3-leitura-e-validação-do-yaml-feedconfigloader)
7. [Passo 4: montagem dos objetos](#7-passo-4-montagem-dos-objetos)
8. [Passo 5: o runner começa a rodar (`NewsCollectionRunner.run`)](#8-passo-5-o-runner-começa-a-rodar-newscollectionrunnerrun)
9. [Passo 6: a coleta (`FeedCollector`)](#9-passo-6-a-coleta-feedcollector)
10. [Passo 7: o download (`GoogleNewsFeedDownloader`)](#10-passo-7-o-download-googlenewsfeeddownloader)
11. [Passo 8: a exportação (`DigestExporter` e filhas)](#11-passo-8-a-exportação-digestexporter-e-filhas)
12. [Passo 9: o código de saída](#12-passo-9-o-código-de-saída)
13. [Exemplo completo de uma execução](#13-exemplo-completo-de-uma-execução)
14. [Conceitos de POO e onde estão](#14-conceitos-de-poo-e-onde-estão)
15. [Testes](#15-testes)
16. [Scripts e ferramentas](#16-scripts-e-ferramentas)
17. [Glossário](#17-glossário)

---

## 1. O que o programa faz

O News Coo é um coletor de notícias. Ele lê uma lista de **tópicos** (por exemplo, "Economia Mundial") e de **fontes** de cada tópico (por exemplo, Reuters e Financial Times) num arquivo YAML. Para cada tópico, faz uma busca no **Google News** que devolve um feed RSS, transforma cada item do feed num artigo e, no fim, entrega o resultado a dois exportadores:

- um que **imprime um resumo no terminal**;
- outro que **grava um arquivo JSON** em `output/`.

O fluxo inteiro, em uma linha por passo:

1. `python main.py` chama a função `main()`.
2. `main()` configura o log.
3. `FeedConfigLoader` lê `config/feeds.yaml`, valida tudo e devolve as configurações e a lista de tópicos.
4. `main()` cria o downloader, o coletor, os dois exportadores e o runner.
5. O runner pede ao coletor que colete.
6. O coletor busca todos os tópicos **ao mesmo tempo**. Para cada um, monta a URL do Google News, usa o downloader para baixar o RSS e transforma o RSS em artigos.
7. O runner entrega o resultado a cada exportador: primeiro o do terminal, depois o do JSON.
8. `main()` devolve `0` (sucesso) ou `1` (erro), e esse é o código de saída do processo.

---

## 2. Mapa dos arquivos

| Arquivo | O que tem |
|---|---|
| `main.py` | A função `main()` (ponto de entrada) e a classe `NewsCollectionRunner` |
| `config/settings.py` | Os caminhos do arquivo de feeds e da pasta de saída |
| `config/feeds.yaml` | A declaração dos tópicos e das fontes |
| `core/models.py` | As classes de dados: `FeedSettings`, `Source`, `Topic`, `Article`, `TopicResult`, `CollectionResult` |
| `core/feed_loader.py` | `FeedConfigError` e `FeedConfigLoader` (lê e valida o YAML) |
| `core/collector.py` | `FeedCollector` (monta as buscas, coleta em paralelo e interpreta o RSS) |
| `core/feed_downloader.py` | `GoogleNewsFeedDownloader` (download HTTP) |
| `core/digest_exporter.py` | `DigestExporter`, `JsonDigestExporter`, `ConsoleDigestExporter` |
| `tests/` | Os testes automatizados (pytest) |
| `_scripts/` | Atalhos para coletar, testar e rodar o lint |
| `ruff.toml` | Configuração do linter e formatador |
| `requirements.txt` | Bibliotecas usadas, com versões fixas |

Os arquivos `__init__.py` (vazios) em `config/`, `core/` e `tests/` só existem para o Python tratar essas pastas como pacotes e permitir imports como `from core.models import Topic`.

Quase todo arquivo começa com `from __future__ import annotations`. Essa linha faz o Python guardar as anotações de tipo (`-> list[Article]`, por exemplo) como texto em vez de avaliá-las na hora. Na prática, permite citar uma classe num tipo antes de ela ser definida e não muda nada no comportamento do programa.

### `config/settings.py`

```python
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
FEEDS_PATH: Path = PROJECT_ROOT / "config" / "feeds.yaml"
DIGEST_OUTPUT_DIR: Path = PROJECT_ROOT / "output"
```

- `Path(__file__)` é o caminho do próprio `settings.py`. `.resolve()` transforma em caminho absoluto, e `.parent.parent` sobe duas pastas (`config/` e depois a raiz do projeto).
- `FEEDS_PATH` aponta para `config/feeds.yaml`, e `DIGEST_OUTPUT_DIR` para a pasta `output/`.
- Como os caminhos partem da localização do arquivo, o programa funciona de qualquer pasta em que for executado.

### `config/feeds.yaml`

Tem duas chaves no nível principal:

```yaml
settings:
  max_articles_per_topic: 15

topics:
  world_economy:              # chave do tópico (identificador interno)
    display_name: "Economia Mundial"
    keywords:
      - "global economy"
      - "world markets"
    language: en
    sources:
      - name: Reuters
        domain: reuters.com
```

Hoje há 7 tópicos: `world_economy`, `brazilian_economy`, `brazilian_economy_international`, `world_politics`, `brazilian_politics`, `technology` e `artificial_intelligence`.

---

## 3. As peças de dados (`core/models.py`)

Antes do fluxo, vale conhecer as classes que carregam os dados de um lado para outro. Todas são **dataclasses**: o decorador `@dataclass` gera automaticamente o construtor (`__init__`), a comparação (`__eq__`) e a representação em texto (`__repr__`) a partir dos atributos declarados. Elas não têm regra de negócio, só guardam dados.

Algumas usam `@dataclass(frozen=True)`, que torna o objeto **imutável**: depois de criado, tentar mudar um atributo gera erro. Isso vale para dados que não devem mudar depois de lidos (configuração, tópicos, fontes, artigos).

### `SUPPORTED_TOPIC_LANGUAGES`

```python
SUPPORTED_TOPIC_LANGUAGES = frozenset({"en", "pt"})
```

Constante com os idiomas aceitos. É um `frozenset` (conjunto imutável). O `FeedConfigLoader` usa essa constante para rejeitar idiomas desconhecidos.

### `FeedSettings` (imutável)

| Atributo | Tipo | Padrão | Significado |
|---|---|---|---|
| `max_articles_per_topic` | `int` | `15` | Quantos artigos guardar por tópico |

### `Source` (imutável)

Uma fonte de notícias.

| Atributo | Tipo | Significado |
|---|---|---|
| `name` | `str` | Nome exibido, por exemplo `"Reuters"` |
| `domain` | `str` | Domínio do site, por exemplo `"reuters.com"` |

### `Topic` (imutável)

Um tópico de busca.

| Atributo | Tipo | Significado |
|---|---|---|
| `key` | `str` | Identificador interno, a chave no YAML (`"world_economy"`) |
| `display_name` | `str` | Nome exibido (`"Economia Mundial"`) |
| `keywords` | `list[str]` | Palavras-chave da busca |
| `language` | `str` | `"en"` ou `"pt"`; define a região do Google News |
| `sources` | `list[Source]` | As fontes do tópico (associação `Topic → Source`) |

### `Article` (imutável)

Uma notícia encontrada.

| Atributo | Tipo | Significado |
|---|---|---|
| `url` | `str` | Link da notícia (é um link do Google News que redireciona para o site) |
| `title` | `str` | Título |
| `source_name` | `str` | Nome da fonte (`"Reuters"`) ou `"Unknown"` se não foi identificada |
| `published_at` | `datetime \| None` | Data de publicação em UTC, ou `None` se o feed não trouxe uma data válida |

### `TopicResult` (mutável)

O resultado da coleta de um tópico. É mutável porque o coletor cria o objeto vazio e depois preenche `articles` ou `failed_sources`.

| Atributo | Tipo | Padrão | Significado |
|---|---|---|---|
| `topic_key` | `str` | | Chave do tópico |
| `topic_display_name` | `str` | | Nome exibido do tópico |
| `articles` | `list[Article]` | lista vazia | Artigos coletados |
| `failed_sources` | `list[str]` | lista vazia | Nomes das fontes que falharam |

O padrão das listas usa `field(default_factory=list)`. Isso garante que cada objeto ganhe **a sua própria** lista vazia. Escrever `articles: list = []` faria todos os objetos compartilharem a mesma lista, um erro clássico em Python.

### `CollectionResult` (mutável)

O resultado da coleta inteira.

| Membro | Tipo | Significado |
|---|---|---|
| `topic_results` | `list[TopicResult]` | Um resultado por tópico, na ordem do YAML |
| `total_articles` | `int` (propriedade) | Soma dos artigos de todos os tópicos |
| `all_failed_sources` | `list[str]` (propriedade) | Todas as fontes com falha, de todos os tópicos, juntas numa lista |

`total_articles` e `all_failed_sources` são **propriedades** (`@property`): parecem atributos (`result.total_articles`, sem parênteses), mas são métodos calculados a cada acesso, a partir de `topic_results`. Não guardam valor próprio, então nunca ficam desatualizados.

- `total_articles` faz `sum(len(topic_result.articles) for topic_result in self.topic_results)`.
- `all_failed_sources` percorre cada `TopicResult` e cada nome em `failed_sources`, juntando tudo. Se a mesma fonte falhar em dois tópicos, aparece duas vezes.

---

## 4. Passo 1: o comando `python main.py`

No fim de `main.py`:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- `__name__` vale `"__main__"` só quando o arquivo é executado diretamente. Quando os testes fazem `import main`, esse bloco **não** roda, e é por isso que os testes conseguem importar o módulo sem disparar uma coleta.
- `main()` devolve um inteiro (`0` ou `1`). `raise SystemExit(código)` encerra o processo com esse código de saída, que o terminal e outros programas podem ler (`echo $?` no Linux).

---

## 5. Passo 2: `main()` liga o log

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
```

- Configura o sistema de log do Python para mostrar mensagens de nível `INFO` para cima (`INFO`, `WARNING`, `ERROR`). Mensagens `DEBUG` ficam ocultas.
- Cada linha mostra data e hora, o nível com 8 caracteres de largura, o nome do logger e a mensagem. Exemplo: `2026-11-19 16:04:53,921 INFO     core.collector: Topic 'Tecnologia': 15 articles`.
- Cada módulo cria o próprio logger com `logging.getLogger(__name__)` (o nome vira `core.collector`, `core.digest_exporter` etc.). O `main.py` usa o nome fixo `"news-coo"`.

O log vai para a saída de erro (stderr), e o resumo do `ConsoleDigestExporter` vai para a saída padrão (stdout). Por isso dá para separar os dois no terminal, por exemplo com `python main.py 2>/dev/null` para ver só o resumo.

---

## 6. Passo 3: leitura e validação do YAML (`FeedConfigLoader`)

Em `main()`:

```python
config_loader = FeedConfigLoader(FEEDS_PATH)
try:
    settings, topics = config_loader.load()
except (FeedConfigError, OSError) as exc:
    log.error("Could not load feeds config %s: %s", FEEDS_PATH, exc)
    return 1
```

- Cria o carregador apontando para `config/feeds.yaml` e chama `load()`.
- Se o arquivo não existir ou não puder ser lido, o Python lança `OSError` (`FileNotFoundError` é filha de `OSError`). Se o conteúdo for inválido, o carregador lança `FeedConfigError`. Nos dois casos, `main()` registra o erro e devolve `1` sem coletar nada.
- Em caso de sucesso, `load()` devolve uma tupla de dois itens, que é desempacotada em `settings` (um `FeedSettings`) e `topics` (uma `list[Topic]`).

### Constantes do módulo `core/feed_loader.py`

| Constante | Valor | Para que serve |
|---|---|---|
| `_FEED_SETTINGS_FIELDS` | `{"max_articles_per_topic"}` | Chaves aceitas em `settings`. É calculada a partir dos campos de `FeedSettings` com `dataclasses.fields`, então um campo novo em `FeedSettings` passa a ser aceito automaticamente |
| `_DEFAULT_FEED_SETTINGS` | `FeedSettings()` | Instância com os valores padrão, de onde sai o `15` |
| `_MAX_ARTICLES_PER_TOPIC_LIMIT` | `50` | Valor máximo aceito em `max_articles_per_topic` |
| `_TOPIC_FIELDS` | `{"display_name", "keywords", "language", "sources"}` | Campos aceitos num tópico |
| `_SOURCE_FIELDS` | `{"name", "domain"}` | Campos aceitos numa fonte |
| `_DOMAIN_PATTERN` | `^[A-Za-z0-9.-]+$` | Expressão regular de um domínio válido: só letras, números, ponto e hífen |

O `_` no início do nome indica que são de uso interno do módulo.

### `FeedConfigError`

```python
class FeedConfigError(ValueError):
    pass
```

Exceção própria do projeto para erros de configuração. Herda de `ValueError` (classe do Python), então qualquer código que trate `ValueError` também a captura. O corpo é só `pass` porque ela não precisa de nada além do que herda. Ter um tipo próprio permite que `main()` capture **apenas** erros de configuração, sem esconder outros problemas.

### `FeedConfigLoader.__init__(path)`

Guarda o caminho do arquivo no atributo privado `self.__path`.

### `FeedConfigLoader.load()` → `tuple[FeedSettings, list[Topic]]`

O único método público. Passo a passo:

1. Abre o arquivo com `encoding="utf-8"`, para que acentos como em "Inteligência" sejam lidos corretamente.
2. `yaml.safe_load` transforma o texto YAML em estruturas Python (dicionários, listas, strings, números). A versão *safe* não cria objetos Python arbitrários a partir do arquivo, o que evita execução de código malicioso escondido num YAML.
3. `__require_mapping` confere que o resultado é um dicionário (um arquivo vazio vira `None` e é rejeitado com `"feeds config must be a mapping"`).
4. `__load_settings` processa a chave `settings` (ou `{}` se ela não existir).
5. `__load_topics` processa a chave `topics` (ou `{}` se ela não existir).
6. Devolve `(settings, topics)`.

### `__load_settings(raw_settings)` → `FeedSettings`

1. Se `settings:` existir no YAML mas estiver vazio, o valor chega como `None` e é trocado por `{}`.
2. `__require_mapping` confere que é um dicionário.
3. `__reject_unknown_fields` rejeita chaves que não sejam de `FeedSettings`, como `unknown_setting: true`. Isso pega erros de digitação, como `max_article_per_topic`, que de outro modo seriam ignorados em silêncio.
4. Pega `max_articles_per_topic` (ou o padrão `15`) e valida com `__validate_max_articles_per_topic`.
5. Cria e devolve `FeedSettings(max_articles_per_topic=...)`.

### `__load_topics(raw_topics)` → `list[Topic]`

1. Troca `None` por `{}`, como acima, e confere que é um dicionário.
2. Para cada par `(chave, conteúdo)` do dicionário, chama `__load_topic` e monta a lista. A ordem dos tópicos é a ordem do YAML.

### `__load_topic(topic_key, raw_topic_entry)` → `Topic`

1. Rejeita chave de tópico vazia (`"Topic keys must be non-empty strings"`).
2. Monta um rótulo `"topic 'world_economy'"`, usado em todas as mensagens de erro para dizer **onde** está o problema.
3. Confere que o conteúdo é um dicionário e rejeita campos desconhecidos.
4. Cria o `Topic` validando cada campo:
   - `display_name` com `__require_non_empty_string`;
   - `keywords` com `__require_string_list`;
   - `language` com `__validate_language` (usa `"en"` se o campo não existir);
   - `sources` com `__load_sources`.

Os argumentos são avaliados nessa ordem, então se dois campos estiverem errados, o erro que aparece é o do primeiro.

### `__load_sources(topic_key, raw_sources)` → `list[Source]`

1. Exige uma lista não vazia (`"topic 'x' sources must be a non-empty list"`).
2. Para cada item, chama `__load_source` com um rótulo numerado a partir de 1: `"topic 'x' source #2"`.

### `__load_source(raw_source, label)` → `Source`

1. Confere que o item é um dicionário e rejeita campos desconhecidos.
2. Cria `Source` com `name` validado por `__require_non_empty_string` e `domain` validado por `__validate_domain`.

### `__validate_language(value, topic_key)` → `str`

Exige texto não vazio e que esteja em `SUPPORTED_TOPIC_LANGUAGES`. Se não estiver, a mensagem lista os idiomas aceitos: `"Unsupported language for topic 'x': fr. Supported: en, pt"`.

### `__validate_domain(value, label)` → `str`

Exige texto não vazio e então rejeita o domínio se qualquer uma destas condições for verdadeira:

- tem caractere fora de letras, números, ponto e hífen (por exemplo `example.com&bad=true`, `https://x.com` ou `x.com/path`);
- começa com ponto;
- termina com ponto;
- tem dois pontos seguidos (`..`).

Isso importa porque o domínio entra na URL de busca. Um domínio com `&` ou `=` poderia injetar parâmetros extras na URL do Google News.

### `__validate_max_articles_per_topic(value)` → `int`

1. Exige um inteiro. Há um detalhe: em Python, `bool` é filho de `int` (`True == 1`), então `isinstance(True, int)` é verdadeiro. Por isso o código rejeita `bool` explicitamente; sem isso, `max_articles_per_topic: true` seria aceito como `1`.
2. Exige um valor entre `1` e `50`.

### `__reject_unknown_fields(entry, allowed_fields, message_prefix)`

Calcula `set(entry) - allowed_fields` (as chaves que sobram depois de tirar as permitidas). Se sobrar alguma, lança `FeedConfigError` com elas em ordem alfabética: `"Unknown field(s) in topic 'x': color, size"`. É usado em `settings`, nos tópicos e nas fontes.

### `__require_mapping(value, label)` → `Mapping`

Confere que o valor é um dicionário (`Mapping`) e que todas as chaves são strings. No YAML, `123: algo` gera uma chave numérica, e isso é rejeitado aqui.

### `__require_non_empty_string(value, label)` → `str`

Confere que o valor é uma string com algo além de espaços e devolve o texto **sem espaços nas pontas** (`.strip()`). Então `" Reuters "` vira `"Reuters"`.

### `__require_string_list(value, label)` → `list[str]`

Exige uma lista não vazia e aplica `__require_non_empty_string` a cada item.

---

## 7. Passo 4: montagem dos objetos

```python
runner = NewsCollectionRunner(
    collector=FeedCollector(settings, topics, GoogleNewsFeedDownloader()),
    exporters=[ConsoleDigestExporter(), JsonDigestExporter(DIGEST_OUTPUT_DIR)],
)
```

São criados, de dentro para fora:

1. `GoogleNewsFeedDownloader()`: o objeto que faz os downloads HTTP. Não tem atributos.
2. `FeedCollector(settings, topics, downloader)`: guarda os três em atributos privados (`__settings`, `__topics`, `__feed_downloader`).
3. `ConsoleDigestExporter()`: guarda em `__output_stream` onde vai escrever (por padrão, `sys.stdout`, o terminal).
4. `JsonDigestExporter(DIGEST_OUTPUT_DIR)`: guarda a pasta de saída em `__output_dir` e o relógio em `__clock` (por padrão, a função `_utc_now`).
5. `NewsCollectionRunner(collector, exporters)`: guarda o coletor e a lista de exportadores.

Essa forma de montar se chama **injeção de dependência**: cada objeto recebe pronto aquilo de que depende, em vez de criar sozinho. O coletor não sabe *como* o download é feito, só que recebeu algo com o método `download(url)`. Isso é o que permite aos testes trocar o downloader real por um falso, que devolve RSS fixo sem acessar a internet.

### `NewsCollectionRunner.__init__(collector, exporters)`

```python
if not exporters:
    raise ValueError("NewsCollectionRunner requires at least one exporter")
self.__collector = collector
self.__exporters = exporters
```

Rejeita uma lista vazia de exportadores, porque coletar sem ter para onde enviar o resultado não faz sentido. Depois guarda os dois em atributos privados.

---

## 8. Passo 5: o runner começa a rodar (`NewsCollectionRunner.run`)

Em `main()`:

```python
try:
    asyncio.run(runner.run())
except OSError as exc:
    log.error("Could not write digest to %s: %s", DIGEST_OUTPUT_DIR, exc)
    return 1
```

`run()` é uma função **assíncrona** (`async def`). Chamar `runner.run()` não executa nada sozinho: cria uma *corrotina*, uma tarefa pronta para rodar. `asyncio.run(...)` cria o *event loop* (o laço que coordena as tarefas assíncronas), executa a corrotina até o fim e fecha o laço.

Se algum exportador falhar ao gravar (disco cheio, sem permissão na pasta), o `OSError` sobe até aqui, é registrado no log e `main()` devolve `1`.

### `NewsCollectionRunner.run()`

```python
result = await self.__collector.collect()
if result.total_articles == 0:
    log.warning("Collection returned no articles; exporting an empty digest")

for exporter in self.__exporters:
    exporter.export(result)
```

1. `await` espera a coleta terminar e recebe um `CollectionResult`.
2. Se nenhum artigo veio (sem internet, por exemplo), registra um aviso, mas **continua**: exporta mesmo assim, para que fique o registro de que a execução aconteceu e de quais fontes falharam.
3. Chama `export(result)` em cada exportador, na ordem da lista: primeiro o do terminal, depois o do JSON. Esse laço é o **polimorfismo** do projeto: o runner chama o mesmo método `export` sem saber qual classe concreta está do outro lado, e cada uma faz uma coisa diferente.

---

## 9. Passo 6: a coleta (`FeedCollector`)

### Constantes de `core/collector.py`

| Constante | Valor | Para que serve |
|---|---|---|
| `GOOGLE_NEWS_RSS_BASE` | `https://news.google.com/rss/search` | Endereço base da busca RSS do Google News |
| `LANGUAGE_PARAMS` | ver abaixo | Parâmetros de região de cada idioma |

```python
LANGUAGE_PARAMS = {
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "pt": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
}
```

- `hl`: idioma da interface;
- `gl`: país;
- `ceid`: a "edição" do Google News, que combina país e idioma.

### `FeedCollector.__init__(settings, topics, feed_downloader)`

Guarda os três argumentos em `__settings`, `__topics` e `__feed_downloader`.

### `FeedCollector.collect()` → `CollectionResult` (assíncrono, público)

```python
topic_results = await asyncio.gather(
    *(self.__collect_topic(topic) for topic in self.__topics)
)
result = CollectionResult(topic_results=list(topic_results))
```

1. Cria uma corrotina `__collect_topic(topic)` para cada tópico.
2. `asyncio.gather(...)` roda todas **ao mesmo tempo** e espera todas terminarem. O `*` "espalha" as corrotinas como argumentos separados. Os resultados voltam **na mesma ordem dos tópicos**, mesmo que um tópico termine antes de outro.
3. Embrulha a lista num `CollectionResult`.
4. Registra no log o total de artigos, de tópicos e de fontes com falha, e devolve o resultado.

Com 7 tópicos, a coleta leva mais ou menos o tempo do tópico mais lento, em vez da soma dos 7.

### `__collect_topic(topic)` → `TopicResult` (assíncrono, privado)

```python
topic_result = TopicResult(topic_key=topic.key, topic_display_name=topic.display_name)

try:
    articles = await asyncio.to_thread(self.__fetch_topic_articles, topic)
except Exception as exc:
    log.error("Failed to fetch topic %s: %s", topic.key, exc)
    topic_result.failed_sources = [source.name for source in topic.sources]
    return topic_result

topic_result.articles = articles[: self.__settings.max_articles_per_topic]
log.info("Topic '%s': %d articles", topic.display_name, len(topic_result.articles))
return topic_result
```

1. Cria um `TopicResult` vazio para o tópico.
2. `asyncio.to_thread` executa `__fetch_topic_articles(topic)` numa **thread** separada. Isso é necessário porque o download usa `urllib`, que é *bloqueante*: enquanto espera a rede, trava quem o chamou. Rodando em threads, os 7 downloads esperam a rede em paralelo e o *event loop* fica livre.
3. **Se qualquer erro acontecer** (rede fora, timeout, HTTP 503, RSS inválido, idioma sem parâmetros), o erro é registrado e **todas** as fontes do tópico entram em `failed_sources`. O tópico volta sem artigos, mas a coleta dos outros tópicos continua normalmente. O `except Exception` amplo é proposital: a falha de um tópico não deve derrubar a execução inteira.
4. Se deu certo, guarda só os primeiros `max_articles_per_topic` artigos. `articles[:15]` corta a lista nos 15 primeiros, que são os mais bem ranqueados pelo Google, porque o feed já vem ordenado por relevância.

### `__fetch_topic_articles(topic)` → `list[Article]` (privado, roda na thread)

```python
url = self.__build_google_news_url(topic)
log.info("Fetching topic '%s': %s", topic.display_name, url)
raw_content = self.__feed_downloader.download(url)
return self.__parse_feed_entries(raw_content, topic)
```

As três etapas de um tópico: monta a URL, baixa o RSS pelo downloader recebido no construtor e transforma o RSS em artigos.

### `__build_google_news_url(topic)` → `str`

1. Junta as palavras-chave com `" OR "`: `global economy OR world markets OR trade`.
2. Junta os domínios como `site:` com `" OR "`: `site:reuters.com OR site:ft.com`.
3. Monta a consulta: `global economy OR world markets OR trade (site:reuters.com OR site:ft.com) when:7d`.
   - `site:dominio` restringe os resultados àquele site, e os parênteses agrupam os sites;
   - `when:7d` restringe aos últimos 7 dias.
4. Junta a consulta (`q`) com os parâmetros de região de `__language_params`.
5. `urllib.parse.urlencode(params, safe="():")` transforma tudo em texto de URL: espaço vira `+` e caracteres especiais viram códigos `%XX` (por exemplo, `&` vira `%26`). O `safe="():"` mantém parênteses e dois-pontos legíveis, porque o Google os entende diretamente.

Resultado:

```text
https://news.google.com/rss/search?q=global+economy+OR+world+markets+OR+trade+(site:reuters.com+OR+site:ft.com)+when:7d&hl=en-US&gl=US&ceid=US:en
```

Codificar a partir de parâmetros (em vez de colar textos) garante que uma palavra-chave como `market & trade` não quebre a URL: o `&` vira `%26` e não é confundido com um separador de parâmetros.

### `__language_params(language)` → `dict[str, str]`

Busca o idioma em `LANGUAGE_PARAMS`. Se não existir, lança `ValueError` com os idiomas suportados. O `FeedConfigLoader` já barra idiomas inválidos, então essa verificação é uma segunda proteção para quem criar um `Topic` direto no código, como os testes fazem. O `from None` no `raise` esconde o `KeyError` original da mensagem de erro, que só confundiria.

### `__parse_feed_entries(raw, topic)` → `list[Article]`

1. `feedparser.parse(raw)` interpreta o RSS (XML) e devolve um objeto com `entries`, um item por notícia.
2. O feedparser marca `bozo = True` quando o XML tem problemas. O código só desiste (relança o erro guardado em `bozo_exception`) se o feed tiver problemas **e** nenhuma notícia aproveitável. Um feed com um defeito pequeno mas com notícias é aceito.
3. Para cada item:
   - pega `link` e `title`, sem espaços nas pontas;
   - **pula** o item se faltar link ou título;
   - pega o endereço da fonte em `entry.source.href`. No RSS do Google News, cada item tem uma tag `<source url="https://www.reuters.com">Reuters</source>`. O `getattr(..., "href", "")` devolve `""` se não houver;
   - cria o `Article` com o nome da fonte (`__identify_source_name`) e a data (`__parse_date`).
4. Registra quantos itens foram lidos (nível `DEBUG`, oculto por padrão) e devolve a lista.

### `__identify_source_name(source_url, sources)` → `str`

1. `urllib.parse.urlparse(source_url).hostname` extrai só o host: de `https://www.reuters.com/x` sai `www.reuters.com`.
2. Procura uma fonte do tópico cujo domínio seja **igual** ao host ou de que o host seja um **subdomínio** (termina com `.` + domínio):
   - `reuters.com` casa com `reuters.com` e com `www.reuters.com`;
   - `asia.nikkei.com` casa com `asia.nikkei.com`.
3. Se encontrar, devolve o nome da fonte; se não, devolve `"Unknown"`.

O teste com `"." + domínio` evita um falso positivo: `notreuters.com` termina com `reuters.com`, mas não com `.reuters.com`, então não é confundido com a Reuters.

### `__parse_date(entry)` → `datetime | None`

1. Tenta o campo `published` e depois `updated` do item.
2. `parsedate_to_datetime` interpreta datas no formato dos e-mails e do RSS (RFC 2822), como `Wed, 14 May 2026 10:00:00 GMT`.
3. `.astimezone(UTC)` converte para o fuso UTC, para que todas as datas fiquem comparáveis.
4. Se a data for inválida, ignora e tenta o próximo campo. Se nenhum servir, devolve `None`.

A linha `except ValueError, TypeError:` (sem parênteses) é uma sintaxe nova do **Python 3.14** e equivale a `except (ValueError, TypeError):`. Em versões anteriores do Python, essa linha é erro de sintaxe, e é por isso que o projeto exige Python 3.14+.

---

## 10. Passo 7: o download (`GoogleNewsFeedDownloader`)

Este passo acontece dentro de `__fetch_topic_articles`, na chamada `self.__feed_downloader.download(url)`.

### Constantes de `core/feed_downloader.py`

| Constante | Valor | Para que serve |
|---|---|---|
| `FETCH_TIMEOUT_SECONDS` | `30` | Tempo máximo de espera de cada tentativa |
| `FETCH_RETRY_ATTEMPTS` | `2` | Quantas **novas** tentativas depois da primeira (3 no total) |
| `FETCH_RETRY_BACKOFF_SECONDS` | `0.5` | Base da pausa entre tentativas |
| `MAX_FEED_BYTES` | `2_000_000` | Tamanho máximo aceito para a resposta (2 MB). O `_` é só separador visual de milhar |
| `USER_AGENT` | `"news-coo/1.0"` | Como o programa se identifica para o servidor |

### `download(url)` → `bytes` (público)

```python
if not url.startswith(("https://", "http://")):
    raise ValueError(f"Unsupported URL scheme: {url}")

for attempt in range(FETCH_RETRY_ATTEMPTS + 1):      # 0, 1, 2
    try:
        return self.__download_once(url)
    except urllib.error.HTTPError:
        raise
    except (TimeoutError, urllib.error.URLError) as exc:
        if attempt == FETCH_RETRY_ATTEMPTS:
            raise
        log.warning("Feed download failed, retrying: %s", exc)
        time.sleep(FETCH_RETRY_BACKOFF_SECONDS * (attempt + 1))
```

1. **Recusa esquemas que não sejam HTTP(S).** O `urllib` também abre `file://`, que leria arquivos do computador. A verificação impede isso.
2. Faz até 3 tentativas (`attempt` = 0, 1, 2):
   - se der certo, devolve o conteúdo na hora;
   - **erro HTTP** (`HTTPError`, por exemplo 404 ou 503): o servidor respondeu com erro, então tentar de novo logo em seguida provavelmente não ajuda. O erro é relançado sem nova tentativa. Ele vem **antes** do `URLError` no código porque `HTTPError` é filho de `URLError`; se a ordem fosse invertida, o `URLError` o capturaria primeiro;
   - **timeout ou falha de rede** (`TimeoutError`, `URLError`): é um problema que pode ser temporário. Se ainda houver tentativas, registra um aviso, espera e tenta de novo. Na última tentativa, relança o erro;
   - a pausa cresce a cada tentativa: 0,5 s depois da primeira falha e 1,0 s depois da segunda (*backoff* linear).
3. Depois do laço há um `raise RuntimeError(...)` que, na prática, nunca é alcançado (toda volta do laço ou devolve ou relança). Ele existe para deixar explícito que a função nunca termina sem devolver `bytes`.

O erro que sai daqui sobe até `__collect_topic`, que marca as fontes do tópico como falhas.

### `__download_once(url)` → `bytes` (privado)

```python
encoded_url = urllib.parse.quote(url, safe=":/?&=+%()")
request = urllib.request.Request(encoded_url, headers={"User-Agent": USER_AGENT})
with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
    content = response.read(MAX_FEED_BYTES + 1)
if len(content) > MAX_FEED_BYTES:
    raise ValueError(f"Feed response exceeded {MAX_FEED_BYTES} bytes")
return content
```

1. `quote` codifica qualquer caractere que ainda não seja seguro em URL (por exemplo, acentos), mantendo os que têm função na URL (`:/?&=+%()`).
2. Monta a requisição com o cabeçalho `User-Agent`.
3. `urlopen` faz a requisição com tempo limite de 30 s. O `with` garante que a conexão é fechada mesmo se der erro.
4. Lê **no máximo** `MAX_FEED_BYTES + 1` bytes. Se vier esse byte a mais, a resposta passou do limite e é rejeitada. O truque permite detectar o excesso sem baixar uma resposta gigante inteira para a memória.

Os comentários `# noqa: S310` nessas linhas dizem ao linter (ruff) para não avisar sobre o uso de `urlopen` com URL variável, porque o esquema já foi verificado em `download`.

---

## 11. Passo 8: a exportação (`DigestExporter` e filhas)

Depois da coleta, o runner chama `export(result)` em cada exportador.

### `_utc_now()` → `datetime`

Função do módulo que devolve a data e hora atuais em UTC. É o relógio padrão do `JsonDigestExporter`. Ficar numa função separada permite que os testes passem um relógio fixo e saibam de antemão o nome do arquivo gerado.

### `DigestExporter` (classe base)

```python
class DigestExporter:
    def export(self, result: CollectionResult) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement export()")
```

Define o **contrato** de todo exportador: ter um método `export(result)`. A própria classe base não sabe exportar e lança `NotImplementedError` se for usada diretamente. Na prática, funciona como uma classe abstrata: só serve para ser herdada. `type(self).__name__` coloca na mensagem o nome da classe que esqueceu de implementar o método.

### `ConsoleDigestExporter` (filha de `DigestExporter`)

#### `__init__(output_stream=sys.stdout)`

Guarda em `__output_stream` onde escrever. O padrão é o terminal. Os testes passam um `io.StringIO` (um "arquivo" em memória) para ler o que foi escrito.

#### `export(result)`

1. Monta a lista de linhas:
   - a primeira: `Collected 105 articles across 7 topics:`;
   - uma por tópico, gerada por `__format_topic_line`.
2. Se houver fontes com falha, acrescenta `Failed sources: A, B`. Se não houver, a linha não aparece.
3. Junta as linhas com quebra de linha e escreve tudo de uma vez.

#### `__format_topic_line(topic_result)` → `str`

Devolve `"  - Economia Mundial: 15 articles"` (dois espaços, hífen, nome e quantidade).

### `JsonDigestExporter` (filha de `DigestExporter`)

Constante do módulo: `DIGEST_FILENAME_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"`, o formato da data no nome do arquivo.

#### `__init__(output_dir, clock=_utc_now)`

Guarda a pasta de saída em `__output_dir` e o relógio em `__clock`.

#### `export(result)`

```python
collected_at = self.__clock().astimezone(UTC)
digest_path = self.__output_dir / self.__build_filename(collected_at)
digest_json = json.dumps(
    self.__serialize_collection(result, collected_at),
    ensure_ascii=False,
    indent=2,
)
self.__write_atomically(digest_path, digest_json)
log.info("Digest saved to %s", digest_path)
```

1. Lê a hora no relógio e garante que está em UTC.
2. Monta o caminho do arquivo: pasta + nome com a data.
3. Transforma o resultado em dicionários e listas (`__serialize_collection`) e depois em texto JSON:
   - `ensure_ascii=False` mantém os acentos legíveis (`"Inflação"` em vez de `"Infla\u00e7\u00e3o"`);
   - `indent=2` deixa o arquivo indentado e fácil de ler.
4. Grava com segurança (`__write_atomically`) e registra o caminho no log.

#### `__build_filename(collected_at)` → `str`

Devolve `digest-20261119T190454Z.json`: ano, mês, dia, `T`, hora, minuto, segundo e `Z` (que indica UTC). Esse formato ordena os arquivos cronologicamente quando listados em ordem alfabética.

#### `__serialize_collection(result, collected_at)` → `dict`

```python
{
    "collected_at": "2026-11-19T19:04:54+00:00",   # data no formato ISO 8601
    "total_articles": 105,
    "failed_sources": [...],                       # result.all_failed_sources
    "topics": [ ...um item por tópico... ],
}
```

#### `__serialize_topic(topic_result)` → `dict`

```python
{
    "key": "world_economy",
    "display_name": "Economia Mundial",
    "article_count": 15,
    "failed_sources": [],
    "articles": [ ...um item por artigo... ],
}
```

#### `__serialize_article(article)` → `dict`

```python
{
    "title": "...",
    "url": "...",
    "source_name": "Reuters",
    "published_at": "2026-11-03T05:14:39+00:00",   # ou None, que vira null no JSON
}
```

O JSON não sabe representar `datetime`, então as datas viram texto com `.isoformat()`.

#### `__write_atomically(digest_path, digest_json)`

Grava o arquivo de forma **atômica**: ou o arquivo final aparece completo, ou não aparece.

1. Cria a pasta `output/` se não existir (`mkdir(parents=True, exist_ok=True)`).
2. `tempfile.mkstemp` cria um arquivo temporário **na mesma pasta**, com nome do tipo `.digest-abc123.tmp`, e devolve um descritor de arquivo (número que o sistema usa para o arquivo aberto) e o nome.
3. Escreve o JSON no temporário.
4. `temp_path.replace(digest_path)` renomeia o temporário para o nome final. No mesmo disco, renomear é uma operação atômica do sistema operacional, e é por isso que o temporário fica na mesma pasta.
5. Se **qualquer** coisa der errado no meio (inclusive Ctrl+C, por isso `BaseException` e não `Exception`), apaga o temporário e relança o erro.

Sem isso, uma execução interrompida no meio da gravação deixaria um JSON pela metade com o nome final.

---

## 12. Passo 9: o código de saída

`main()` devolve:

| Código | Quando |
|---|---|
| `0` | Coleta e exportações concluídas (mesmo que algum tópico tenha falhado ou que nenhum artigo tenha vindo) |
| `1` | `config/feeds.yaml` não existe, não pôde ser lido ou é inválido |
| `1` | O exportador não conseguiu gravar (`OSError`) |

Como o `ConsoleDigestExporter` vem antes do `JsonDigestExporter` na lista, o resumo aparece no terminal mesmo quando a gravação do JSON falha.

Erros que não sejam `FeedConfigError` nem `OSError` não são capturados por `main()`: o Python mostra o *traceback* completo e encerra com código `1`. Isso é proposital, porque um erro inesperado é um bug e precisa aparecer inteiro.

---

## 13. Exemplo completo de uma execução

Imagine um YAML com um único tópico:

```yaml
settings:
  max_articles_per_topic: 2
topics:
  tech:
    display_name: "Tecnologia"
    keywords: ["AI"]
    language: en
    sources:
      - name: Reuters
        domain: reuters.com
      - name: WIRED
        domain: wired.com
```

1. `python main.py` chama `main()`, que liga o log.
2. `FeedConfigLoader(FEEDS_PATH).load()` devolve:
   - `FeedSettings(max_articles_per_topic=2)`;
   - `[Topic(key="tech", display_name="Tecnologia", keywords=["AI"], language="en", sources=[Source("Reuters", "reuters.com"), Source("WIRED", "wired.com")])]`.
3. `main()` monta o downloader, o coletor, os dois exportadores e o runner.
4. `asyncio.run(runner.run())` chama `collector.collect()`, que inicia `__collect_topic(tech)`.
5. Numa thread, `__fetch_topic_articles` monta a URL:
   ```text
   https://news.google.com/rss/search?q=AI+(site:reuters.com+OR+site:wired.com)+when:7d&hl=en-US&gl=US&ceid=US:en
   ```
6. `downloader.download(url)` devolve o XML do RSS.
7. `__parse_feed_entries` lê, digamos, 3 itens:
   - `<source url="https://www.reuters.com">` vira `source_name="Reuters"`;
   - `<source url="https://www.wired.com">` vira `source_name="WIRED"`;
   - `<pubDate>Wed, 14 May 2026 10:00:00 GMT</pubDate>` vira `datetime(2026, 5, 14, 10, 0, tzinfo=UTC)`.
8. `__collect_topic` corta em 2 artigos e devolve `TopicResult(topic_key="tech", topic_display_name="Tecnologia", articles=[a1, a2], failed_sources=[])`.
9. `collect()` devolve `CollectionResult(topic_results=[...])`, com `total_articles == 2`.
10. O runner chama `ConsoleDigestExporter.export`, que imprime:
    ```text
    Collected 2 articles across 1 topics:
      - Tecnologia: 2 articles
    ```
11. O runner chama `JsonDigestExporter.export`, que grava `output/digest-20261119T190454Z.json`.
12. `main()` devolve `0`.

Se no passo 6 a rede caísse nas 3 tentativas, o passo 8 devolveria `TopicResult(..., articles=[], failed_sources=["Reuters", "WIRED"])`, o terminal mostraria `Failed sources: Reuters, WIRED` e o programa ainda terminaria com `0`.

---

## 14. Conceitos de POO e onde estão

| Conceito | Onde aparece |
|---|---|
| **Classes** | 14 classes: 6 em `models.py`, 2 em `feed_loader.py`, 1 em `collector.py`, 1 em `feed_downloader.py`, 3 em `digest_exporter.py` e 1 em `main.py` |
| **Objetos** | `main()` cria `FeedConfigLoader`, `GoogleNewsFeedDownloader`, `FeedCollector`, `ConsoleDigestExporter`, `JsonDigestExporter` e `NewsCollectionRunner` |
| **Herança** | `JsonDigestExporter` e `ConsoleDigestExporter` herdam de `DigestExporter`; `FeedConfigError` herda de `ValueError` |
| **Polimorfismo** | `NewsCollectionRunner.run()` chama `exporter.export(result)` sem saber a classe concreta; cada filha implementa `export` do seu jeito |
| **Associação** | `NewsCollectionRunner` guarda um `FeedCollector` e uma lista de `DigestExporter`; `FeedCollector` guarda `FeedSettings`, a lista de `Topic` e o `GoogleNewsFeedDownloader`; `Topic` guarda a lista de `Source`; `CollectionResult` guarda `TopicResult`; `TopicResult` guarda `Article` |
| **Atributo privado** | `__collector`, `__exporters`, `__path`, `__settings`, `__topics`, `__feed_downloader`, `__output_dir`, `__clock`, `__output_stream` |
| **Método privado** | Todos os métodos com `__` no começo, como `__load_topic`, `__collect_topic`, `__download_once` e `__write_atomically` |
| **Encapsulamento** | Cada classe expõe um único método público (`load`, `collect`, `download`, `export`, `run`) e esconde o resto |
| **Classe abstrata** (por convenção) | `DigestExporter`, cujo `export` lança `NotImplementedError` |
| **Propriedade** | `CollectionResult.total_articles` e `CollectionResult.all_failed_sources` |
| **Imutabilidade** | `@dataclass(frozen=True)` em `FeedSettings`, `Source`, `Topic` e `Article` |

### Como o Python faz o "privado" (*name mangling*)

O Python não tem `private` como Java. Quando um nome dentro de uma classe começa com dois sublinhados (e não termina com dois), o Python o **renomeia** por baixo dos panos: `self.__path` dentro de `FeedConfigLoader` vira `self._FeedConfigLoader__path`. Por isso:

- de fora da classe, `loader.__path` dá `AttributeError`;
- uma subclasse não enxerga nem sobrescreve sem querer os membros `__` da classe mãe.

Esse renomeio é o que o projeto usa como "privado".

---

## 15. Testes

Os testes ficam em `tests/` e rodam com `./_scripts/test.sh` (ou `python -m pytest tests/`). São 42 testes, e nenhum acessa a internet.

### Dublês de teste (classes falsas)

| Classe | Arquivo | O que faz |
|---|---|---|
| `CannedFeedDownloader` | `test_collector.py` | Filho de `GoogleNewsFeedDownloader`. Sobrescreve `download(url)` para devolver um RSS fixo conforme um trecho da URL (por exemplo, `"site:example.com"`) e anota as URLs pedidas em `requested_urls`. Se nenhum trecho casar, lança `ConnectionError`, simulando falha de rede |
| `OversizedFeedResponse` | `test_feed_downloader.py` | Imita a resposta HTTP e devolve 1 byte além do limite de 2 MB |
| `CannedResultCollector` | `test_main.py` | Filho de `FeedCollector`. Sobrescreve `collect()` para devolver um resultado pronto |
| `RecordingDigestExporter` | `test_main.py` | Filho de `DigestExporter`. Anota em que ordem foi chamado |

Esses dublês também são exemplos de herança e polimorfismo: o código de produção os usa sem saber que são falsos.

### O que cada arquivo testa

**`test_collector.py`**
- RSS válido vira artigos com título, fonte e data corretos.
- RSS mal formado e falha de download marcam todas as fontes do tópico como falhas.
- Os artigos mantêm a ordem do Google e respeitam o limite `max_articles_per_topic`.
- Vários tópicos são coletados de forma independente (um download por tópico).
- A URL tem as palavras-chave, os `site:`, o `when:7d` e a região certa para `en` e `pt`.
- Caracteres especiais nas palavras-chave são codificados corretamente na URL.
- Um idioma desconhecido faz o tópico falhar sem tentar download.
- A fonte é identificada pelo domínio exato, por `www.` e por subdomínio, e vira `"Unknown"` quando não há correspondência.

**`test_feed_downloader.py`**
- Resposta maior que 2 MB gera erro claro.
- URL que não é HTTP (como `file:///etc/passwd`) é recusada antes do download.

**`test_feed_loader.py`**
- Um YAML completo vira `FeedSettings` e `Topic` com os valores certos.
- Um YAML sem `settings` usa os padrões.
- Arquivo vazio, chave desconhecida, `max_articles_per_topic` fora do limite, idioma não suportado, lista de palavras-chave vazia e domínio inválido geram `FeedConfigError`.

**`test_digest_exporter.py`**
- A classe base lança erro até ser sobrescrita, e as duas filhas são `DigestExporter`.
- O JSON tem o nome com a data, cria a pasta se ela não existir, tem o resumo e os campos certos, usa `null` para data ausente, mantém acentos e funciona com resultado vazio.
- Se a gravação falha no meio, nenhum arquivo temporário fica para trás.
- O resumo do terminal mostra os totais, lista as fontes com falha e omite essa linha quando não há falha.

**`test_main.py`**
- O runner entrega o resultado a todos os exportadores, na ordem.
- O runner grava o JSON com os artigos e também quando não há nenhum artigo.
- O runner rejeita lista vazia de exportadores.
- `main()` devolve `1` com o YAML ausente ou inválido.

### Recursos do pytest usados

- `tmp_path`: uma pasta temporária nova para cada teste, apagada depois.
- `monkeypatch`: troca algo temporariamente durante um teste, por exemplo o `FEEDS_PATH` do `main` ou o `urlopen`.
- `@pytest.mark.parametrize`: roda o mesmo teste com várias entradas diferentes.
- `pytest.raises(Erro, match="texto")`: confere que um erro é lançado e que a mensagem contém o texto.

---

## 16. Scripts e ferramentas

| Script | O que faz |
|---|---|
| `_scripts/collect.sh` | Ativa o `.venv`, entra na raiz do projeto e roda `python main.py` |
| `_scripts/test.sh` | Ativa o `.venv` e roda `python -m pytest tests/`, repassando argumentos (`-v`, `-k nome` etc.) |
| `_scripts/lint.sh` | Ativa o `.venv` e roda `ruff check --fix` e `ruff format`; com `--check`, só verifica sem alterar arquivos |

Os três começam com `set -euo pipefail`, que faz o script parar no primeiro erro, tratar variável não definida como erro e considerar falha em qualquer parte de um *pipe*.

O `ruff.toml` configura o **ruff**, que faz duas coisas: aponta problemas (imports não usados, nomes fora do padrão, riscos de segurança etc.) e formata o código (linhas de até 100 caracteres, aspas duplas). Nos testes, as regras de segurança (`S`) e de `print` (`T20`) ficam desligadas.

### Bibliotecas (`requirements.txt`)

| Biblioteca | Para quê |
|---|---|
| `feedparser` | Interpretar o RSS (`sgmllib3k` é dependência dela) |
| `PyYAML` | Ler o `feeds.yaml` |
| `pytest` | Rodar os testes (`iniconfig`, `packaging`, `pluggy` e `Pygments` são dependências dele) |
| `ruff` | Lint e formatação |

O download HTTP, o JSON, as datas, os arquivos temporários e o `asyncio` vêm da biblioteca padrão do Python.

---

## 17. Glossário

| Termo | Significado |
|---|---|
| **RSS** | Formato XML que sites usam para publicar uma lista das últimas notícias |
| **Feed** | Um documento RSS: o resultado de uma busca no Google News |
| **Digest** | O resumo que o programa produz (o JSON e o texto no terminal) |
| **Dataclass** | Classe cujo construtor, comparação e representação o Python gera a partir dos atributos |
| **`frozen`** | Dataclass imutável: os atributos não podem ser alterados depois da criação |
| **`@property`** | Método acessado como atributo, sem parênteses |
| **Name mangling** | Renomeio automático de nomes com `__` no começo; é como o Python faz membros privados |
| **Corrotina** | Função `async def`; roda dentro do *event loop* e pode pausar em `await` |
| **Event loop** | O laço do `asyncio` que alterna entre as corrotinas enquanto elas esperam |
| **`asyncio.gather`** | Roda várias corrotinas ao mesmo tempo e devolve os resultados na ordem original |
| **`asyncio.to_thread`** | Roda uma função bloqueante numa thread, sem travar o *event loop* |
| **Timeout** | Tempo máximo de espera antes de desistir |
| **Retry / backoff** | Tentar de novo depois de uma falha, esperando um pouco mais a cada vez |
| **Escrita atômica** | Gravar num temporário e renomear, para que o arquivo final nunca fique pela metade |
| **UTC** | Fuso horário de referência mundial, sem horário de verão |
| **ISO 8601** | Formato padrão de data e hora, como `2026-11-19T19:04:54+00:00` |
| **Injeção de dependência** | Passar a um objeto, pelo construtor, os objetos de que ele depende |
| **Dublê de teste** | Classe falsa que substitui uma real durante os testes |
| **Código de saída** | Número que um programa devolve ao terminar: `0` é sucesso, outro valor é erro |
