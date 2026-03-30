const affiliate = require('./affiliate.json');

module.exports = Object.values(affiliate)
  .filter(Array.isArray)
  .flat()
  .filter((item) => item.go_slug)
  .map((item) => {
    const raw = item.url || '';
    const usable = /^https?:\/\//i.test(raw) && !raw.startsWith('REPLACE_');
    return {
      go_slug: item.go_slug,
      url: usable ? raw : '/',
      name: item.name || item.go_slug,
    };
  });
