# Facebook Group Lead Comment Bot (n8n-integrated)

Objetivo: Monitorar um grupo do Facebook, enviar o texto do post para um webhook do n8n (onde você gera a resposta com IA) e comentar automaticamente no post com a resposta recebida.

## Visão geral
- Selenium + Chrome para automação do Facebook
- Webhook do n8n para gerar a resposta personalizada
- Deduplicação por ID do post para não comentar mais de uma vez
- Configuração via .env

## Requisitos
- Python 3.10+
- Google Chrome instalado
- Pacotes Python: ver `requirements.txt`

## Instalação
1. Crie um virtualenv e instale dependências:
   pip install -r requirements.txt

2. Configure o arquivo `.env` (crie na raiz do projeto, ao lado do `main.py`):
   N8N_WEBHOOK_URL=http://localhost:5678/webhook/308ca8c9-395f-4889-a946-50ff9e7ac401
   FB_GROUP_URL=https://www.facebook.com/groups/768640319860824
   HEADLESS=false
   COOKIES_PATH=./cookies.json
   LOOP_INTERVAL_SECONDS=60

3. Exporte cookies do Facebook (logado) com uma extensão como "Cookie-Editor" e salve em `cookies.json` na raiz. O formato deve ser a lista padrão de cookies de extensões (lista de objetos com domain, name, value etc.).

4. Execute:
   python main.py

## Como funciona
- O script abre o grupo, faz scroll, coleta posts e extrai texto.
- Para cada post ainda não processado, envia o texto ao n8n via POST JSON { "text": "<conteúdo>" }.
- Se o n8n retornar `{"reply": "..."}`, o bot comenta no post.
- O arquivo `processed_posts.json` guarda os IDs já comentados.

## Dicas
- Ajuste seletores e delays se perceber mudanças no Facebook.
- Se quiser rodar sem UI, defina HEADLESS=true no .env.
- Se o Facebook mudar labels de botões por idioma, o script já tenta múltiplas variações.

## Estrutura
- main.py – loop principal
- fb_bot/login.py – inicializa o driver e aplica cookies
- fb_bot/monitor.py – navega, extrai posts e texto
- fb_bot/commenter.py – localiza a caixa e comenta
- fb_bot/n8n_client.py – chama o webhook do n8n
- fb_bot/config.py – carrega variáveis de ambiente

## n8n (exemplo de fluxo)
- Nó Webhook (POST) → Nó IA (gera mensagem) → Nó Respond to Webhook (JSON { reply })
- Lembre de usar o endpoint de produção (sem /webhook-test) quando for rodar o bot.

