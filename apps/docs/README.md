# Code Compass - Portal de Documentação

Portal de documentação técnica do **Code Compass** construído com [Nextra](https://nextra.site).

## 🚀 Quick Start

```bash
# Instalar dependências
pnpm install

# Desenvolvimento (localhost:3000)
pnpm dev

# Build de produção
pnpm build

# Preview do build
pnpm start
```

## 📚 Estrutura

- **`pages/`** - Documentação em Markdown/MDX (file-system routing)
- **`theme.config.jsx`** - Configuração do tema Nextra
- **`next.config.mjs`** - Configuração do Next.js + Nextra
- **`MIGRATION_LOG.md`** - Log da migração dos docs originais

## ✨ Features

- ✅ **Busca Full-Text** com FlexSearch
- ✅ **Dark Mode** nativo
- ✅ **Navegação automática** (prev/next)
- ✅ **Syntax Highlighting** para código
- ✅ **Mobile-first** e responsivo
- ✅ **SEO otimizado**
- ✅ **Performance** - Geração estática (SSG)

## 📖 Conteúdo

O portal documenta:

- **Arquitetura** - Visão geral do sistema
- **ADRs** - Decisões arquiteturais (6 documentos)
- **Indexer** - Sistema de indexação e RAG
- **CLI** - Interface de linha de comando
- **MCP** - Model Context Protocol integration

## 🛠️ Tecnologias

- Next.js 14.2 (Pages Router)
- Nextra 3.3
- React 18.3
- TypeScript 5.x

## 📝 Adicionando Conteúdo

1. Crie arquivos `.md` ou `.mdx` em `pages/`
2. Atualize `_meta.js` no diretório para definir ordem e títulos
3. O Nextra gera rotas automaticamente baseado em file-system

Exemplo:

```js
// pages/nova-secao/_meta.js
export default {
  'intro': 'Introdução',
  'guia': 'Guia Completo',
};
```

## 🎨 Customização

Edite `theme.config.jsx` para ajustar:

- Logo e branding
- Links do GitHub
- Footer
- Cor primária
- Configurações de busca

## 📦 Deploy

### Vercel (Recomendado)

```bash
vercel --prod
```

### Build estático

```bash
pnpm build
# Arquivos gerados em .next/ e out/ (se usar 'output: export')
```

## 🔗 Links

- [Documentação Nextra](https://nextra.site)
- [Next.js Docs](https://nextjs.org/docs)
- [Repositório Code Compass](https://github.com/juniormartinxo/code-compass)

---

**Migrado em:** 2026-02-10  
**Engine:** Nextra 3.3 + Next.js 14
