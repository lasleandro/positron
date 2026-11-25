# Deploy no Azure

A imagem do repositório compila o frontend React (Vite) em um estágio Node e executa Django e Gunicorn (Python 3.11) na porta 8000, servindo a API em `/api/` e o SPA nas demais rotas. Esta configuração usa **Azure App Service Linux com contêiner personalizado**, **Azure Container Registry** e **Azure Database for PostgreSQL Flexible Server**. Comece com uma instância do App Service. O contêiner roda as migrações antes de inicializar o Gunicorn. A versão com cofre requer uma instalação anterior vazia ou um banco novo. Leia a [avaliação de criptografia](crypto_assessment_2026-11-25.md) antes de atualizar uma instância com dados.

## 1. Rede e banco

- Use PostgreSQL 17 e um banco dedicado. Para produção, coloque o PostgreSQL em rede privada e use a integração de VNet do App Service. Com Flexible Server em VNet, use uma subnet delegada para PostgreSQL, outra para App Service e DNS privado associado à VNet. O hostname usado pelo cliente deve ser o FQDN fornecido pelo Azure.
- Conecte-se ao banco inicial a partir de uma máquina com acesso à VNet. Como administrador do PostgreSQL, crie o banco e uma conta de aplicação dedicada. Por exemplo, no `psql`:

```sql
CREATE ROLE exames_app LOGIN;
\password exames_app
GRANT exames_app TO CURRENT_USER;
CREATE DATABASE meus_exames OWNER exames_app;
```

A aplicação usa TLS com `sslmode=verify-full` em produção. A imagem usa as raízes do pacote `ca-certificates`. Se a sua configuração precisar de um bundle adicional, inclua-o na imagem e aponte `POSTGRES_SSLROOTCERT` para o caminho do PEM.

## 2. Imagem e App Service

Crie o ACR em modo de permissões RBAC do registro e um App Service Linux com contêiner personalizado. Crie a imagem a partir da raiz do repositório. Em vez de reutilizar a tag, escolha uma nova para cada versão.

```bash
ACR='<nome-do-registro>'
APP='<nome-do-app>'
RG='<grupo-do-app>'
TAG='v0.1.0'

az acr build --registry "$ACR" --image "pode-abrir:$TAG" .
ACR_LOGIN="$(az acr show --name "$ACR" --query loginServer -o tsv)"
ACR_ID="$(az acr show --name "$ACR" --query id -o tsv)"
APP_PRINCIPAL="$(az webapp identity assign -g "$RG" -n "$APP" --query principalId -o tsv)"
az role assignment create --assignee-object-id "$APP_PRINCIPAL" \
  --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID"
az webapp config set -g "$RG" -n "$APP" \
  --generic-configurations '{"acrUseManagedIdentityCreds": true}'
az webapp update -g "$RG" -n "$APP" --https-only true
```

Se a criação do App Service já pedir a imagem, publique-a primeiro. Aguarde a propagação da permissão antes de testar o pull. Os comandos de configuração de registro e contêiner abaixo supõem um Web App no modo clássico. Se a criação foi feita no modo sidecar, configure a imagem e a identidade gerenciada em **Deployment Center → Containers** e informe **8000** como porta do contêiner principal.

## 3. Configuração

Em um ambiente local com as dependências deste repositório:

```bash
APP_ENV=development python manage.py bootstrap_invite
```

No Azure Portal, adicione estas variáveis em **Settings → Environment variables**. Use o conteúdo de cada valor gerado sem as aspas externas. Guarde as chaves e a senha em local privado. Referências do Azure Key Vault também servem para os três segredos de longa duração.

| Variável | Valor |
|---|---|
| `APP_ENV` | `production` |
| `APP_ORIGIN` | URL HTTPS final, sem barra no fim. Use o hostname real exibido no App Service. |
| `VAULT_NAMESPACE` | Valor público estável gerado por `bootstrap_invite`. Preserve-o em backups de configuração e restaurações. Mudá-lo torna incompatíveis as credenciais e as chaves existentes. |
| `DJANGO_SECRET_KEY` | Valor gerado por `bootstrap_invite` |
| `TOTP_ENCRYPTION_KEY` | Chave Fernet gerada no mesmo comando. Guarde uma cópia segura junto do plano de recuperação do banco. |
| `BOOTSTRAP_INVITE_DIGEST` | Digest do convite inicial gerado pelo comando. O convite público é o código fornecido separadamente. |
| `POSTGRES_HOST` | FQDN do PostgreSQL Flexible Server |
| `POSTGRES_PORT` | `5432`, valor padrão |
| `POSTGRES_DB` | `meus_exames`, se usou o nome sugerido |
| `POSTGRES_USER` | `exames_app`, se usou o nome sugerido |
| `POSTGRES_PASSWORD` | Senha da conta de aplicação |
| `WEBSITES_PORT` | `8000` no modo clássico |
| `WEBSITE_WARMUP_PATH` | `/healthz` |
| `WEBSITE_WARMUP_STATUSES` | `200` |
| `EMAIL_ENABLED` + `EMAIL_SMTP_*`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME` | Obrigatórios em produção (convites e redefinição de senha). O contêiner inicia o worker `send_emails` junto do Gunicorn. Use um domínio com SPF, DKIM e DMARC. |
| `PASSWORD_RESET_MINUTES` | Validade do link de redefinição (padrão 30) |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | Notificações push do app instalável. Gere com `python manage.py generate_vapid`. Sem elas, o push fica desativado. |
| `GRANT_MAX_MINUTES`, `LINK_VIEW_MINUTES`, `LINK_PIN_MAX_FAILURES` | Limites do acesso efêmero (padrões em `.env.example`) |
| Limites opcionais | `OWNER_SESSION_MINUTES`, `CONSULT_PAIR_MINUTES`, `CONSULT_ACCESS_MINUTES`, `ENROLLMENT_MINUTES`, `INVITATION_HOURS`, `PDF_MAX_MB`, `EXAM_PAGE_SIZE` (padrões em `.env.example`) |

Depois, configure a imagem no App Service clássico:

```bash
az webapp config container set -g "$RG" -n "$APP" \
  --container-image-name "$ACR_LOGIN/pode-abrir:$TAG" \
  --docker-registry-server-url "https://$ACR_LOGIN"
```

Defina `/healthz` como Health check no Portal. O endpoint verifica a conexão com o banco e devolve apenas `ok`. Após o primeiro start, abra `/cadastro/` no domínio final, expanda “Primeira conta desta instalação”, informe o código gerado e o seu email, e conclua o cadastro pelo link recebido. Guarde o código de recuperação exibido no cadastro. Você pode remover `BOOTSTRAP_INVITE_DIGEST` do App Service após criar essa conta. Os outros usuários entram por convite enviado ao email deles pelo painel.

## 4. Teste e operação

- Teste em HTTPS com dois navegadores e PDFs fictícios. Crie uma segunda conta, confira que cada uma lista somente seus próprios exames, autorize um subconjunto, abra um PDF e encerre o acesso com o leitor aberto. Atualize a aba e confirme que o arquivo continua bloqueado.
- Use os backups do Flexible Server e teste uma restauração. Antes de colocar uma restauração em serviço, invalide sessões antigas com `python manage.py flush_access --confirm-restore` para evitar que permissões restauradas voltem a valer. Rode esse comando somente após parar o tráfego para a instância restaurada.
- Execute `python manage.py prune_access` periodicamente em um ambiente com acesso ao banco. O comando limpa consultas, convites, sessões e dados de limitação expirados. O app verifica as expirações mesmo entre limpezas.
- A v0 não tem recuperação de conta ou de MFA pelo próprio usuário. Guarde a chave de criptografia TOTP fora do banco. Ela é necessária para recuperar os fatores do Authenticator após uma restauração. Preserve também o `VAULT_NAMESPACE`; cada usuário ainda precisa da senha original para abrir o cofre.
- O modo de consulta controla o acesso HTTP do navegador. Capturas e cópias já feitas permanecem com o destinatário.

## 5. Domínio podeabrir.com e e-mail

Passos manuais (não executados a partir deste repositório):

1. **Domínio no App Service**: em **Custom domains**, adicione `podeabrir.com` (registro `A` + `TXT asuid`)
   e `www.podeabrir.com` (`CNAME`). Crie o **App Service Managed Certificate** para os dois e vincule com
   SNI. Redirecione `www` para o domínio raiz.
2. **Configuração**: `APP_ORIGIN=https://podeabrir.com`. Os links de convite, redefinição, QR de leitura,
   endereços `@nome` e links compartilhados usam esse valor.
3. **E-mail**: crie a caixa de envio do domínio (por exemplo `nao-responda@podeabrir.com`), publique SPF,
   DKIM e DMARC, e troque `EMAIL_SMTP_*`, `EMAIL_FROM_ADDRESS` e `EMAIL_REPLY_TO`. Até lá, o
   desenvolvimento usa a caixa de testes `auth@tennisos.com.br` com o nome "Pode Abrir".
4. **Push**: gere as chaves VAPID uma única vez por ambiente e guarde-as com os demais segredos; trocar a
   chave invalida as inscrições existentes (os usuários reativam em Conta).
5. **Teste após publicar**: leitura presencial em dois dispositivos, link de leitura única aberto no
   WhatsApp (a prévia não pode consumir a abertura), pedido por `podeabrir.com/@nome` com conferência do
   código de 6 dígitos e uma notificação push no celular com o app instalado.

## Referências

- [App Service com contêiner personalizado e identidade gerenciada](https://learn.microsoft.com/azure/app-service/configure-custom-container)
- [Variáveis de configuração do App Service](https://learn.microsoft.com/azure/app-service/reference-app-settings)
- [TLS no PostgreSQL Flexible Server](https://learn.microsoft.com/azure/postgresql/security/security-tls-how-to-connect)
- [Adicionar conta de terceiros no Microsoft Authenticator](https://support.microsoft.com/en-us/authenticator/how-to-add-your-accounts-to-microsoft-authenticator)
