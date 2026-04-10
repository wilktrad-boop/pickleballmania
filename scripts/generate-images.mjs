/**
 * Generate hero images for blog articles using Replicate Flux Pro 1.1
 *
 * Usage: node scripts/generate-images.mjs [--dry-run] [--force]
 *
 * --dry-run: Show what would be generated without actually calling the API
 * --force: Regenerate images even for articles that already have a heroImage
 */

import Replicate from 'replicate';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import https from 'https';
import http from 'http';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const CONTENT_DIR = path.join(ROOT, 'src', 'content', 'blog');
const IMAGES_DIR = path.join(ROOT, 'src', 'assets', 'blog');

const DRY_RUN = process.argv.includes('--dry-run');
const FORCE = process.argv.includes('--force');

const CATEGORY_PROMPTS = {
  actualites: 'professional sports photography of a pickleball tournament, dynamic action shot on an outdoor court, players in motion, vibrant atmosphere, editorial quality',
  tests: 'product photography of a pickleball paddle, studio lighting on clean white background, detailed close-up showing texture and design, commercial quality',
  conseils: 'pickleball training scene on an indoor court, coach demonstrating technique to player, warm natural lighting, educational and welcoming atmosphere',
  equipement: 'flat lay arrangement of pickleball equipment including paddles and balls on a clean surface, modern sports aesthetic, overhead shot, well-lit',
  debuter: 'beginner-friendly pickleball scene, diverse casual players having fun on a colorful court, sunny day, welcoming and inclusive atmosphere',
};

function slugify(text) {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 50);
}

function buildPrompt(title, category) {
  const style = CATEGORY_PROMPTS[category] || 'pickleball sport scene, vibrant and modern, professional photography';
  return `${style}, inspired by the theme: ${title}, high quality, 4k resolution, vibrant colors, modern editorial style, no text overlay, no watermark, no logos`;
}

function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const dir = path.dirname(dest);
    fs.mkdirSync(dir, { recursive: true });

    const file = fs.createWriteStream(dest);
    const client = url.startsWith('https') ? https : http;

    client.get(url, (response) => {
      if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
        file.close();
        fs.unlinkSync(dest);
        return downloadFile(response.headers.location, dest).then(resolve).catch(reject);
      }
      response.pipe(file);
      file.on('finish', () => {
        file.close();
        resolve();
      });
    }).on('error', (err) => {
      fs.unlinkSync(dest);
      reject(err);
    });
  });
}

function parseArticle(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8').replace(/\r\n/g, '\n');
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---/);
  if (!fmMatch) return null;

  const fm = fmMatch[1];
  const titleMatch = fm.match(/title:\s*"(.+?)"/);
  const categoryMatch = fm.match(/category:\s*"?(\w+)"?/);
  const heroImageMatch = fm.match(/heroImage:/);

  return {
    filePath,
    fileName: path.basename(filePath),
    title: titleMatch?.[1] || path.basename(filePath, '.md'),
    category: categoryMatch?.[1] || 'actualites',
    hasHeroImage: !!heroImageMatch,
    content,
    frontmatter: fm,
    fmEnd: fmMatch[0].length,
  };
}

function updateFrontmatter(article, imagePath) {
  const relPath = path.relative(path.dirname(article.filePath), imagePath).replace(/\\/g, '/');
  const content = article.content;

  if (article.hasHeroImage) {
    // Replace existing heroImage line
    const updated = content.replace(/heroImage:.*/, `heroImage: "${relPath}"`);
    fs.writeFileSync(article.filePath, updated, 'utf-8');
  } else {
    // Insert heroImage after category line
    const updated = content.replace(
      /category:\s*"?(\w+)"?/,
      (match) => `${match}\nheroImage: "${relPath}"`
    );
    fs.writeFileSync(article.filePath, updated, 'utf-8');
  }
}

async function main() {
  if (!process.env.REPLICATE_API_TOKEN) {
    // Try loading from .env
    const envPath = path.join(ROOT, '.env');
    if (fs.existsSync(envPath)) {
      const envContent = fs.readFileSync(envPath, 'utf-8');
      const match = envContent.match(/REPLICATE_API_TOKEN=(.+)/);
      if (match) process.env.REPLICATE_API_TOKEN = match[1].trim();
    }
  }

  if (!process.env.REPLICATE_API_TOKEN) {
    console.error('Error: REPLICATE_API_TOKEN not found. Set it in .env or environment.');
    process.exit(1);
  }

  const replicate = new Replicate({ auth: process.env.REPLICATE_API_TOKEN });

  // Find all articles
  const files = fs.readdirSync(CONTENT_DIR).filter(f => f.endsWith('.md'));
  const articles = files.map(f => parseArticle(path.join(CONTENT_DIR, f))).filter(Boolean);

  const toGenerate = FORCE
    ? articles
    : articles.filter(a => !a.hasHeroImage);

  console.log(`Found ${articles.length} articles, ${toGenerate.length} need images${FORCE ? ' (force mode)' : ''}`);

  if (toGenerate.length === 0) {
    console.log('Nothing to generate!');
    return;
  }

  for (const article of toGenerate) {
    const prompt = buildPrompt(article.title, article.category);
    const slug = slugify(article.title);
    const outputDir = path.join(IMAGES_DIR, article.category);
    const outputFile = path.join(outputDir, `${slug}.webp`);

    console.log(`\n--- ${article.fileName} ---`);
    console.log(`  Title: ${article.title}`);
    console.log(`  Category: ${article.category}`);
    console.log(`  Output: ${path.relative(ROOT, outputFile)}`);

    if (DRY_RUN) {
      console.log(`  Prompt: ${prompt.slice(0, 100)}...`);
      console.log('  [DRY RUN - skipped]');
      continue;
    }

    let success = false;
    for (let attempt = 1; attempt <= 3 && !success; attempt++) {
      try {
        if (attempt > 1) console.log(`  Retry ${attempt}/3...`);
        console.log('  Generating...');

        const output = await replicate.run('black-forest-labs/flux-1.1-pro', {
          input: {
            prompt,
            aspect_ratio: '16:9',
            output_format: 'webp',
            output_quality: 90,
            safety_tolerance: 5,
          },
        });

        // Save the output - Replicate SDK may return different types
        fs.mkdirSync(path.dirname(outputFile), { recursive: true });

        if (output && typeof output[Symbol.asyncIterator] === 'function') {
          // ReadableStream / FileOutput - read chunks
          const chunks = [];
          for await (const chunk of output) {
            chunks.push(typeof chunk === 'string' ? Buffer.from(chunk) : chunk);
          }
          fs.writeFileSync(outputFile, Buffer.concat(chunks));
        } else if (typeof output === 'string' && output.startsWith('http')) {
          await downloadFile(output, outputFile);
        } else if (output && typeof output === 'object' && output.url) {
          const url = typeof output.url === 'function' ? output.url() : output.url;
          await downloadFile(url, outputFile);
        } else {
          // Try toString as last resort
          const str = String(output);
          if (str.startsWith('http')) {
            await downloadFile(str, outputFile);
          } else {
            console.error('  Error: unexpected output format:', typeof output);
            break;
          }
        }

        const size = fs.statSync(outputFile).size;
        console.log(`  Saved: ${(size / 1024).toFixed(0)} KB`);

        // Update frontmatter
        updateFrontmatter(article, outputFile);
        console.log('  Frontmatter updated');
        success = true;

      } catch (err) {
        const msg = err.message || String(err);
        if (msg.includes('429') || msg.includes('Too Many Requests')) {
          const retryMatch = msg.match(/retry_after.*?(\d+)/);
          const wait = retryMatch ? parseInt(retryMatch[1]) + 2 : 12;
          console.log(`  Rate limited, waiting ${wait}s...`);
          await new Promise(r => setTimeout(r, wait * 1000));
        } else {
          console.error(`  Error: ${msg}`);
          break; // Don't retry non-rate-limit errors
        }
      }
    }

    // Delay between successful calls to avoid rate limiting
    if (success) {
      await new Promise(r => setTimeout(r, 10000));
    }
  }

  console.log('\nDone!');
}

main().catch(console.error);
