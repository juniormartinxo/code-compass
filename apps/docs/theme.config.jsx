export default {
  logo: <strong>📍 Code Compass</strong>,
  project: {
    link: 'https://github.com/juniormartinxo/code-compass',
  },
  docsRepositoryBase: 'https://github.com/juniormartinxo/code-compass/tree/main/docs',
  useNextSeoProps() {
    return {
      titleTemplate: '%s – Code Compass',
    };
  },
  head: (
    <>
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <meta name="description" content="Documentação técnica do Code Compass - Context Platform para codebases" />
      <meta name="og:title" content="Code Compass Docs" />
    </>
  ),
  editLink: {
    component: null, // Desabilita "Edit this page"
  },
  feedback: {
    content: null, // Desabilita feedback widget
  },
  footer: {
    text: (
      <span>
        {new Date().getFullYear()} © Code Compass Team
      </span>
    ),
  },
  darkMode: true,
  primaryHue: 210,
  primarySaturation: 100,
  search: {
    placeholder: 'Buscar na documentação...',
  },
  toc: {
    title: 'Nesta página',
  },
  navigation: {
    prev: true,
    next: true,
  },
}
