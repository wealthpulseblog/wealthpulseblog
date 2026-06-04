const fs = require("fs");
const path = require("path");

function loadAffiliateData() {
  try {
    const file = path.join(__dirname, "src", "_data", "affiliate.json");
    if (!fs.existsSync(file)) return {};
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (e) {
    return {};
  }
}

function productCardHtml(product) {
  if (!product) return "";
  const name = product.name || "Recommended Product";
  const desc = product.description || "";
  const url = product.url || "#";
  const button = product.cta || "Learn more";

  return `
<section class="affiliate-section">
  <div class="product-card">
    <h3>${name}</h3>
    <p>${desc}</p>
    <a href="${url}" target="_blank" rel="nofollow sponsored">${button}</a>
  </div>
</section>
`.trim();
}

module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("assets");
  eleventyConfig.addPassthroughCopy("admin");

  eleventyConfig.addFilter("year", () => new Date().getFullYear());

  eleventyConfig.addFilter("isoDate", (dateObj) => {
    if (!dateObj) return "";
    return new Date(dateObj).toISOString();
  });

  eleventyConfig.addFilter("readableDate", (dateObj) => {
    if (!dateObj) return "";
    return new Date(dateObj).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  });

  eleventyConfig.addFilter("truncate", (str, len = 120) => {
    if (!str) return "";
    if (str.length <= len) return str;
    return str.slice(0, len).trimEnd() + "…";
  });

  eleventyConfig.addFilter("wordcount", (content) => {
    if (!content) return 0;
    const text = content.replace(/<[^>]*>/g, " ");
    return text.trim().split(/\s+/).filter(Boolean).length;
  });

  eleventyConfig.addCollection("articles", (collectionApi) => {
    return collectionApi
      .getAll()
      .filter((item) => item.data && item.data.tags && item.data.tags.includes("articles"))
      .filter((item) => !item.data.draft)
      .sort((a, b) => b.date - a.date);
  });

  eleventyConfig.addCollection("featured", (collectionApi) => {
    return collectionApi
      .getAll()
      .filter((item) => item.data && item.data.tags && item.data.tags.includes("articles"))
      .filter((item) => item.data && item.data.featured === true)
      .filter((item) => !item.data.draft)
      .sort((a, b) => b.date - a.date);
  });

  eleventyConfig.addTransform("replaceProductPlaceholders", function (content, outputPath) {
    if (!outputPath || !outputPath.endsWith(".html")) return content;

    const affiliate = loadAffiliateData();

    return content.replace(/\[product:([^\]]+)\]/g, (_, slug) => {
      const product = affiliate[slug];
      return productCardHtml(product);
    });
  });

  return {
    dir: {
      input: "src",
      includes: "_includes",
      data: "_data",
      output: "_site",
    },
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
  };
};
