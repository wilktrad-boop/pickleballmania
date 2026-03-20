// @ts-check
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import vercel from '@astrojs/vercel';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'astro/config';

export default defineConfig({
	site: 'https://pickleballmania.fr',
	output: 'static',
	adapter: vercel(),
	integrations: [mdx(), sitemap()],
	vite: {
		plugins: [tailwindcss()],
	},
});
