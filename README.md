
# Facebook Bot with Playwright

Bot que monitora um grupo do Facebook, extrai autor, texto e imagens dos posts, envia ao n8n para processamento por IA e comenta de volta automaticamente.

## Características

- ✅ Automação com Playwright (headless/visual)
- ✅ Interface web Flask para configuração e monitoramento
- ✅ Processamento assíncrono não-bloqueante
- ✅ Integração com n8n via webhook
- ✅ Estado persistente para evitar reprocessamento
- ✅ Logs estruturados e debug dumps
- ✅ Parada limpa sem threads órfãos
- ✅ Testes automatizados com pytest

## Instalação

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Instalar navegadores do Playwright

```bash
playwright install
```

### 3. Configurar variáveis de ambiente

Copie `.env.example` para `.env` e configure:

```bash
N8N_WEBHOOK_URL=https://seu-n8n.com/webhook/facebook-bot
FACEBOOK_GROUP_URL=https://facebook.com/groups/seu-grupo
KEYWORDS=["palavra1", "palavra2", "palavra3"]
LOOP_INTERVAL_SECONDS=120
MAX_POSTS_PER_CYCLE=15
HEADLESS=true
```

## Execução

### Modo desenvolvimento

```bash
python app.py
```

Acesse: http://localhost:5000

### Executar testes

```bash
# Todos os testes
pytest

# Testes específicos
pytest tests/test_monitor.py -v

# Com coverage
pytest --cov=fb_bot tests/
```

### Scripts de validação

```bash
# Verificar configuração
python -c "from fb_bot.config import config; print(config.is_valid())"

# Testar webhook n8n
python -c "import asyncio; from fb_bot.n8n_client import healthcheck_n8n; print(asyncio.run(healthcheck_n8n('SUA_URL')))"
```

## Uso

1. **Configure o bot** na página `/config`:
   - URL do webhook n8n
   - URL do grupo Facebook
   - Palavras-chave para filtrar posts
   - Intervalo entre ciclos (30-3600s)

2. **Inicie o bot** via interface web ou API:
   ```bash
   curl -X POST http://localhost:5000/api/start
   ```

3. **Monitore logs** em tempo real na página `/logs`

4. **Pare o bot** de forma limpa:
   ```bash
   curl -X POST http://localhost:5000/api/stop
   ```

## Arquitetura

```
fb_bot/
├── config.py          # Configurações com validação
├── login.py           # Gerenciamento de login Facebook
├── monitor.py         # Extração de posts e conteúdo
├── commenter.py       # Sistema de comentários
├── n8n_client.py      # Cliente assíncrono para n8n
└── selectors.py       # Seletores CSS do Facebook

app.py                 # Servidor Flask com API
main.py               # Loop principal assíncrono
state_manager.py      # Gerenciamento de estado thread-safe
logger.py             # Sistema de logging
```

## API Endpoints

- `GET /` - Dashboard principal
- `GET /config` - Página de configuração
- `GET /logs` - Visualização de logs
- `GET /api/status` - Status do bot (JSON)
- `POST /api/start` - Iniciar bot
- `POST /api/stop` - Parar bot
- `POST /api/save-config` - Salvar configurações
- `POST /api/test-webhook` - Testar conexão n8n

## Fluxo n8n

O webhook deve retornar JSON no formato:

```json
{
  "reply": "Sua resposta da IA aqui"
}
```

Payload enviado ao n8n:

```json
{
  "prompt": "Texto extraído do post",
  "author": "Nome do autor",
  "image_url": "URL da imagem principal",
  "post_id": "ID único do post"
}
```

## Troubleshooting

### Bot não encontra posts

- Verifique se o grupo é público ou se você tem acesso
- Ajuste seletores em `fb_bot/selectors.py` se necessário
- Veja debug dumps em `html_dumps/` para análise

### Erro de login

- Delete `sessions/` e `cookies.json` para login fresh
- Execute em modo não-headless (`HEADLESS=false`) para login manual
- Verifique se não há checkpoint/2FA pendente

### n8n não responde

- Teste conexão: `curl -X POST sua-webhook-url`
- Verifique logs do n8n para erros
- Confirme formato do payload

### Captcha detectado

- Bot pausa automaticamente quando detecta captcha
- Resolva manualmente no Facebook
- Reinicie o bot após resolver

## Configuração avançada

### Limites e intervals

```env
LOOP_INTERVAL_SECONDS=120    # 30-3600 segundos
MAX_POSTS_PER_CYCLE=15      # 5-50 posts
```

### Debug e desenvolvimento

```env
HEADLESS=false              # Ver navegador
LOG_LEVEL=DEBUG            # Logs verbosos
```

### Performance

```env
# Reduzir para grupos com alta atividade
MAX_POSTS_PER_CYCLE=10
LOOP_INTERVAL_SECONDS=180
```

## Contribuição

1. Execute testes: `pytest`
2. Verifique tipos: `mypy fb_bot/`  
3. Formate código: `ruff format .`
4. Lint: `ruff check .`

## Changelog

### v2.0.0
- Refatoração completa para assíncrono não-bloqueante
- Testes automatizados com pytest
- Parada limpa sem threads órfãos
- Configuração thread-safe com validação
- Client n8n assíncrono com retry/backoff
- Extração melhorada de autor/texto/imagens
- Detecção de captcha automática

### v1.x.x
- Versão inicial com requests síncronos
- Interface Flask básica
- Login persistente com cookies
